from flask import Flask, render_template, request, redirect, url_for, jsonify
from database import db, Order, Garment
from datetime import datetime
import random
import string
import os

app = Flask(__name__)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'laundry.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

# Hardcoded price list
PRICES = {
    'Shirt': 5.0,
    'Pants': 7.0,
    'Saree': 10.0,
    'Blazer': 12.0,
    'Dress': 8.0,
    'Suit': 15.0
}

def generate_order_id():
    """Generate unique order ID: LD + timestamp + random chars"""
    timestamp = datetime.now().strftime('%Y%m%d')
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"LD{timestamp}{random_str}"

@app.route('/')
def index():
    """Dashboard - Home page"""
    # Get filter parameters
    status_filter = request.args.get('status', '')
    search_query = request.args.get('search', '')
    
    # Build query
    query = Order.query
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    if search_query:
        query = query.filter(
            db.or_(
                Order.customer_name.contains(search_query),
                Order.phone.contains(search_query)
            )
        )
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    # Calculate dashboard stats
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    
    status_counts = {
        'RECEIVED': Order.query.filter_by(status='RECEIVED').count(),
        'PROCESSING': Order.query.filter_by(status='PROCESSING').count(),
        'READY': Order.query.filter_by(status='READY').count(),
        'DELIVERED': Order.query.filter_by(status='DELIVERED').count()
    }
    
    return render_template('index.html', 
                         orders=orders, 
                         total_orders=total_orders,
                         total_revenue=round(total_revenue, 2),
                         status_counts=status_counts,
                         current_status=status_filter,
                         current_search=search_query)

@app.route('/create', methods=['GET', 'POST'])
def create_order():
    """Create new order"""
    if request.method == 'POST':
        try:
            customer_name = request.form['customer_name']
            phone = request.form['phone']
            
            # Get garment data
            garment_types = request.form.getlist('garment_type[]')
            quantities = request.form.getlist('quantity[]')
            
            # Create order
            order_id = generate_order_id()
            new_order = Order(
                order_id=order_id,
                customer_name=customer_name,
                phone=phone,
                status='RECEIVED',
                total_amount=0
            )
            
            db.session.add(new_order)
            db.session.flush()  # Get order.id without committing
            
            total_bill = 0
            
            # Add garments
            for i in range(len(garment_types)):
                if garment_types[i] and quantities[i]:
                    g_type = garment_types[i]
                    qty = int(quantities[i])
                    price = PRICES.get(g_type, 0)
                    item_total = price * qty
                    total_bill += item_total
                    
                    garment = Garment(
                        order_id=new_order.id,
                        garment_type=g_type,
                        quantity=qty,
                        price_per_item=price,
                        total=item_total
                    )
                    db.session.add(garment)
            
            new_order.total_amount = total_bill
            db.session.commit()
            
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            return f"Error: {str(e)}", 400
    
    return render_template('create_order.html', prices=PRICES)

@app.route('/update-status/<int:order_id>', methods=['GET', 'POST'])
def update_status(order_id):
    """Update order status"""
    order = Order.query.get_or_404(order_id)
    
    if request.method == 'POST':
        new_status = request.form['status']
        order.status = new_status
        db.session.commit()
        return redirect(url_for('index'))
    
    # Get garments for this order
    garments = Garment.query.filter_by(order_id=order_id).all()
    
    return render_template('update_status.html', order=order, garments=garments)

@app.route('/api/order/<int:order_id>')
def get_order_details(order_id):
    """API endpoint for order details"""
    order = Order.query.get_or_404(order_id)
    garments = Garment.query.filter_by(order_id=order_id).all()
    
    return jsonify({
        'order_id': order.order_id,
        'customer_name': order.customer_name,
        'phone': order.phone,
        'status': order.status,
        'total': order.total_amount,
        'garments': [{
            'type': g.garment_type,
            'quantity': g.quantity,
            'price': g.price_per_item,
            'total': g.total
        } for g in garments]
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)