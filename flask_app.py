import re,random, json, os, time
from flask_socketio import SocketIO, send
from flask import Flask, flash, render_template, redirect, url_for, request, session
from flask_sqlalchemy import SQLAlchemy 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'development'
socketio = SocketIO(app, cors_allowed_origins='*')

db = SQLAlchemy(app)

login_manager = LoginManager() 
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) 


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), unique=True)
    password = db.Column(db.String(30))
    rice = db.Column(db.Integer, default=20)
    usd = db.Column(db.Integer, default=10000)
    orders = db.relationship('OpenOrder', cascade ='all,delete' , backref='user')
    
class OpenOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(6))
    price = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    buy_sell = db.Column(db.String(4))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    email = db.Column(db.String(320))
    time = db.Column(db.Float())
    
class CompleteOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(6))
    price = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    buyer_email = db.Column(db.String(320))
    seller_email = db.Column(db.String(320))
    time = db.Column(db.Float())



def open_order_fetch(limit=False):
    if limit:
        OpenOrders = OpenOrder.query.order_by(OpenOrder.price).limit(limit)
    else:
        OpenOrders = OpenOrder.query.order_by(OpenOrder.price)
    buy_orders, sell_orders=[],[]
    for x in OpenOrders:
        cont = False
        if x.buy_sell == "buy":
            for y,z in enumerate(buy_orders):
                if x.price == buy_orders[y]['price']:
                    buy_orders[y]['quantity'] += x.quantity
                    cont = True
                    break
            if cont:
                continue
            buy_orders.append({"price":x.price, "quantity":x.quantity})
        else:
            for y,z in enumerate(sell_orders):
                if x.price == sell_orders[y]['price']:
                    sell_orders[y]['quantity'] += x.quantity
                    cont = True
                    break
            if cont:
                continue
            sell_orders.insert(0,{"price":x.price, "quantity":x.quantity})
    return {"buy":buy_orders, "sell":sell_orders, "action":"open_order_update"}



def order_request(orderform_user):
    orders = []
    quantity_balance = int(orderform_user['quantity'])
    
    
    if orderform_user["trade_type"] == "Buy":
        if current_user.usd >= int(orderform_user['price']) * quantity_balance:
            open_orders = OpenOrder.query.filter(OpenOrder.buy_sell == "buy").order_by(OpenOrder.price)
            open_order_count = 0
            for open_order in open_orders:
                open_order_count += 1
                if int(orderform_user['price']) >= open_order.price and quantity_balance >= open_order.quantity:
                    orders.append(CompleteOrder(commodity=orderform_user['commodity'], 
                                                price=open_order.price, 
                                                quantity=open_order.quantity, 
                                                buyer_email=current_user.email, 
                                                seller_email=open_order.email))
                                                
                    quantity_balance -= open_order.quantity
                    current_user.usd -= open_order.quantity * open_order.price
                    open_order.user.usd += open_order.quantity * open_order.price
                    current_user.rice += open_order.quantity
                    db.session.delete(open_order)
                    
                elif int(orderform_user['price']) >= open_order.price and quantity_balance > 0:
                    orders.append(CompleteOrder(commodity=orderform_user['commodity'], 
                                                price=open_order.price, 
                                                quantity=quantity_balance, 
                                                buyer_email=current_user.email, 
                                                seller_email=open_order.email))
                                                
                    current_user.usd -= quantity_balance * open_order.price
                    open_order.user.usd += quantity_balance * open_order.price
                    current_user.rice += quantity_balance
                    open_order.quantity -= quantity_balance 
                    quantity_balance = 0
                    
                    
            if open_order_count == 0 or quantity_balance > 0:
                new_open_order = OpenOrder(commodity = orderform_user['commodity'], 
                                      price = orderform_user['price'], 
                                      quantity = quantity_balance, 
                                      buy_sell = "sell", 
                                      user_id = current_user.id, 
                                      email = current_user.email, 
                                      time = time.time())
                
                current_user.usd -= quantity_balance * int(orderform_user['price'])
                quantity_balance = 0        
                db.session.add(new_open_order)
                
                
                
            db.session.add_all(orders)
            db.session.commit()
            trades = []
            for order in orders:
                trades.append({"price":order.price, "quantity":order.quantity, "buysell":None})
            return {"action":"recent_trade_update", "orders": trades}
        else:
            return {"action":"error", "message":"Insuffient funds or commodity"}
            
            
            
    elif orderform_user["trade_type"] == "Sell":
        if current_user.rice >= quantity_balance:
            open_orders = OpenOrder.query.filter(OpenOrder.buy_sell == "sell").order_by(OpenOrder.price.desc())
            open_order_count = 0
            for open_order in open_orders:
                open_order_count += 1
                if int(orderform_user['price']) <= open_order.price and quantity_balance >= open_order.quantity:
                    orders.append(CompleteOrder(commodity=orderform_user['commodity'], 
                                                price=open_order.price, 
                                                quantity=open_order.quantity, 
                                                buyer_email=open_order.email, 
                                                seller_email=current_user.email))
                                                
                    quantity_balance -= open_order.quantity
                    current_user.usd += open_order.quantity * open_order.price
                    current_user.rice -= open_order.quantity
                    open_order.user.rice += open_order.quantity
                    db.session.delete(open_order)
                    
                elif int(orderform_user['price']) <= open_order.price and quantity_balance > 0:
                    orders.append(CompleteOrder(commodity=orderform_user['commodity'], 
                                                price=open_order.price, 
                                                quantity=quantity_balance, 
                                                buyer_email=current_user.email, 
                                                seller_email=open_order.email))
                    current_user.usd += quantity_balance * open_order.price
                    current_user.rice -= quantity_balance
                    open_order.user.rice += quantity_balance
                    open_order.quantity -= quantity_balance 
                    quantity_balance = 0
                    

            if open_order_count == 0 or quantity_balance > 0:
                new_open_order = OpenOrder(commodity = orderform_user['commodity'], 
                                      price = orderform_user['price'], 
                                      quantity = quantity_balance, 
                                      buy_sell = "buy", 
                                      user_id = current_user.id, 
                                      email = current_user.email, time = time.time())
                                      
                current_user.rice -= quantity_balance                      
                quantity_balance = 0                      
                db.session.add(new_open_order)
                
            print(quantity_balance)
            db.session.add_all(orders)
            db.session.commit()
            trades = []
            for order in orders:
                trades.append({"price":order.price, "quantity":order.quantity, "buysell":None})
            return {"action":"recent_trade_update", "orders": trades}
            
        else:
            return {"action":"error", "message":"Insuffient funds or commodity"}
            
            

@socketio.on('message')
def handleMessage(msg):
    print(msg)
    send(msg, broadcast=True)

@app.route('/create_account',methods=["GET","POST"])
def create_account():
    if request.method == "POST":
        if not re.match(r"[^@]+@[^@]+\.[^@]+", request.form["email"]):
            return render_template("create_account.html", err = "Not a valid email")
        else:
            print(request.form)
            empty = False
            for x in request.form:
                if request.form[x] == "":
                    empty = True
                    break
            if empty: 
                return render_template("create_account.html", err = "All fields required")
            else:
                if request.form["password"] != request.form["c_password"]:
                    return render_template("create_account.html", err = "Passwords did not match")
                else:
                    user = User.query.filter_by(email=request.form['email']).first()
                    print(user)
                    if user != None:
                        return render_template("create_account.html", err = "Email already in use")
                    else:
                        new_user = User(email = request.form['email'], password = generate_password_hash(request.form['password']))
                        db.session.add(new_user)
                        db.session.commit()
                        login_user(new_user)
                        return redirect(url_for("home"))
    else:
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        else:
            return(render_template("create_account.html"))
        
@app.route("/login", methods=["POST","GET"])
def login():
    if request.method == "POST":
        user = None
        users = User.query.all()
        for x in users:
            if x.email == request.form["email"] and check_password_hash(x.password, request.form["password"]):
                user = x
        if not user:
            return render_template("login.html",err = "Invalid Credentials")
        else:
            login_user(user)
            return redirect(url_for("home"))
    else:
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        else:
            return render_template("login.html")
    
    
@app.route('/home', methods=['GET', 'POST']) 
@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    print(current_user.orders)
    return render_template("home.html",)
    
    
@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == "POST":
        if "delete_account" in request.form:
            db.session.delete(current_user)
            db.session.commit()
            OpenOrders = open_order_fetch()
            socketio.send(OpenOrders, broadcast=True)
            return redirect(url_for("login",))
    else:
        return render_template("account.html",)



@app.route('/rice', methods=['GET', 'POST'])
@login_required
def rice():
    if request.method == "POST":
        recent_trade_update = order_request(request.form)
        if len(recent_trade_update['orders']) > 0:
            socketio.send(recent_trade_update, broadcast=True)
        ##########################################
        #NEED TO KEEP WORKING ON RECENT TRADE UPDATE. GET IT TO UPDATE ON ALL CLIENTS INCLUDING CURRENT TRADER
        ##########################################
        OpenOrders = open_order_fetch()
        socketio.send(OpenOrders, broadcast=True)
        return redirect(url_for("rice"))
        
    else:
        OpenOrders = open_order_fetch()
        buy_orders, sell_orders = OpenOrders["buy"], OpenOrders["sell"]
        return render_template("rice.html",data=OpenOrders, buy_orders=buy_orders, sell_orders=sell_orders)
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
    

db.create_all()
if __name__ == '__main__':
    print("start")
    #app.run(debug=True)
    socketio.run(app, debug=True)
    