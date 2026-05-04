from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
from datetime import datetime, date, timedelta
from functools import wraps

# ─── ML IMPORT ────────────────────────────────────────────────────────────────
from ml_predictor import predict_demand, get_category_summary

app = Flask(__name__)
app.secret_key = 'wmsu_inventory_secret_key_2024'
DATABASE = os.path.join(app.instance_path, 'wmsu_inventory.db')
with app.app_context():
    init_db()
os.makedirs(app.instance_path, exist_ok=True)

# ─── DB HELPERS ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Student',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'General',
                quantity INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Available',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS borrow_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity_requested INTEGER NOT NULL DEFAULT 1,
                date_borrowed TEXT,
                due_date TEXT,
                date_returned TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (item_id) REFERENCES items(item_id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        ''')
        # Seed admin
        admin = db.execute("SELECT id FROM users WHERE email='admin@wmsu.edu.ph'").fetchone()
        if not admin:
            db.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                ('Administrator', 'admin@wmsu.edu.ph', generate_password_hash('admin123'), 'Admin'))
        # Seed staff
        staff = db.execute("SELECT id FROM users WHERE email='staff@wmsu.edu.ph'").fetchone()
        if not staff:
            db.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                ('Staff Member', 'staff@wmsu.edu.ph', generate_password_hash('staff123'), 'Staff'))
        # Seed sample items
        count = db.execute("SELECT COUNT(*) as c FROM items").fetchone()['c']
        if count == 0:
            items = [
                ('Calculus: Early Transcendentals', 'James Stewart, 8th Edition', 'Mathematics', 12),
                ('College Physics', 'Serway & Vuille, 11th Edition — General Physics', 'Science', 10),
                ('Intro to Programming Using Python', 'Daniel Liang — CS Fundamentals', 'Computer Science', 8),
                ('Engineering Mathematics', 'K.A. Stroud, 7th Edition', 'Mathematics', 15),
                ('General Chemistry', 'Petrucci, Herring & Madura, 11th Edition', 'Science', 9),
                ('Data Structures and Algorithms', 'Goodrich & Tamassia — Python Edition', 'Computer Science', 6),
                ('Principles of Economics', 'N. Gregory Mankiw, 8th Edition', 'Social Science', 11),
                ('Human Anatomy & Physiology', 'Marieb & Hoehn, 11th Edition', 'Health Sciences', 7),
                ('Technical Communication', 'Markel & Selber, 13th Edition', 'English', 14),
                ('Philippine History', 'Zaide & Zaide — Survey of Philippine History', 'Social Science', 20),
                ('Discrete Mathematics', 'Kenneth Rosen, 8th Edition', 'Mathematics', 5),
                ('Database Management Systems', 'Ramakrishnan & Gehrke, 3rd Edition', 'Computer Science', 4),
            ]
            for i in items:
                status = 'Available' if i[3] > 5 else ('Low Stock' if i[3] > 0 else 'Out of Stock')
                db.execute("INSERT INTO items (item_name, description, category, quantity, status) VALUES (?,?,?,?,?)",
                    (i[0], i[1], i[2], i[3], status))
        db.commit()

# ─── AUTH DECORATORS ──────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Access denied.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = request.form.get('role', 'Student')
        if role == 'Admin':
            role = 'Student'
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            flash('Email already registered.', 'error')
        else:
            db.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                (name, email, generate_password_hash(password), role))
            db.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    role = session['role']
    stats = {}
    if role == 'Admin':
        stats['total_users'] = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
        stats['total_items'] = db.execute("SELECT COUNT(*) as c FROM items").fetchone()['c']
        stats['pending_requests'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE status='Pending'").fetchone()['c']
        stats['active_borrows'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE status='Approved'").fetchone()['c']
        recent = db.execute("""SELECT br.*, u.name as borrower, i.item_name
            FROM borrow_requests br JOIN users u ON br.user_id=u.id JOIN items i ON br.item_id=i.item_id
            ORDER BY br.created_at DESC LIMIT 5""").fetchall()
        stats['recent'] = recent
    elif role == 'Staff':
        stats['total_items'] = db.execute("SELECT COUNT(*) as c FROM items").fetchone()['c']
        stats['pending_requests'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE status='Pending'").fetchone()['c']
        stats['approved_today'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE status='Approved' AND date(date_borrowed)=date('now')").fetchone()['c']
        stats['low_stock'] = db.execute("SELECT COUNT(*) as c FROM items WHERE status='Low Stock'").fetchone()['c']
        recent = db.execute("""SELECT br.*, u.name as borrower, i.item_name
            FROM borrow_requests br JOIN users u ON br.user_id=u.id JOIN items i ON br.item_id=i.item_id
            WHERE br.status='Pending' ORDER BY br.created_at DESC LIMIT 5""").fetchall()
        stats['recent'] = recent
    else:  # Student
        uid = session['user_id']
        stats['my_borrows'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE user_id=? AND status='Approved'", (uid,)).fetchone()['c']
        stats['pending'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE user_id=? AND status='Pending'", (uid,)).fetchone()['c']
        stats['returned'] = db.execute("SELECT COUNT(*) as c FROM borrow_requests WHERE user_id=? AND status='Returned'", (uid,)).fetchone()['c']
        recent = db.execute("""SELECT br.*, i.item_name FROM borrow_requests br
            JOIN items i ON br.item_id=i.item_id WHERE br.user_id=?
            ORDER BY br.created_at DESC LIMIT 5""", (uid,)).fetchall()
        stats['recent'] = recent
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    return render_template('dashboard.html', stats=stats, notif_count=notifs, today=date.today().isoformat())

# ─── ITEMS ────────────────────────────────────────────────────────────────────

@app.route('/items')
@login_required
def items():
    db = get_db()
    q = request.args.get('q','')
    cat = request.args.get('category','')
    query = "SELECT * FROM items WHERE 1=1"
    params = []
    if q:
        query += " AND (item_name LIKE ? OR description LIKE ?)"
        params += [f'%{q}%', f'%{q}%']
    if cat:
        query += " AND category=?"
        params.append(cat)
    query += " ORDER BY item_name"
    all_items = db.execute(query, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM items ORDER BY category").fetchall()
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    return render_template('items.html', items=all_items, categories=categories, q=q, cat=cat, notif_count=notifs)

@app.route('/items/add', methods=['POST'])
@login_required
@role_required('Staff', 'Admin')
def add_item():
    name = request.form['item_name'].strip()
    desc = request.form.get('description','').strip()
    category = request.form.get('category','General').strip()
    qty = int(request.form.get('quantity', 0))
    status = 'Available' if qty > 5 else ('Low Stock' if qty > 0 else 'Out of Stock')
    db = get_db()
    db.execute("INSERT INTO items (item_name, description, category, quantity, status) VALUES (?,?,?,?,?)",
        (name, desc, category, qty, status))
    db.commit()
    flash('Item added successfully.', 'success')
    return redirect(url_for('items'))

@app.route('/items/edit/<int:item_id>', methods=['POST'])
@login_required
@role_required('Staff', 'Admin')
def edit_item(item_id):
    name = request.form['item_name'].strip()
    desc = request.form.get('description','').strip()
    category = request.form.get('category','General').strip()
    qty = int(request.form.get('quantity', 0))
    status = request.form.get('status','Available')
    db = get_db()
    db.execute("UPDATE items SET item_name=?, description=?, category=?, quantity=?, status=? WHERE item_id=?",
        (name, desc, category, qty, status, item_id))
    db.commit()
    flash('Item updated successfully.', 'success')
    return redirect(url_for('items'))

@app.route('/items/delete/<int:item_id>', methods=['POST'])
@login_required
@role_required('Staff', 'Admin')
def delete_item(item_id):
    db = get_db()
    db.execute("DELETE FROM items WHERE item_id=?", (item_id,))
    db.commit()
    flash('Item deleted.', 'success')
    return redirect(url_for('items'))

@app.route('/api/item/<int:item_id>')
@login_required
def get_item(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
    if item:
        return jsonify(dict(item))
    return jsonify({'error': 'Not found'}), 404

# ─── BORROW REQUESTS ─────────────────────────────────────────────────────────

@app.route('/requests')
@login_required
def borrow_requests():
    db = get_db()
    role = session['role']
    status_filter = request.args.get('status','')
    if role == 'Student':
        query = """SELECT br.*, i.item_name, i.category FROM borrow_requests br
            JOIN items i ON br.item_id=i.item_id WHERE br.user_id=?"""
        params = [session['user_id']]
        if status_filter:
            query += " AND br.status=?"
            params.append(status_filter)
        query += " ORDER BY br.created_at DESC"
        requests_list = db.execute(query, params).fetchall()
    else:
        query = """SELECT br.*, u.name as borrower, u.email, i.item_name, i.category
            FROM borrow_requests br JOIN users u ON br.user_id=u.id JOIN items i ON br.item_id=i.item_id WHERE 1=1"""
        params = []
        if status_filter:
            query += " AND br.status=?"
            params.append(status_filter)
        query += " ORDER BY br.created_at DESC"
        requests_list = db.execute(query, params).fetchall()
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    items_list = db.execute("SELECT * FROM items WHERE status != 'Out of Stock' ORDER BY item_name").fetchall()
    return render_template('requests.html', requests=requests_list, items=items_list, status_filter=status_filter, notif_count=notifs, today=date.today().isoformat())

@app.route('/requests/submit', methods=['POST'])
@login_required
@role_required('Student')
def submit_request():
    item_id = int(request.form['item_id'])
    qty = int(request.form.get('quantity_requested', 1))
    due_date = request.form['due_date']
    notes = request.form.get('notes','').strip()
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
    if not item or item['quantity'] < qty:
        flash('Item not available in requested quantity.', 'error')
        return redirect(url_for('borrow_requests'))
    db.execute("""INSERT INTO borrow_requests (user_id, item_id, quantity_requested, due_date, status, notes)
        VALUES (?,?,?,?,'Pending',?)""", (session['user_id'], item_id, qty, due_date, notes))
    db.commit()
    flash('Borrow request submitted successfully!', 'success')
    return redirect(url_for('borrow_requests'))

@app.route('/requests/approve/<int:req_id>', methods=['POST'])
@login_required
@role_required('Staff', 'Admin')
def approve_request(req_id):
    db = get_db()
    req = db.execute("SELECT * FROM borrow_requests WHERE request_id=?", (req_id,)).fetchone()
    if req and req['status'] == 'Pending':
        item = db.execute("SELECT * FROM items WHERE item_id=?", (req['item_id'],)).fetchone()
        if item['quantity'] >= req['quantity_requested']:
            new_qty = item['quantity'] - req['quantity_requested']
            new_status = 'Available' if new_qty > 5 else ('Low Stock' if new_qty > 0 else 'Out of Stock')
            db.execute("UPDATE items SET quantity=?, status=? WHERE item_id=?", (new_qty, new_status, req['item_id']))
            db.execute("UPDATE borrow_requests SET status='Approved', date_borrowed=? WHERE request_id=?",
                (datetime.now().strftime('%Y-%m-%d'), req_id))
            db.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
                (req['user_id'], f'Your borrow request for {item["item_name"]} has been APPROVED.'))
            db.commit()
            flash('Request approved.', 'success')
        else:
            flash('Insufficient stock.', 'error')
    return redirect(url_for('borrow_requests'))

@app.route('/requests/reject/<int:req_id>', methods=['POST'])
@login_required
@role_required('Staff', 'Admin')
def reject_request(req_id):
    db = get_db()
    req = db.execute("SELECT * FROM borrow_requests WHERE request_id=?", (req_id,)).fetchone()
    if req and req['status'] == 'Pending':
        item = db.execute("SELECT * FROM items WHERE item_id=?", (req['item_id'],)).fetchone()
        db.execute("UPDATE borrow_requests SET status='Rejected' WHERE request_id=?", (req_id,))
        db.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
            (req['user_id'], f'Your borrow request for {item["item_name"]} has been REJECTED.'))
        db.commit()
        flash('Request rejected.', 'success')
    return redirect(url_for('borrow_requests'))

@app.route('/requests/return/<int:req_id>', methods=['POST'])
@login_required
def return_item(req_id):
    db = get_db()
    req = db.execute("SELECT * FROM borrow_requests WHERE request_id=?", (req_id,)).fetchone()
    if req and req['status'] == 'Approved' and (session['role'] in ('Staff','Admin') or req['user_id'] == session['user_id']):
        item = db.execute("SELECT * FROM items WHERE item_id=?", (req['item_id'],)).fetchone()
        new_qty = item['quantity'] + req['quantity_requested']
        new_status = 'Available' if new_qty > 5 else ('Low Stock' if new_qty > 0 else 'Out of Stock')
        db.execute("UPDATE items SET quantity=?, status=? WHERE item_id=?", (new_qty, new_status, req['item_id']))
        db.execute("UPDATE borrow_requests SET status='Returned', date_returned=? WHERE request_id=?",
            (datetime.now().strftime('%Y-%m-%d'), req_id))
        db.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
            (req['user_id'], f'Return of {item["item_name"]} recorded. Thank you!'))
        db.commit()
        flash('Item returned successfully.', 'success')
    return redirect(url_for('borrow_requests'))

# ─── USERS (ADMIN) ────────────────────────────────────────────────────────────

@app.route('/users')
@login_required
@role_required('Admin')
def manage_users():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY role, name").fetchall()
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    return render_template('users.html', users=users, notif_count=notifs)

@app.route('/users/add', methods=['POST'])
@login_required
@role_required('Admin')
def add_user():
    name = request.form['name'].strip()
    email = request.form['email'].strip()
    password = request.form['password']
    role = request.form['role']
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        flash('Email already exists.', 'error')
    else:
        db.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
            (name, email, generate_password_hash(password), role))
        db.commit()
        flash('User added successfully.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def edit_user(user_id):
    name = request.form['name'].strip()
    email = request.form['email'].strip()
    role = request.form['role']
    db = get_db()
    db.execute("UPDATE users SET name=?, email=?, role=? WHERE id=?", (name, email, role, user_id))
    db.commit()
    flash('User updated.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Cannot delete your own account.', 'error')
    else:
        db = get_db()
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
        flash('User deleted.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/api/user/<int:user_id>')
@login_required
@role_required('Admin')
def get_user(user_id):
    db = get_db()
    user = db.execute("SELECT id, name, email, role FROM users WHERE id=?", (user_id,)).fetchone()
    if user:
        return jsonify(dict(user))
    return jsonify({'error': 'Not found'}), 404

# ─── REPORTS (ADMIN) ─────────────────────────────────────────────────────────

@app.route('/reports')
@login_required
@role_required('Admin')
def reports():
    db = get_db()
    most_borrowed = db.execute("""SELECT i.item_name, i.category, COUNT(*) as borrow_count
        FROM borrow_requests br JOIN items i ON br.item_id=i.item_id
        GROUP BY br.item_id ORDER BY borrow_count DESC LIMIT 10""").fetchall()
    active_users = db.execute("""SELECT u.name, u.email, u.role, COUNT(*) as request_count
        FROM borrow_requests br JOIN users u ON br.user_id=u.id
        GROUP BY br.user_id ORDER BY request_count DESC LIMIT 10""").fetchall()
    status_summary = db.execute("""SELECT status, COUNT(*) as count
        FROM borrow_requests GROUP BY status""").fetchall()
    overdue = db.execute("""SELECT br.*, u.name as borrower, i.item_name
        FROM borrow_requests br JOIN users u ON br.user_id=u.id JOIN items i ON br.item_id=i.item_id
        WHERE br.status='Approved' AND br.due_date < date('now')""").fetchall()
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    monthly = db.execute("""SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM borrow_requests GROUP BY month ORDER BY month DESC LIMIT 6""").fetchall()
    return render_template('reports.html', most_borrowed=most_borrowed, active_users=active_users,
        status_summary=status_summary, overdue=overdue, monthly=monthly, notif_count=notifs)

# ─── ML: DEMAND PREDICTION (ADMIN & STAFF) ───────────────────────────────────

@app.route('/predictions')
@login_required
@role_required('Admin', 'Staff')
def predictions():
    """
    Demand Prediction page — gamiton ang ML (Linear Regression)
    para ma-predict ang expected borrow demand sa sunod na bulan.
    """
    preds = predict_demand(DATABASE)
    category_summary = get_category_summary(preds)
    notifs = get_db().execute(
        "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0",
        (session['user_id'],)
    ).fetchone()['c']

    return render_template(
        'prediction.html',
        predictions=preds,
        category_summary=category_summary,
        notif_count=notifs,
        generated_at=datetime.now().strftime('%B %d, %Y %I:%M %p')
    )


@app.route('/api/predictions')
@login_required
@role_required('Admin', 'Staff')
def api_predictions():
    """JSON endpoint — para sa charts or external tools."""
    preds = predict_demand(DATABASE)
    return jsonify(preds)

# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

@app.route('/notifications')
@login_required
def notifications():
    db = get_db()
    db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session['user_id'],))
    db.commit()
    notifs_list = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC", (session['user_id'],)).fetchall()
    return render_template('notifications.html', notifications=notifs_list, notif_count=0)

@app.route('/api/notifications/count')
@login_required
def notif_count():
    db = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    return jsonify({'count': count})

# ─── PROFILE ─────────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    db = get_db()
    if request.method == 'POST':
        name = request.form['name'].strip()
        current_pw = request.form.get('current_password','')
        new_pw = request.form.get('new_password','')
        user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if new_pw:
            if not check_password_hash(user['password'], current_pw):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('profile'))
            db.execute("UPDATE users SET name=?, password=? WHERE id=?",
                (name, generate_password_hash(new_pw), session['user_id']))
        else:
            db.execute("UPDATE users SET name=? WHERE id=?", (name, session['user_id']))
        session['name'] = name
        db.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))
    user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    notifs = db.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()['c']
    return render_template('profile.html', user=user, notif_count=notifs)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)