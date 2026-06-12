from flask import render_template, request, redirect, url_for, flash, jsonify, g, session
from datetime import datetime
from werkzeug.security import generate_password_hash
from crm import crm_bp
from crm.auth import crm_login_required, role_required
from crm.models import db_query, db_query_one, db_execute, log_timeline_activity
from crm.utils import encrypt_smtp_password, decrypt_smtp_password

# ----------------------------------------------------
# User Management CRUD
# ----------------------------------------------------
@crm_bp.route('/admin/crm/users', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin')
def admin_users():
    user = g.crm_user
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            group_id = request.form.get('group_id') or None
            manager_id = request.form.get('manager_id') or None
            sales_head_id = request.form.get('sales_head_id') or None
            geography = request.form.get('geography')
            department = request.form.get('department')
            
            if not name or not email or not password or not role:
                flash("Name, email, password and role are mandatory.", "error")
                return redirect(url_for('crm.admin_users'))
                
            # Verify if email exists
            existing = db_query_one("SELECT id FROM crm_users WHERE email = ?", (email,))
            if existing:
                flash("Email already exists.", "error")
                return redirect(url_for('crm.admin_users'))
                
            # If Group Admin, restrict to their group
            if user['role'] == 'Group Admin':
                group_id = user['group_id']
                
            password_hash = generate_password_hash(password)
            db_execute('''
                INSERT INTO crm_users (name, email, password_hash, role, group_id, manager_id, sales_head_id, geography, department, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ''', (name, email, password_hash, role, group_id, manager_id, sales_head_id, geography, department, now_str, now_str))
            
            flash(f"User {name} created successfully.", "success")
            return redirect(url_for('crm.admin_users'))
            
        elif action == 'edit':
            user_id = request.form.get('user_id')
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            group_id = request.form.get('group_id') or None
            manager_id = request.form.get('manager_id') or None
            sales_head_id = request.form.get('sales_head_id') or None
            geography = request.form.get('geography')
            department = request.form.get('department')
            is_active = 1 if request.form.get('is_active') == '1' else 0
            
            # If Group Admin, restrict to their group
            if user['role'] == 'Group Admin':
                # Check user exists in their group
                chk = db_query_one("SELECT id FROM crm_users WHERE id = ? AND group_id = ?", (user_id, user['group_id']))
                if not chk:
                    flash("Access denied.", "error")
                    return redirect(url_for('crm.admin_users'))
                group_id = user['group_id']
                
            # Email validation
            email_chk = db_query_one("SELECT id FROM crm_users WHERE email = ? AND id != ?", (email, user_id))
            if email_chk:
                flash("Email already in use.", "error")
                return redirect(url_for('crm.admin_users'))
                
            if password:
                # Update password
                password_hash = generate_password_hash(password)
                db_execute('''
                    UPDATE crm_users 
                    SET name=?, email=?, password_hash=?, role=?, group_id=?, manager_id=?, sales_head_id=?, geography=?, department=?, is_active=?, updated_at=?
                    WHERE id=?
                ''', (name, email, password_hash, role, group_id, manager_id, sales_head_id, geography, department, is_active, now_str, user_id))
            else:
                db_execute('''
                    UPDATE crm_users 
                    SET name=?, email=?, role=?, group_id=?, manager_id=?, sales_head_id=?, geography=?, department=?, is_active=?, updated_at=?
                    WHERE id=?
                ''', (name, email, role, group_id, manager_id, sales_head_id, geography, department, is_active, now_str, user_id))
                
            flash(f"User {name} updated.", "success")
            return redirect(url_for('crm.admin_users'))
            
        elif action == 'deactivate':
            user_id = request.form.get('user_id')
            if user['role'] == 'Group Admin':
                chk = db_query_one("SELECT id FROM crm_users WHERE id = ? AND group_id = ?", (user_id, user['group_id']))
                if not chk:
                    flash("Access denied.", "error")
                    return redirect(url_for('crm.admin_users'))
                    
            db_execute("UPDATE crm_users SET is_active = 0, updated_at = ? WHERE id = ?", (now_str, user_id))
            flash("User deactivated.", "success")
            return redirect(url_for('crm.admin_users'))
            
    # Read users based on role
    if user['role'] == 'Platform Admin':
        users = db_query("SELECT u.*, g.name as group_name FROM crm_users u LEFT JOIN crm_groups g ON u.group_id = g.id ORDER BY u.id DESC")
        groups = db_query("SELECT * FROM crm_groups")
    else: # Group Admin
        users = db_query("SELECT u.*, g.name as group_name FROM crm_users u LEFT JOIN crm_groups g ON u.group_id = g.id WHERE u.group_id = ? ORDER BY u.id DESC", (user['group_id'],))
        groups = db_query("SELECT * FROM crm_groups WHERE id = ?", (user['group_id'],))
        
    potential_managers = db_query("SELECT id, name FROM crm_users WHERE role IN ('Manager / Sales Manager', 'Sales Head', 'Platform Admin') AND is_active = 1")
    potential_heads = db_query("SELECT id, name FROM crm_users WHERE role IN ('Sales Head', 'Platform Admin') AND is_active = 1")
    
    return render_template(
        'admin/users.html',
        users=users,
        groups=groups,
        managers=potential_managers,
        heads=potential_heads,
        active_page='admin_users'
    )

# ----------------------------------------------------
# Business Groups Management
# ----------------------------------------------------
@crm_bp.route('/admin/crm/groups', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_groups():
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        name = request.form.get('name')
        desc = request.form.get('description')
        admin_id = request.form.get('group_admin_id') or None
        
        if not name:
            flash("Group Name is required.", "error")
            return redirect(url_for('crm.admin_groups'))
            
        if action == 'create':
            db_execute('''
                INSERT INTO crm_groups (name, description, group_admin_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, desc, admin_id, now_str, now_str))
            flash(f"Group {name} created successfully.", "success")
        elif action == 'edit':
            group_id = request.form.get('group_id')
            db_execute('''
                UPDATE crm_groups 
                SET name=?, description=?, group_admin_id=?, updated_at=?
                WHERE id=?
            ''', (name, desc, admin_id, now_str, group_id))
            flash(f"Group {name} updated.", "success")
            
        return redirect(url_for('crm.admin_groups'))
        
    groups = db_query("SELECT g.*, u.name as admin_name FROM crm_groups g LEFT JOIN crm_users u ON g.group_admin_id = u.id")
    potential_admins = db_query("SELECT id, name FROM crm_users WHERE role IN ('Platform Admin', 'Group Admin') AND is_active = 1")
    
    return render_template('admin/groups.html', groups=groups, admins=potential_admins, active_page='admin_groups')

# ----------------------------------------------------
# Products/Solutions and Partners Mapping
# ----------------------------------------------------
@crm_bp.route('/admin/crm/products-partners', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_products_partners():
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_product':
            name = request.form.get('name')
            category = request.form.get('category')
            desc = request.form.get('description')
            
            db_execute('''
                INSERT INTO product_solutions (name, category, description, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
            ''', (name, category, desc, now_str, now_str))
            flash(f"Product {name} added.", "success")
            
        elif action == 'edit_product':
            pid = request.form.get('product_id')
            name = request.form.get('name')
            category = request.form.get('category')
            desc = request.form.get('description')
            active = 1 if request.form.get('is_active') == '1' else 0
            
            db_execute('''
                UPDATE product_solutions 
                SET name=?, category=?, description=?, is_active=?, updated_at=?
                WHERE id=?
            ''', (name, category, desc, active, now_str, pid))
            flash(f"Product {name} updated.", "success")
            
        elif action == 'create_partner':
            name = request.form.get('name')
            ptype = request.form.get('partner_type')
            desc = request.form.get('description')
            
            db_execute('''
                INSERT INTO partners (name, partner_type, description, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
            ''', (name, ptype, desc, now_str, now_str))
            flash(f"Partner {name} added.", "success")
            
        elif action == 'edit_partner':
            part_id = request.form.get('partner_id')
            name = request.form.get('name')
            ptype = request.form.get('partner_type')
            desc = request.form.get('description')
            active = 1 if request.form.get('is_active') == '1' else 0
            
            db_execute('''
                UPDATE partners 
                SET name=?, partner_type=?, description=?, is_active=?, updated_at=?
                WHERE id=?
            ''', (name, ptype, desc, active, now_str, part_id))
            flash(f"Partner {name} updated.", "success")
            
        elif action == 'map_partner':
            pid = request.form.get('product_id')
            part_id = request.form.get('partner_id')
            
            try:
                db_execute('''
                    INSERT INTO product_partner_mappings (product_solution_id, partner_id, is_active, created_at, updated_at)
                    VALUES (?, ?, 1, ?, ?)
                ''', (pid, part_id, now_str, now_str))
                flash("Partner mapping created.", "success")
            except Exception:
                flash("Mapping already exists.", "error")
                
        return redirect(url_for('crm.admin_products_partners'))
        
    products = db_query("SELECT * FROM product_solutions ORDER BY name ASC")
    partners = db_query("SELECT * FROM partners ORDER BY name ASC")
    mappings = db_query('''
        SELECT m.*, ps.name as product_name, p.name as partner_name 
        FROM product_partner_mappings m
        JOIN product_solutions ps ON m.product_solution_id = ps.id
        JOIN partners p ON m.partner_id = p.id
        ORDER BY ps.name ASC
    ''')
    
    return render_template(
        'admin/products_partners.html',
        products=products,
        partners=partners,
        mappings=mappings,
        active_page='admin_products'
    )

# ----------------------------------------------------
# General and SMTP Settings
# ----------------------------------------------------
@crm_bp.route('/admin/crm/settings', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_settings():
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        host = request.form.get('smtp_host')
        port = int(request.form.get('smtp_port') or 587)
        user = request.form.get('smtp_username')
        pwd = request.form.get('smtp_password')
        from_email = request.form.get('from_email')
        default_owner = request.form.get('default_sql_owner_id')
        dup_detect = 1 if request.form.get('duplicate_detection_enabled') == '1' else 0
        careers_capture = 1 if request.form.get('careers_capture_enabled') == '1' else 0
        
        # Keep old password if empty
        settings = db_query_one("SELECT smtp_password_encrypted FROM crm_settings LIMIT 1")
        if pwd:
            pwd_encrypted = encrypt_smtp_password(pwd)
        else:
            pwd_encrypted = settings['smtp_password_encrypted'] if settings else ""
            
        db_execute('''
            UPDATE crm_settings 
            SET smtp_host=?, smtp_port=?, smtp_username=?, smtp_password_encrypted=?, from_email=?, 
                duplicate_detection_enabled=?, careers_capture_enabled=?, default_sql_owner_id=?, updated_at=?
            WHERE id = 1
        ''', (host, port, user, pwd_encrypted, from_email, dup_detect, careers_capture, default_owner, now_str))
        
        flash("System settings updated successfully.", "success")
        return redirect(url_for('crm.admin_settings'))
        
    settings = db_query_one("SELECT * FROM crm_settings WHERE id = 1")
    # Decrypt password for editing (empty if blank)
    smtp_pwd_decrypted = decrypt_smtp_password(settings['smtp_password_encrypted']) if settings else ""
    
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    return render_template(
        'admin/settings.html',
        settings=settings,
        smtp_pwd=smtp_pwd_decrypted,
        owners=owners,
        active_page='admin_settings'
    )


# ----------------------------------------------------
# Custom Fields Administration
# ----------------------------------------------------
@crm_bp.route('/admin/crm/custom-fields', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_custom_fields():
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            entity_type = request.form.get('entity_type')
            field_name = request.form.get('field_name', '').strip().lower().replace(' ', '_')
            field_label = request.form.get('field_label', '').strip()
            field_type = request.form.get('field_type')
            options = request.form.get('options', '').strip()
            is_filterable = 1 if request.form.get('is_filterable') == '1' else 0
            
            # Clean field name to be strictly alphanumeric / snake_case
            field_name = "".join([c for c in field_name if c.isalnum() or c == '_'])
            
            if not entity_type or not field_name or not field_label or not field_type:
                flash("Entity Type, Field Name, Field Label, and Field Type are required.", "error")
                return redirect(url_for('crm.admin_custom_fields'))
                
            # Check unique combination
            existing = db_query_one("SELECT id FROM crm_custom_fields WHERE entity_type = ? AND field_name = ?", (entity_type, field_name))
            if existing:
                flash("A custom field with that name already exists for this entity type.", "error")
                return redirect(url_for('crm.admin_custom_fields'))
                
            db_execute('''
                INSERT INTO crm_custom_fields (entity_type, field_name, field_label, field_type, options, is_filterable, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (entity_type, field_name, field_label, field_type, options, is_filterable, now_str))
            
            flash(f"Custom field '{field_label}' created successfully.", "success")
            return redirect(url_for('crm.admin_custom_fields'))
            
        elif action == 'edit':
            field_id = request.form.get('field_id')
            field_label = request.form.get('field_label', '').strip()
            options = request.form.get('options', '').strip()
            is_filterable = 1 if request.form.get('is_filterable') == '1' else 0
            
            if not field_label:
                flash("Field Label is required.", "error")
                return redirect(url_for('crm.admin_custom_fields'))
                
            db_execute('''
                UPDATE crm_custom_fields 
                SET field_label = ?, options = ?, is_filterable = ?
                WHERE id = ?
            ''', (field_label, options, is_filterable, field_id))
            
            flash("Custom field updated successfully.", "success")
            return redirect(url_for('crm.admin_custom_fields'))
            
        elif action == 'delete':
            field_id = request.form.get('field_id')
            db_execute("DELETE FROM crm_custom_fields WHERE id = ?", (field_id,))
            flash("Custom field deleted successfully.", "success")
            return redirect(url_for('crm.admin_custom_fields'))
            
    custom_fields = db_query("SELECT * FROM crm_custom_fields ORDER BY entity_type ASC, id DESC")
    return render_template('admin/custom_fields.html', custom_fields=custom_fields, active_page='admin_custom_fields')

