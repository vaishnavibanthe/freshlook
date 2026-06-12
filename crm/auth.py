from flask import render_template, request, redirect, session, flash, url_for, g, jsonify
from functools import wraps
import sqlite3
from werkzeug.security import check_password_hash
from crm import crm_bp

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect('blog.db', timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

# Helper to fetch current crm user
def get_current_user():
    user_id = session.get('crm_user_id')
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT u.*, g.name as group_name FROM crm_users u LEFT JOIN crm_groups g ON u.group_id = g.id WHERE u.id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

# Decorator to check if CRM user is logged in
def crm_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'crm_user_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('crm.crm_login'))
        
        # Verify user is active in DB
        user = get_current_user()
        if not user or not user.get('is_active'):
            session.clear()
            flash("Your account is inactive. Please contact an administrator.", "error")
            return redirect(url_for('crm.crm_login'))
        
        g.crm_user = user
        return f(*args, **kwargs)
    return decorated_function

# Decorator for role-based access control
def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'crm_user_id' not in session:
                return redirect(url_for('crm.crm_login'))
            
            user = get_current_user()
            if not user or not user.get('is_active'):
                session.clear()
                return redirect(url_for('crm.crm_login'))
            
            role = user.get('role')
            # 'Platform Admin' has full access overrides
            if role == 'Platform Admin' or role in allowed_roles:
                g.crm_user = user
                return f(*args, **kwargs)
                
            flash("You do not have permission to access this resource.", "error")
            # Redirect to dashboards based on role
            if role == 'Telecaller':
                return redirect(url_for('crm.telecrm_dialing_workbench'))
            elif role in ('Telecaller Manager', 'Group Admin'):
                return redirect(url_for('crm.telecrm_dashboard'))
            else:
                return redirect(url_for('crm.crm_dashboard'))
        return decorated_function
    return decorator

# Inject current user into all template contexts
@crm_bp.app_context_processor
def inject_crm_user():
    user = get_current_user()
    return dict(current_crm_user=user)

# ----------------------------------------------------
# Auth Routes
# ----------------------------------------------------

@crm_bp.route('/crm/login', methods=['GET', 'POST'])
def crm_login():
    if 'crm_user_id' in session:
        # Already logged in, redirect based on role
        role = session.get('crm_user_role')
        if role == 'Telecaller':
            return redirect(url_for('crm.telecrm_dialing_workbench'))
        elif role == 'Telecaller Manager':
            return redirect(url_for('crm.telecrm_dashboard'))
        else:
            return redirect(url_for('crm.crm_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template('login.html')
            
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM crm_users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash("Your account has been deactivated.", "error")
                return render_template('login.html')
                
            # Log session
            session['crm_user_id'] = user['id']
            session['crm_user_role'] = user['role']
            session['crm_user_name'] = user['name']
            session['crm_user_group'] = user['group_id']
            
            flash(f"Welcome back, {user['name']}!", "success")
            
            # Redirect by role
            if user['role'] == 'Telecaller':
                return redirect(url_for('crm.telecrm_dialing_workbench'))
            elif user['role'] == 'Telecaller Manager':
                return redirect(url_for('crm.telecrm_dashboard'))
            else:
                return redirect(url_for('crm.crm_dashboard'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template('login.html')

@crm_bp.route('/crm/logout')
def crm_logout():
    session.pop('crm_user_id', None)
    session.pop('crm_user_role', None)
    session.pop('crm_user_name', None)
    session.pop('crm_user_group', None)
    flash("You have successfully logged out.", "success")
    return redirect(url_for('crm.crm_login'))
