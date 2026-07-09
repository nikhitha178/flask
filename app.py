from flask import Flask, render_template, request, session, redirect, flash
from flask import Flask, make_response, redirect, request, url_for, render_template, flash, session
import mysql.connector
import config
import bcrypt
import random
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from flask import request, jsonify, render_template
import razorpay
import traceback
from utils.pdf_generator import generate_pdf

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)


app = Flask(__name__)
app.secret_key = config.secret_key

app.config['MAIL_SERVER'] = config.mail_server
app.config['MAIL_PORT'] = config.mail_port
app.config['MAIL_USE_TLS'] = config.mail_use_tls
app.config['MAIL_USERNAME'] = config.mail_username
app.config['MAIL_PASSWORD'] = config.mail_password
mail = Mail(app)


def get_db_connection():
    return mysql.connector.connect(
        host=config.db_host,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name
    )


@app.route('/')
def Home():
    return render_template('index.html')


@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    # Show form
    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    # POST → Process signup
    name = request.form['name']
    email = request.form['email']

    # 1️⃣ Check if admin email already exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    # 2️⃣ Save user input temporarily in session
    session['signup_name'] = name
    session['signup_email'] = email

    # 3️⃣ Generate OTP and store in session
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    # 4️⃣ Send OTP Email
    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.mail_username,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"

    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')


@app.route('/verify-otp', methods=['get'])
def verify_otp_get():
    return render_template("admin/verify_otp.html")


@app.route('/verify-otp', methods=['post'])
def verify_otp_post():
    # user submitted otp & password
    user_otp = request.form['otp']
    password = request.form['password']
    # comparing otp by using bcrypt
    if str(session.get('otp')) != str(user_otp):
        flash("invalid OTP. Try again!!", "danger")
        return redirect('/verify-otp')
    # hashing password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    # insert admin into database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
        (session['signup_name'], session['signup_email'], hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()
    # clearing temporary sessions data
    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)
    flash("Admin Registered Successfully!!", "success")
    return redirect('/admin-signup')

# ADMIN LOGIN PAGE (GET + POST)


@app.route('/admin-login', methods=["GET", "POST"])
def admin_login():

    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    # POST request
    email = request.form.get("email")
    password = request.form.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first", "danger")
        return redirect("/admin-login")

    stored_hashed_password = admin['password'].encode('utf-8')

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')

    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')
# Admin Dashboard -Only logged in admins can access


@app.route("/admin-dashboard")
def admin_dashboard():
    if 'admin_id' not in session:
        flash("please login to access dashboard!!!", "danger")
        return redirect("/admin-login")
    return render_template("admin/dashboard.html", admin_name=session['admin_name'])
# Admin Logout


@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)
    flash("Logged out successfully.", "success")
    return redirect('/admin-login')


UPLOAD_FOLDER = 'static/uploads/product_image'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route('/admin/add-item', methods=['get'])
def add_item_page():
    if 'admin_id' not in session:
        flash("Please Login First!!", "danger")
        return redirect('/admin-login')
    return render_template("admin/add_item.html")


@app.route("/admin/add-item", methods=['post'])
def add_item():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    # validating image upload
    if image_file.filename == "":
        flash("Please upload a Product Image!!!", "danger")
        return redirect('/admin/add-item')
    # securing file name
    filename = secure_filename(image_file.filename)
    # creating full path
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # saving image into folder
    image_file.save(image_path)
    # inserting product
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, category, price, image) VALUES (%s, %s, %s, %s, %s)",
        (name, description, category, price, filename)
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')


@app.route('/admin/item-list')
def show_item_list():
    if 'admin_id' not in session:
        flash("Pleae Login First!!!", "danger")
        return redirect('/admin-login')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/item_list.html", products=products)


@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)

# new


@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    # Check login
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # Fetch product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)


# 12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE


@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get updated form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    # 2️⃣ Fetch old product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    # 3️⃣ If admin uploaded a new image → replace it
    if new_image and new_image.filename != "":

        # Secure filename
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        new_image_path = os.path.join(
            app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)

        # Delete old image file
        old_image_path = os.path.join(
            app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        # No new image uploaded → keep old one
        final_image_name = old_image_name

    # 4️⃣ Update product in the database
    cursor.execute("""
        UPDATE products
        SET name=%s, description=%s, category=%s, price=%s, image=%s
        WHERE product_id=%s
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')


@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # 2️ Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )


@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch product to get image name
    cursor.execute(
        "SELECT image FROM products WHERE product_id=%s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    image_name = product['image']

    # Delete image from folder
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
    if os.path.exists(image_path):
        os.remove(image_path)

    # 2️⃣ Delete product from DB
    cursor.execute("DELETE FROM products WHERE product_id=%s", (item_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')


@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    # 1️⃣ Get form data
    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 2️⃣ Fetch old admin data
    cursor.execute("SELECT * FROM admin WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()

    old_image_name = admin['profile_image']

    # 3️⃣ Update password only if entered
    if new_password:
        hashed_password = bcrypt.hashpw(
            new_password.encode('utf-8'), bcrypt.gensalt())
    else:
        hashed_password = admin['password']  # keep old password

    # 4️⃣ Process new profile image if uploaded
    if new_image and new_image.filename != "":

        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        image_path = os.path.join(
            app.config['ADMIN_UPLOAD_FOLDER'], new_filename)
        new_image.save(image_path)

        # Delete old image
        if old_image_name:
            old_image_path = os.path.join(
                app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)

        final_image_name = new_filename
    else:
        final_image_name = old_image_name

    # 5️⃣ Update database
    cursor.execute("""
        UPDATE admin
        SET name=%s, email=%s, password=%s, profile_image=%s
        WHERE admin_id=%s
    """, (name, email, hashed_password, final_image_name, admin_id))

    conn.commit()
    cursor.close()
    conn.close()

    # Update session name for UI consistency
    session['admin_name'] = name
    session['admin_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')


# ⭐ ROUTE 1: User Registration (GET + POST with OTP Verification)
# ⭐ ROUTE 1: User Registration (GET + POST with OTP Verification)
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    if request.method == 'GET':
        # Combined name update to look for your target template file name
        return render_template("user/user_register.html")

    name = request.form['name']
    email = request.form['email']

    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    existing_user = cursor.fetchone()

    cursor.close()
    conn.close()

    if existing_user:
        flash("Email already registered! Please login.", "danger")
        return redirect('/user-register')

    # 1️⃣ Save inputs temporarily in session + set role tracking flag
    session['signup_name'] = name
    session['signup_email'] = email
    session['signup_role'] = 'user'  # <-- Identifies this as a user signup

    # 2️⃣ Generate OTP and store it in session
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    # 3️⃣ Send OTP Email
    message = Message(
        subject="SmartCart User Registration OTP",
        sender=config.mail_username,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart User Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')
# ⭐ ROUTE 2: User Login(GET + POST)
# ROUTE: USER LOGIN


# ==========================================
# 🟢 1. UNIQUE GET ENDPOINT FOR THE FORM
# ==========================================
@app.route('/user-verify-otp', methods=['GET'])
def user_verify_otp_get():
    return render_template("admin/verify_otp.html")


# ==========================================
# 🟢 2. UNIQUE POST ENDPOINT FOR THE LOGIC
# ==========================================
@app.route('/user-verify-otp', methods=['POST'])
def user_verify_otp_post():
    user_otp = request.form['otp']
    password = request.form['password']

    # Comparing OTP strings safely
    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!!", "danger")
        return redirect('/user-verify-otp')

    # Hashing password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Check what role is currently registering (Defaults to admin if not found)
    role = session.get('signup_role', 'admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    if role == 'user':
        # 👤 INSERT INTO USERS TABLE
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (session['signup_name'], session['signup_email'], hashed_password)
        )
        target_redirect = '/user-login'
        flash_msg = "User Registered Successfully!!"
    else:
        # 👑 INSERT INTO ADMIN TABLE
        cursor.execute(
            "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
            (session['signup_name'], session['signup_email'], hashed_password)
        )
        target_redirect = '/admin-signup'
        flash_msg = "Admin Registered Successfully!!"

    conn.commit()
    cursor.close()
    conn.close()

    # Clearing temporary session workspace data
    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)
    session.pop('signup_role', None)

    flash(flash_msg, "success")
    return redirect(target_redirect)


@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'GET':
        return render_template("user/user_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        flash("Email not found! Please register.", "danger")
        return redirect('/user-login')

    # Verify password
    if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        flash("Incorrect password!", "danger")
        return redirect('/user-login')

    # Create user session
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']

    flash("Login successful!", "success")
    return redirect('/user-dashboard')


# ⭐ ROUTE 3: User Dashboard(Protected)
# ROUTE: USER DASHBOARD


@app.route('/user-dashboard')
def user_dashboard():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    return render_template("user/user_dashboard.html", user_name=session['user_name'])


# ⭐ ROUTE 4: User Logout
# ROUTE: USER LOGOUT


@app.route('/user-logout')
def user_logout():

    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')


@app.route('/user/products')
def user_products():

    # Optional: restrict only logged-in users
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch categories for filter dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # Build dynamic SQL
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )


#  ROUTE: Single Product Details Page
# ROUTE: USER PRODUCT DETAILS PAGE


@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)


@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    # Create cart if doesn't exist
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    # Get product
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer)

    pid = str(product_id)

    # If exists → increase quantity
    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart

    flash("Item added to cart!", "success")
    return redirect('/user/cart')   # instead of this line use below line
    return redirect(request.referrer)   # ⭐ Return to same page


# ⭐ ROUTE 2: View Cart Page
# =================================================================
# VIEW CART PAGE
# =================================================================


@app.route('/user/cart')
def view_cart():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    # Calculate total
    grand_total = sum(item['price'] * item['quantity']
                      for item in cart.values())

    return render_template("user/cart.html", cart=cart, grand_total=grand_total)


# ⭐ ROUTE 3: Increase Quantity
# =================================================================
# INCREASE QUANTITY
# =================================================================


@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    return redirect('/user/cart')


# ⭐ ROUTE 4: Decrease Quantity
# =================================================================
# DECREASE QUANTITY
# =================================================================


@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] -= 1

        # If quantity becomes 0 → remove item
        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)

    session['cart'] = cart
    return redirect('/user/cart')


# ⭐ ROUTE 5: Remove Item Completely
# =================================================================
# REMOVE ITEM
# =================================================================


@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart.pop(pid)

    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')


@app.route('/user/pay', methods=['POST'])
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    # ✅ Get selected items
    selected_items = request.form.getlist('selected_items')

    if not selected_items:
        flash("Please select at least one item!", "danger")
        return redirect('/user/cart')

    # ✅ Calculate only selected items total
    total_amount = 0
    selected_products = {}

    for pid in selected_items:
        item = cart.get(pid)
        if item:
            total_amount += item['price'] * item['quantity']
            selected_products[pid] = item

    razorpay_amount = int(total_amount * 100)

    # ✅ Create Razorpay order
    razorpay_order = razorpay_client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    # ✅ Store session data
    session['razorpay_order_id'] = razorpay_order['id']
    session['selected_products'] = selected_products

    return render_template(
        "user/payment.html",
        amount=total_amount,
        amount_in_paise=razorpay_amount,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id']
    )
# Route: Verify Payment and Store Order
# ------------------------------


@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    if 'user_id' not in session:
        flash("Please login to complete the payment.", "danger")
        return redirect('/user-login')

    # 1. Read values posted from frontend payment_gateway layout template
    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')

    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        flash("Payment verification failed (missing signature data).", "danger")
        return redirect('/user/cart')

    # 2. Build verification payload required by Razorpay utility module
    payload = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        # Raises an explicit SignatureVerificationError if token is fraudulent
        razorpay_client.utility.verify_payment_signature(payload)
    except Exception as e:
        app.logger.error("Razorpay signature verification failed: %s", str(e))
        flash(
            "Payment token verification failed. Fraud protection block applied.", "danger")
        return redirect('/user/cart')

    # 3. Signature Verified — Route data to compile Order Items matrix array
    user_id = session['user_id']
    checkout_type = session.get('checkout_type', 'cart')
    order_items_to_save = []
    total_amount = 0.00

    if checkout_type == 'single' and 'buy_now_item' in session:
        # PATHWAY A: Deconstruct individual item parameters from "Buy Now" structure block
        single_item = session.get('buy_now_item')
        order_items_to_save.append({
            'product_id': single_item['product_id'],
            'name': single_item['name'],
            'quantity': 1,
            'price': single_item['price']
        })
        total_amount = float(single_item['price'])
    else:
        # PATHWAY B: Multi-item structural block pull from traditional cart framework
        cart = session.get('cart', {})
        if not cart:
            flash("Checkout session timeout. Your active item cart is empty.", "danger")
            return redirect('/user/products')

        for pid_str, item in cart.items():
            order_items_to_save.append({
                'product_id': int(pid_str),
                'name': item['name'],
                'quantity': item['quantity'],
                'price': item['price']
            })
            total_amount += float(item['price'] * item['quantity'])

    # 4. Extract Shipping Address records cached during step 1 checkout process
    address_data = session.get('temp_shipping_address', {})

    # 5. Connect and execute write query transactions down to MySQL
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Updated Query containing direct address parameters matrix allocation
        order_query = """
            INSERT INTO orders (
                user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status,
                recipient_name, phone_number, address_line_1, address_line_2, city, state, pin_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        order_values = (
            user_id, razorpay_order_id, razorpay_payment_id, total_amount, 'paid',
            address_data.get('name', 'N/A'),
            address_data.get('phone', 'N/A'),
            address_data.get('addr1', 'N/A'),
            address_data.get('addr2', ''),
            address_data.get('city', 'N/A'),
            address_data.get('state', 'N/A'),
            address_data.get('pincode', 'N/A')
        )

        cursor.execute(order_query, order_values)
        order_db_id = cursor.lastrowid  # Auto-incremented primary key generated by MySQL

        # Insert items tied to this master order primary key ID
        for item in order_items_to_save:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, quantity, price)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_db_id, item['product_id'], item['name'], item['quantity'], item['price']))

        # Complete transactional lock commit
        conn.commit()

        # Clean session memory nodes completely to avoid duplicate processing loops
        session.pop('cart', None)
        session.pop('buy_now_item', None)
        session.pop('checkout_type', None)
        session.pop('temp_shipping_address', None)
        session.pop('razorpay_order_id', None)

        flash("Payment authorized and order entries generated successfully!", "success")
        return redirect(f"/user/order-success/{order_db_id}")

    except Exception as e:
        conn.rollback()
        app.logger.error("MySQL Engine Order Storage Failed structural breakdown: %s\n%s", str(
            e), traceback.format_exc())
        flash("There was a database synchronization error processing your order. Please contact support.", "danger")
        return redirect('/user/cart')
    finally:
        cursor.close()
        conn.close()


@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s",
                   (order_db_id, session['user_id']))
    order = cursor.fetchone()

    cursor.execute(
        "SELECT * FROM order_items WHERE order_id=%s", (order_db_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/products')

    return render_template("user/order_success.html", order=order, items=items)


@app.route('/user/my-orders')
def my_orders():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (session['user_id'],))
    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user/my_orders.html", orders=orders)


@app.route("/user/download-invoice/<int:order_id>")
def download_invoice(order_id):
    # 1. Gatekeeper Authentication Assessment
    if 'user_id' not in session:
        flash("Please log in to authorize resource requests.", "danger")
        return redirect('/user-login')

    # 2. Open MySQL Database Connection Pipeline
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 3. Securely Fetch the Specific Order Meta Record
    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s",
                   (order_id, session['user_id']))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        conn.close()
        flash("Target transactional ledger resource not found.", "danger")
        return redirect('/user/my-orders')

    # 4. Fetch the Associated Item Components Block
    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    # 5. Process Content via the PDF Generator Engine
    html = render_template("user/invoice.html", order=order, items=items)
    pdf = generate_pdf(html)

    if not pdf:
        flash("Invoice compilation pipeline processing failure.", "danger")
        return redirect('/user/my-orders')

    # 6. Stream Binary Action Directly Back to Customer Client
    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers[
        'Content-Disposition'] = f"attachment; filename=SmartCart_Invoice_{order_id}.pdf"

    return response


@app.route('/privacy-policy')
def privacy_policy():
    # Renders the static privacy agreement document panel
    return render_template('privacy.html')


@app.route('/service-status')
def service_status():
    # In production, you could dynamically query system uptime or DB health here.
    # For now, we will pass explicit operational status keys.
    status_metrics = {
        'database_node': 'OPERATIONAL',
        'pdf_engine': 'OPERATIONAL',
        'payment_gateway': 'OPERATIONAL',
        'core_api': 'OPERATIONAL'
    }
    return render_template('node_status.html', metrics=status_metrics)


@app.route('/user/checkout')
def universal_checkout_gateway():
    if 'user_id' not in session:
        flash("Please log in to continue.", "danger")
        return redirect('/user-login')

    product_id = request.args.get('product_id')
    total_amount = 0.00

    if product_id:
        # PATHWAY A: Buy Now processing
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT price FROM products WHERE product_id = %s", (product_id,))
            product = cursor.fetchone()
            if product:
                total_amount = float(product['price'])
                session['checkout_type'] = 'single'
                session['checkout_product_id'] = str(product_id)
            else:
                flash("Product not found.", "danger")
                return redirect('/user/products')
        except Exception as e:
            print("Database Error:", e)
            return redirect('/user/products')
        finally:
            cursor.close()
            conn.close()
    else:
        # PATHWAY B: Cart page processing
        cart = session.get('cart', {})
        if not cart:
            flash("Your cart container is currently empty.", "danger")
            return redirect('/user/products')

        total_amount = sum(
            float(item['price']) * int(item['quantity']) for item in cart.values())
        session['checkout_type'] = 'cart'

    session['checkout_total'] = total_amount
    return render_template('checkout.html', total_amount=total_amount)
# ====================================================================
# 🟢 FIND OR ADD THIS ROUTE IN YOUR ROUTE SECTION BELOW YOUR CONFIGS


@app.route('/user/checkout/process', methods=['POST'])
def process_address_and_launch_payment():
    if 'user_id' not in session:
        return redirect('/user-login')

    # Temporarily bundle address input strings directly into session memory structures
    session['temp_shipping_address'] = {
        'name': request.form.get('full_name'),
        'phone': request.form.get('phone'),
        'addr1': request.form.get('address_1'),
        'addr2': request.form.get('address_2'),
        'city': request.form.get('city'),
        'state': request.form.get('state'),
        'pincode': request.form.get('pin_code')
    }

    # Pull calculations from checkout routing setup
    checkout_type = session.get('checkout_type', 'cart')

    if checkout_type == 'single':
        prod_id = session.get('checkout_product_id')
        # Fetch individual item criteria directly from MySQL
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT name, price FROM products WHERE product_id = %s", (prod_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()

        session['buy_now_item'] = {
            'product_id': prod_id,
            'name': product['name'],
            'price': float(product['price'])
        }
        total_amount = float(product['price'])
    else:
        cart = session.get('cart', {})
        total_amount = sum(item['price'] * item['quantity']
                           for item in cart.values())

    amount_in_paise = int(total_amount * 100)

    # Initialize Razorpay Order Session Registry
    razorpay_order = razorpay_client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"rcpt_user_{session['user_id']}",
        "payment_capture": 1
    })

    return render_template(
        'payment_gateway.html',
        key_id=config.RAZORPAY_KEY_ID,
        amount=total_amount,
        amount_in_paise=amount_in_paise,
        order_id=razorpay_order['id']
    )


if __name__ == '__main__':
    app.run(debug=True)
