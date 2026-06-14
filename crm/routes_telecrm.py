from flask import render_template, request, redirect, url_for, flash, jsonify, g, session, Response
from datetime import datetime, timedelta
import json
import csv
import io
import sqlite3
from crm import crm_bp
from crm.auth import crm_login_required, role_required
from crm.models import db_query, db_query_one, db_execute, log_timeline_activity, get_or_create_account_and_contact

# Helper to check if user has access to a specific telecrm contact
def check_telecrm_contact_access(contact_id):
    user = g.crm_user
    role = user['role']
    
    if role == 'Platform Admin':
        return True
    elif role in ('Group Admin', 'Telecaller Manager'):
        contact = db_query_one("SELECT id FROM telecrm_contacts WHERE id = ? AND group_id = ?", (contact_id, user['group_id']))
        return True if contact else False
    elif role == 'Telecaller':
        contact = db_query_one("SELECT id FROM telecrm_contacts WHERE id = ? AND assigned_telecaller_id = ?", (contact_id, user['id']))
        return True if contact else False
    else:
        return False

# Helper to check SQL duplicates

def check_sql_duplicates(email, phone, company, product_solution_id):
    dup_contacts = []
    dup_accounts = []
    dup_opportunities = []
    
    if email:
        rows = db_query("SELECT id FROM contacts WHERE email = ?", (email,))
        dup_contacts.extend([r['id'] for r in rows])
    if phone:
        rows = db_query("SELECT id FROM contacts WHERE phone = ?", (phone,))
        dup_contacts.extend([r['id'] for r in rows if r['id'] not in dup_contacts])
        
    if company:
        rows = db_query("SELECT id FROM accounts WHERE LOWER(account_name) = ?", (company.lower().strip(),))
        dup_accounts.extend([r['id'] for r in rows])
        
    if dup_accounts:
        placeholder = ','.join(['?'] * len(dup_accounts))
        rows = db_query(f"SELECT id FROM opportunities WHERE account_id IN ({placeholder}) AND status = 'Open'", dup_accounts)
        dup_opportunities.extend([r['id'] for r in rows])
    elif dup_contacts:
        placeholder = ','.join(['?'] * len(dup_contacts))
        rows = db_query(f"SELECT id FROM opportunities WHERE contact_id IN ({placeholder}) AND status = 'Open'", dup_contacts)
        dup_opportunities.extend([r['id'] for r in rows if r['id'] not in dup_opportunities])
        
    return {
        'contact_ids': dup_contacts,
        'account_ids': dup_accounts,
        'opportunity_ids': dup_opportunities,
        'status': 'Duplicate' if (dup_contacts or dup_accounts or dup_opportunities) else 'None'
    }

# Helper to check if user has access to a specific campaign / list

def check_campaign_access(campaign_id):
    user = g.crm_user
    role = user['role']
    if role == 'Platform Admin':
        return True
    elif role in ('Group Admin', 'Telecaller Manager', 'Telecaller'):
        campaign = db_query_one("SELECT id FROM telecrm_lists WHERE id = ? AND group_id = ?", (campaign_id, user['group_id']))
        return True if campaign else False
    return False

# Function to compute and update list/campaign completion stats
def update_campaign_completion_stats(campaign_id):
    contacts = db_query("SELECT id, call_attempt_count, is_finalized, sql_status, dialing_status FROM telecrm_contacts WHERE telecrm_list_id = ?", (campaign_id,))
    if not contacts:
        return
    
    total = len(contacts)
    if total == 0:
        return
        
    attempted = 0
    finalized = 0
    converted = 0
    sqls = 0
    
    for c in contacts:
        # Attempt completion: at least one valid dialing attempt
        if c['call_attempt_count'] > 0:
            attempted += 1
        
        # Final completion: has a final disposition, follow-up, meeting, or SQL/opportunity conversion
        if c['is_finalized'] == 1:
            finalized += 1
            
        # Converted: SQL review approved or Converted to Opportunity
        if c['sql_status'] in ('SQL Approved', 'Converted to Opportunity'):
            sqls += 1
            converted += 1
        elif c['dialing_status'] == 'SQL Marked':
            converted += 1
            
    attempted_pct = round((attempted / total) * 100, 1)
    finalized_pct = round((finalized / total) * 100, 1)
    conversion_pct = round((converted / total) * 100, 1)
    sql_pct = round((sqls / total) * 100, 1)
    
    # overall completion is equivalent to finalized percentage
    db_execute('''
        UPDATE telecrm_lists
        SET overall_completion_percentage = ?,
            attempted_percentage = ?,
            finalized_percentage = ?,
            conversion_percentage = ?,
            sql_percentage = ?,
            completed_count = ?,
            updated_at = ?
        WHERE id = ?
    ''', (finalized_pct, attempted_pct, finalized_pct, conversion_pct, sql_pct, finalized, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), campaign_id))

# Helper to log user daily stat updates
def update_user_daily_stat(user_id, campaign_id, date_str, metric_updates):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    # Check if record exists
    stat = db_query_one('''
        SELECT id FROM telecrm_user_daily_stats
        WHERE user_id = ? AND campaign_id = ? AND stat_date = ?
    ''', (user_id, campaign_id, date_str))
    
    if not stat:
        # Insert initial record
        db_execute('''
            INSERT INTO telecrm_user_daily_stats (user_id, campaign_id, stat_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, campaign_id, date_str, now_str, now_str))
        
    set_clauses = []
    params = []
    for k, v in metric_updates.items():
        if k in ('first_call_at', 'last_call_at'):
            set_clauses.append(f"{k} = ?")
            params.append(v)
        else:
            set_clauses.append(f"{k} = {k} + ?")
            params.append(v)
            
    params.extend([user_id, campaign_id, date_str])
    
    query = f'''
        UPDATE telecrm_user_daily_stats
        SET {', '.join(set_clauses)}, updated_at = ?
        WHERE user_id = ? AND campaign_id = ? AND stat_date = ?
    '''
    params.insert(len(params) - 3, now_str)
    db_execute(query, params)

# Helper to verify LinkedIn/Website format warnings
def get_validation_warnings(email, phone, website, company):
    warnings = []
    if email and ('@' not in email or '.' not in email):
        warnings.append('Invalid email format')
    if phone and not any(c.isdigit() for c in phone):
        warnings.append('Invalid phone format')
    if website and '.' not in website:
        warnings.append('Invalid website format')
        
    # Check duplicate crm matches
    if email:
        core_contact = db_query_one("SELECT id FROM contacts WHERE email = ?", (email,))
        if core_contact:
            warnings.append('Existing CRM contact')
            
    if company:
        core_acct = db_query_one("SELECT id FROM accounts WHERE LOWER(account_name) = ?", (company.lower().strip(),))
        if core_acct:
            warnings.append('Existing CRM account')
            
    if email:
        core_opp = db_query_one("SELECT id FROM opportunities WHERE primary_contact_email = ? AND status = 'Open'", (email,))
        if core_opp:
            warnings.append('Existing opportunity')
            
    return warnings

# ----------------------------------------------------
# TeleCRM Legacy Navigation & Helper Redirects
# ----------------------------------------------------
@crm_bp.route('/telecrm/dialing')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_dialing_workbench():
    user = g.crm_user
    role = user['role']
    if role == 'Platform Admin':
        campaign = db_query_one("SELECT id FROM telecrm_lists ORDER BY id DESC LIMIT 1")
    else:
        campaign = db_query_one("SELECT id FROM telecrm_lists WHERE group_id = ? ORDER BY id DESC LIMIT 1", (user['group_id'],))
    if campaign:
        return redirect(url_for('crm.campaign_dialing_workspace', campaign_id=campaign['id']))
    flash("No campaigns found.", "error")
    return redirect(url_for('crm.telecrm_dashboard'))

@crm_bp.route('/telecrm/import')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_import_page():
    user = g.crm_user
    role = user['role']
    products = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    if role == 'Platform Admin':
        callers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1")
    else:
        callers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1 AND group_id = ?", (user['group_id'],))
    return render_template(
        'telecrm/import.html',
        products=products,
        partners=partners,
        callers=callers,
        active_page='telecrm_import'
    )

@crm_bp.route('/telecrm/contacts/new', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def new_telecrm_contact():
    user = g.crm_user
    role = user['role']
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        alternate_phone = request.form.get('alternate_phone', '').strip()
        job_title = request.form.get('job_title', '').strip()
        geography = request.form.get('geography', '').strip()
        country = request.form.get('country', '').strip()
        industry = request.form.get('industry', '').strip()
        website = request.form.get('website', '').strip()
        linkedin_profile = request.form.get('linkedin_profile', '').strip()
        
        assigned_telecaller_id = request.form.get('assigned_telecaller_id') or None
        if assigned_telecaller_id == '':
            assigned_telecaller_id = None
        else:
            assigned_telecaller_id = int(assigned_telecaller_id) if assigned_telecaller_id else None
            
        product_solution_id = request.form.get('product_solution_id') or None
        if product_solution_id == '':
            product_solution_id = None
        else:
            product_solution_id = int(product_solution_id) if product_solution_id else None
            
        partner_id = request.form.get('partner_id') or None
        if partner_id == '':
            partner_id = None
        else:
            partner_id = int(partner_id) if partner_id else None
            
        if not full_name or not email:
            flash("Name and Email are required.", "error")
            return redirect(url_for('crm.new_telecrm_contact'))
            
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        group_id = user['group_id']
        
        list_row = db_query_one("SELECT id FROM telecrm_lists WHERE name = 'Manually Added Contacts' AND group_id = ?", (group_id,))
        if list_row:
            list_id = list_row['id']
        else:
            list_id = db_execute('''
                INSERT INTO telecrm_lists (name, campaign_name, description, status, group_id, created_at, updated_at)
                VALUES ('Manually Added Contacts', 'Manual', 'Manually added contacts list', 'Active', ?, ?, ?)
            ''', (group_id, now_str, now_str))
            
        contact_id = db_execute('''
            INSERT INTO telecrm_contacts (
                telecrm_list_id, full_name, email, phone, alternate_phone, job_title, geography, country, industry, website, linkedin_profile,
                assigned_telecaller_id, product_solution_id, partner_id, group_id, dialing_status, contact_validation_status, meeting_status, sql_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Not Dialed', 'Not Validated', 'Not Required', 'Not SQL', ?, ?)
        ''', (
            list_id, full_name, email, phone, alternate_phone, job_title, geography, country, industry, website, linkedin_profile,
            assigned_telecaller_id, product_solution_id, partner_id, group_id, now_str, now_str
        ))
        
        total_cnt = db_query_one("SELECT COUNT(*) as cnt FROM telecrm_contacts WHERE telecrm_list_id = ?", (list_id,))['cnt']
        db_execute("UPDATE telecrm_lists SET total_contacts = ?, updated_at = ? WHERE id = ?", (total_cnt, now_str, list_id))
        
        log_timeline_activity('telecrm_contact', contact_id, 'Contact created', 'Contact manually added to TeleCRM list', '', user['id'])
        flash("Contact created successfully.", "success")
        return redirect(url_for('crm.campaign_dialing_workspace', campaign_id=list_id, contact_id=contact_id))
        
    products = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    if role == 'Platform Admin':
        callers = db_query("SELECT id, name FROM crm_users WHERE is_active = 1")
    else:
        callers = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND group_id = ?", (user['group_id'],))
        
    return render_template(
        'telecrm/new.html',
        products=products,
        partners=partners,
        callers=callers,
        active_page='telecrm_workbench'
    )

@crm_bp.route('/telecrm/contacts/<int:contact_id>')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_contact_detail(contact_id):
    if not check_telecrm_contact_access(contact_id):
        flash("Access denied to this contact.", "error")
        return redirect(url_for('crm.telecrm_dashboard'))
        
    contact = db_query_one("SELECT * FROM telecrm_contacts WHERE id = ?", (contact_id,))
    if not contact:
        flash("Contact not found.", "error")
        return redirect(url_for('crm.telecrm_dashboard'))
        
    if request.args.get('ajax') == '1':
        products = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
        partners = db_query("SELECT id, name FROM partners WHERE is_active = 1")
        managers = db_query("SELECT id, name, role FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
        
        timeline = db_query("SELECT t.*, u.name as user_name FROM timeline_activities t LEFT JOIN crm_users u ON t.created_by = u.id WHERE t.telecrm_contact_id = ? ORDER BY t.id DESC", (contact_id,))
        call_logs = db_query("SELECT * FROM telecrm_calls WHERE telecrm_contact_id = ? ORDER BY id DESC", (contact_id,))
        email_logs = db_query("SELECT * FROM telecrm_channel_logs WHERE telecrm_contact_id = ? AND channel = 'Email' ORDER BY id DESC", (contact_id,))
        
        custom_fields = db_query("SELECT * FROM crm_custom_fields WHERE entity_type = 'telecrm_contact'")
        custom_values = db_query("SELECT custom_field_id, field_value FROM crm_custom_field_values WHERE entity_id = ?", (contact_id,))
        custom_values_dict = {val['custom_field_id']: val['field_value'] for val in custom_values}
        
        return render_template(
            'telecrm/contact_detail.html',
            contact=contact,
            products=products,
            partners=partners,
            managers=managers,
            timeline=timeline,
            call_logs=call_logs,
            email_logs=email_logs,
            custom_fields=custom_fields,
            custom_values=custom_values_dict
        )
    else:
        return redirect(url_for('crm.campaign_dialing_workspace', campaign_id=contact['telecrm_list_id'], contact_id=contact_id))

@crm_bp.route('/telecrm/contacts/<int:contact_id>/update-profile', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def update_telecrm_contact_profile(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip()
    email = request.form.get('email', '')
    phone = request.form.get('phone', '')
    alternate_phone = request.form.get('alternate_phone', '')
    linkedin_profile = request.form.get('linkedin_profile', '')
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    product_solution_id = request.form.get('product_solution_id') or None
    partner_id = request.form.get('partner_id') or None
    geography = request.form.get('geography', '')
    country = request.form.get('country', '')
    
    if product_solution_id == '':
        product_solution_id = None
    if partner_id == '':
        partner_id = None
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_contacts
        SET first_name = ?, last_name = ?, full_name = ?, email = ?, phone = ?, alternate_phone = ?,
            linkedin_profile = ?, company = ?, job_title = ?, product_solution_id = ?, partner_id = ?,
            geography = ?, country = ?, updated_at = ?
        WHERE id = ?
    ''', (
        first_name, last_name, full_name, email, phone, alternate_phone,
        linkedin_profile, company, job_title, product_solution_id, partner_id,
        geography, country, now_str, contact_id
    ))
    
    custom_fields = db_query("SELECT * FROM crm_custom_fields WHERE entity_type = 'telecrm_contact'")
    for cf in custom_fields:
        val = request.form.get(f"cf_{cf['field_name']}")
        if val is not None:
            db_execute('''
                INSERT INTO crm_custom_field_values (custom_field_id, entity_id, field_value, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(custom_field_id, entity_id) DO UPDATE SET field_value = excluded.field_value, updated_at = excluded.updated_at
            ''', (cf['id'], contact_id, val, now_str, now_str))
            
    log_timeline_activity('telecrm_contact', contact_id, 'Profile updated', 'Contact profile details updated manually', '', user_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1' or request.is_json or request.accept_mimetypes.accept_json:
        return jsonify({'status': 'success', 'message': 'Profile updated successfully.'})
        
    flash("Profile updated successfully.", "success")
    return redirect(url_for('crm.campaign_dialing_workspace', campaign_id=db_query_one("SELECT telecrm_list_id FROM telecrm_contacts WHERE id = ?", (contact_id,))['telecrm_list_id']))

@crm_bp.route('/telecrm/contacts/<int:contact_id>/send-email', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_send_email(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    to_email = request.form.get('to_email')
    cc = request.form.get('cc', '')
    subject = request.form.get('subject')
    body = request.form.get('body')
    
    if not to_email or not subject or not body:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'status': 'error', 'message': 'Mandatory fields missing.'}), 400
        flash("Recipient, Subject, and Body are mandatory.", "error")
        return redirect(url_for('crm.telecrm_contact_detail', contact_id=contact_id))
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    contact = db_query_one("SELECT telecrm_list_id FROM telecrm_contacts WHERE id = ?", (contact_id,))
    campaign_id = contact['telecrm_list_id']
    
    db_execute('''
        INSERT INTO telecrm_channel_logs (
            telecrm_contact_id, campaign_id, user_id, channel, direction, recipient, subject, body, status, sent_at, created_at
        ) VALUES (?, ?, ?, 'Email', 'Outgoing', ?, ?, ?, 'Sent', ?, ?)
    ''', (contact_id, campaign_id, user_id, to_email, subject, body, now_str, now_str))
    
    update_user_daily_stat(user_id, campaign_id, now_str[:10], {'emails_sent': 1})
    
    log_timeline_activity('telecrm_contact', contact_id, 'Email Sent', f"Subject: {subject}", body[:150], user_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'status': 'success', 'message': 'Email logged and sent.'})
        
    flash("Email sent successfully.", "success")
    return redirect(url_for('crm.campaign_dialing_workspace', campaign_id=campaign_id, contact_id=contact_id))

# ----------------------------------------------------
# TeleCRM Dashboard / Home Redirect
# ----------------------------------------------------
@crm_bp.route('/telecrm')
@crm_bp.route('/telecrm/dashboard')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_dashboard():
    return redirect(url_for('crm.telecrm_campaigns'))

# ----------------------------------------------------
# TeleCRM Campaigns Registry Section
# ----------------------------------------------------
@crm_bp.route('/telecrm/campaigns')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_campaigns():
    user = g.crm_user
    role = user['role']
    
    if role == 'Platform Admin':
        campaigns = db_query('''
            SELECT c.*, 
                   p.name as product_name,
                   part.name as partner_name,
                   u.name as uploader_name
            FROM telecrm_lists c
            LEFT JOIN product_solutions p ON c.product_solution_id = p.id
            LEFT JOIN partners part ON c.partner_id = part.id
            LEFT JOIN crm_users u ON c.uploaded_by = u.id
            ORDER BY c.id DESC
        ''')
    else:
        campaigns = db_query('''
            SELECT c.*, 
                   p.name as product_name,
                   part.name as partner_name,
                   u.name as uploader_name
            FROM telecrm_lists c
            LEFT JOIN product_solutions p ON c.product_solution_id = p.id
            LEFT JOIN partners part ON c.partner_id = part.id
            LEFT JOIN crm_users u ON c.uploaded_by = u.id
            WHERE c.group_id = ?
            ORDER BY c.id DESC
        ''', (user['group_id'],))
        
    return render_template(
        'telecrm/campaigns.html',
        campaigns=campaigns,
        active_page='telecrm_campaigns'
    )

# ----------------------------------------------------
# TeleCRM Campaign Detail & Allocation & Reporting
# ----------------------------------------------------
@crm_bp.route('/telecrm/campaigns/<int:campaign_id>')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_campaign_detail(campaign_id):
    if not check_campaign_access(campaign_id):
        flash("Campaign not found or access denied.", "error")
        return redirect(url_for('crm.telecrm_campaigns'))
        
    user = g.crm_user
    role = user['role']
    group_id = user['group_id']
    
    # Fetch campaign metadata
    campaign = db_query_one('''
        SELECT c.*, 
               p.name as product_name,
               part.name as partner_name,
               u.name as uploader_name,
               cg.name as group_name
        FROM telecrm_lists c
        LEFT JOIN product_solutions p ON c.product_solution_id = p.id
        LEFT JOIN partners part ON c.partner_id = part.id
        LEFT JOIN crm_users u ON c.uploaded_by = u.id
        LEFT JOIN crm_groups cg ON c.group_id = cg.id
        WHERE c.id = ?
    ''', (campaign_id,))
    
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for('crm.telecrm_campaigns'))
        
    # Fetch caller performance allocations in this campaign
    allocations = db_query('''
        SELECT al.*, u.name as telecaller_name
        FROM telecrm_allocation_logs al
        JOIN crm_users u ON al.telecaller_id = u.id
        WHERE al.telecrm_list_id = ?
    ''', (campaign_id,))
    
    # Fetch available callers for this group/all to show in allocations form
    if role == 'Platform Admin':
        callers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1")
    else:
        callers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1 AND group_id = ?", (group_id,))
        
    # Detailed campaign statistics
    stats = db_query_one('''
        SELECT COUNT(*) as total_cnt,
               SUM(CASE WHEN assigned_telecaller_id IS NOT NULL THEN 1 ELSE 0 END) as assigned_cnt,
               SUM(is_finalized) as completed_cnt,
               SUM(call_attempt_count) as total_attempts,
               SUM(connected_call_count) as total_connected,
               SUM(spoken_call_count) as total_spoken,
               SUM(CASE WHEN meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as total_meetings_sched,
               SUM(CASE WHEN sql_status IN ('SQL Approved', 'Converted to Opportunity') THEN 1 ELSE 0 END) as total_sqls
        FROM telecrm_contacts
        WHERE telecrm_list_id = ?
    ''', (campaign_id,))
    
    total = stats['total_cnt'] or 0
    assigned = stats['assigned_cnt'] or 0
    completed = stats['completed_cnt'] or 0
    dialed = stats['total_attempts'] or 0
    spoken = stats['total_spoken'] or 0
    meetings_sched = stats['total_meetings_sched'] or 0
    converted = stats['total_sqls'] or 0
    completion_pct = round((completed / total) * 100, 1) if total > 0 else 0.0
    
    # Outcome breakdown (dispositions) specific to this campaign
    disp_stats = db_query('''
        SELECT last_disposition as label, COUNT(*) as value
        FROM telecrm_contacts
        WHERE telecrm_list_id = ? AND last_disposition IS NOT NULL AND last_disposition != ''
        GROUP BY last_disposition
        ORDER BY value DESC
    ''', (campaign_id,))
    
    # Team performance specific to this campaign
    team_performance = db_query('''
        SELECT u.name,
               COUNT(tc.id) as assigned,
               SUM(tc.call_attempt_count) as dialed,
               SUM(tc.spoken_call_count) as spoken,
               SUM(CASE WHEN tc.meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as scheduled,
               SUM(CASE WHEN tc.sql_status IN ('SQL Approved', 'Converted to Opportunity') THEN 1 ELSE 0 END) as converted,
               SUM(tc.is_finalized) as completed
        FROM crm_users u
        LEFT JOIN telecrm_contacts tc ON tc.assigned_telecaller_id = u.id AND tc.telecrm_list_id = ?
        WHERE u.role = 'Telecaller' AND u.is_active = 1
          AND (u.group_id = ? OR ? = 'Platform Admin')
        GROUP BY u.id
        HAVING assigned > 0
    ''', (campaign_id, group_id, role))
    
    for row in team_performance:
        tot = row['assigned'] or 0
        row['completion_percentage'] = round((row['completed'] / tot * 100), 1) if tot > 0 else 0.0
        
    # Contacts listing with filter support
    search_q = request.args.get('search', '').strip()
    status_f = request.args.get('status', '').strip()
    caller_f = request.args.get('caller_id', '').strip()
    
    where_clauses = ["telecrm_list_id = ?"]
    params = [campaign_id]
    
    if search_q:
        where_clauses.append("(full_name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ?)")
        q_wild = f"%{search_q}%"
        params.extend([q_wild, q_wild, q_wild, q_wild])
    if status_f:
        where_clauses.append("dialing_status = ?")
        params.append(status_f)
    if caller_f:
        where_clauses.append("assigned_telecaller_id = ?")
        params.append(int(caller_f))
        
    # Query contacts
    contacts = db_query(f'''
        SELECT tc.*, u.name as caller_name
        FROM telecrm_contacts tc
        LEFT JOIN crm_users u ON tc.assigned_telecaller_id = u.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY tc.id ASC
        LIMIT 100
    ''', params)
    
    return render_template(
        'telecrm/campaign_detail.html',
        campaign=campaign,
        allocations=allocations,
        callers=callers,
        contacts=contacts,
        assigned=assigned,
        completed=completed,
        dialed=dialed,
        spoken=spoken,
        meetings_sched=meetings_sched,
        converted=converted,
        completion_pct=completion_pct,
        disp_stats=disp_stats,
        team_performance=team_performance,
        search_q=search_q,
        status_f=status_f,
        caller_f=caller_f,
        active_page='telecrm_campaigns'
    )

# ----------------------------------------------------
# TeleCRM Analytics & Performance Reporting Section
# ----------------------------------------------------
@crm_bp.route('/telecrm/analytics')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_analytics():
    user = g.crm_user
    role = user['role']
    group_id = user['group_id']
    
    # Fetch lists for campaign filter
    if role == 'Platform Admin':
        campaign_options = db_query("SELECT id, name, campaign_name FROM telecrm_lists ORDER BY id DESC")
    else:
        campaign_options = db_query("SELECT id, name, campaign_name FROM telecrm_lists WHERE group_id = ? ORDER BY id DESC", (group_id,))
        
    campaign_id = request.args.get('campaign_id', '').strip()
    if campaign_id:
        campaign_id = int(campaign_id)
    else:
        campaign_id = None
        
    # Validate and build filter clauses
    where_clauses = []
    params = []
    
    if role != 'Platform Admin':
        where_clauses.append("group_id = ?")
        params.append(group_id)
    if campaign_id:
        where_clauses.append("telecrm_list_id = ?")
        params.append(campaign_id)
        
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    # Calculate aggregated stats
    stats = db_query_one(f'''
        SELECT COUNT(*) as total_cnt,
               SUM(CASE WHEN assigned_telecaller_id IS NOT NULL THEN 1 ELSE 0 END) as assigned_cnt,
               SUM(is_finalized) as completed_cnt,
               SUM(call_attempt_count) as total_attempts,
               SUM(connected_call_count) as total_connected,
               SUM(spoken_call_count) as total_spoken,
               SUM(CASE WHEN meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as total_meetings_sched,
               SUM(CASE WHEN sql_status IN ('SQL Approved', 'Converted to Opportunity') THEN 1 ELSE 0 END) as total_sqls
        FROM telecrm_contacts
        {where_sql}
    ''', params)
    
    total = stats['total_cnt'] or 0
    assigned = stats['assigned_cnt'] or 0
    completed = stats['completed_cnt'] or 0
    dialed = stats['total_attempts'] or 0
    spoken = stats['total_spoken'] or 0
    meetings_sched = stats['total_meetings_sched'] or 0
    converted = stats['total_sqls'] or 0
    completion_pct = round((completed / assigned) * 100, 1) if assigned > 0 else 0.0
    
    # Team performance aggregations
    team_performance = db_query(f'''
        SELECT u.name,
               COUNT(tc.id) as assigned,
               SUM(tc.call_attempt_count) as dialed,
               SUM(tc.spoken_call_count) as spoken,
               SUM(CASE WHEN tc.meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as scheduled,
               SUM(CASE WHEN tc.sql_status IN ('SQL Approved', 'Converted to Opportunity') THEN 1 ELSE 0 END) as converted,
               SUM(tc.is_finalized) as completed
        FROM crm_users u
        LEFT JOIN telecrm_contacts tc ON tc.assigned_telecaller_id = u.id {f"AND tc.telecrm_list_id = {campaign_id}" if campaign_id else ""}
        WHERE u.role = 'Telecaller' AND u.is_active = 1
          {f"AND u.group_id = {group_id}" if role != 'Platform Admin' else ""}
        GROUP BY u.id
        HAVING assigned > 0
    ''')
    
    for row in team_performance:
        tot = row['assigned'] or 0
        row['completion_percentage'] = round((row['completed'] / tot * 100), 1) if tot > 0 else 0.0
        
    # Call Outcome Breakdown
    where_cl_outcomes = []
    params_outcomes = []
    if role != 'Platform Admin':
        where_cl_outcomes.append("group_id = ?")
        params_outcomes.append(group_id)
    if campaign_id:
        where_cl_outcomes.append("telecrm_list_id = ?")
        params_outcomes.append(campaign_id)
        
    where_outcomes_sql = f"WHERE {' AND '.join(where_cl_outcomes)}" if where_cl_outcomes else ""
    
    disp_stats = db_query(f'''
        SELECT last_disposition as label, COUNT(*) as value
        FROM telecrm_contacts
        {where_outcomes_sql}
        GROUP BY last_disposition
        HAVING label IS NOT NULL AND label != ''
        ORDER BY value DESC
    ''', params_outcomes)
    
    # Individual details for log-in telecaller today's schedules
    followups_today = 0
    if role == 'Telecaller':
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        followups_row = db_query_one('''
            SELECT COUNT(*) as cnt
            FROM telecrm_contacts
            WHERE assigned_telecaller_id = ? AND next_followup_at LIKE ?
        ''', (user['id'], f"{today_str}%"))
        followups_today = followups_row['cnt'] if followups_row else 0
        
    is_caller = (role == 'Telecaller')
    
    # Calculate Lead Source Funnel Data
    funnel_data = db_query(f'''
        SELECT COALESCE(NULLIF(source, ''), 'Direct / Unknown') as label,
               COUNT(*) as total,
               SUM(CASE WHEN connected_call_count > 0 THEN 1 ELSE 0 END) as connected,
               SUM(CASE WHEN spoken_call_count > 0 THEN 1 ELSE 0 END) as spoken,
               SUM(CASE WHEN meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as scheduled,
               SUM(CASE WHEN sql_status IN ('SQL Approved', 'Converted to Opportunity') THEN 1 ELSE 0 END) as sql_conversions
        FROM telecrm_contacts
        {where_sql}
        GROUP BY label
        ORDER BY total DESC
    ''', params)

    for row in funnel_data:
        tot = row['total'] or 1
        row['connected_pct'] = round((row['connected'] / tot) * 100, 1)
        row['spoken_pct'] = round((row['spoken'] / tot) * 100, 1)
        row['scheduled_pct'] = round((row['scheduled'] / tot) * 100, 1)
        row['sql_conversions_pct'] = round((row['sql_conversions'] / tot) * 100, 1)

    # Activity Timeline Logs
    call_where_list = []
    call_params_list = []
    if role != 'Platform Admin':
        call_where_list.append("u.group_id = ?")
        call_params_list.append(group_id)
    if campaign_id:
        call_where_list.append("c.campaign_id = ?")
        call_params_list.append(campaign_id)
    
    call_where_str = f"AND {' AND '.join(call_where_list)}" if call_where_list else ""
    
    daily_calls = db_query(f'''
        SELECT SUBSTR(c.created_at, 1, 10) as stat_date, COUNT(*) as call_count
        FROM telecrm_calls c
        JOIN crm_users u ON c.telecaller_id = u.id
        WHERE 1=1 {call_where_str}
        GROUP BY stat_date
        ORDER BY stat_date DESC
        LIMIT 14
    ''', call_params_list)
    
    log_where_list = []
    log_params_list = []
    if role != 'Platform Admin':
        log_where_list.append("u.group_id = ?")
        log_params_list.append(group_id)
    if campaign_id:
        log_where_list.append("l.campaign_id = ?")
        log_params_list.append(campaign_id)
        
    log_where_str = f"AND {' AND '.join(log_where_list)}" if log_where_list else ""
    
    daily_logs = db_query(f'''
        SELECT SUBSTR(l.created_at, 1, 10) as stat_date,
               SUM(CASE WHEN l.channel = 'SMS' THEN 1 ELSE 0 END) as sms_count,
               SUM(CASE WHEN l.channel = 'Email' THEN 1 ELSE 0 END) as email_count
        FROM telecrm_channel_logs l
        JOIN crm_users u ON l.user_id = u.id
        WHERE 1=1 {log_where_str}
        GROUP BY stat_date
        ORDER BY stat_date DESC
        LIMIT 14
    ''', log_params_list)
    
    activity_dict = {}
    for r in daily_calls:
        dt = r['stat_date']
        activity_dict[dt] = {'date': dt, 'calls': r['call_count'], 'sms': 0, 'emails': 0}
        
    for r in daily_logs:
        dt = r['stat_date']
        if dt not in activity_dict:
            activity_dict[dt] = {'date': dt, 'calls': 0, 'sms': 0, 'emails': 0}
        activity_dict[dt]['sms'] = r['sms_count'] or 0
        activity_dict[dt]['emails'] = r['email_count'] or 0
        
    activity_log = sorted(activity_dict.values(), key=lambda x: x['date'], reverse=True)

    return render_template(
        'telecrm/analytics.html',
        campaign_options=campaign_options,
        campaign_id=campaign_id,
        assigned=assigned,
        completed=completed,
        dialed=dialed,
        spoken=spoken,
        meetings_sched=meetings_sched,
        converted=converted,
        completion_pct=completion_pct,
        team_performance=team_performance,
        disp_stats=disp_stats,
        followups_today=followups_today,
        is_caller=is_caller,
        funnel_data=funnel_data,
        activity_log=activity_log,
        active_page='telecrm_analytics'
    )

# ----------------------------------------------------
# Three-Panel Campaign Execution Workbench
# ----------------------------------------------------
@crm_bp.route('/telecrm/campaigns/<int:campaign_id>/dialing')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def campaign_dialing_workspace(campaign_id):
    if not check_campaign_access(campaign_id):
        flash("Campaign not found or access denied.", "error")
        return redirect(url_for('crm.telecrm_dashboard'))
        
    user = g.crm_user
    
    campaign = db_query_one('''
        SELECT tl.*, ps.name as product_name, p.name as partner_name, u.name as owner_name
        FROM telecrm_lists tl
        LEFT JOIN product_solutions ps ON tl.product_solution_id = ps.id
        LEFT JOIN partners p ON tl.partner_id = p.id
        LEFT JOIN crm_users u ON tl.campaign_owner_id = u.id
        WHERE tl.id = ?
    ''', (campaign_id,))
    
    products = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    dispositions = db_query("SELECT * FROM telecrm_dispositions WHERE is_active = 1 ORDER BY sort_order ASC")
    lost_reasons = db_query("SELECT * FROM telecrm_lost_reasons WHERE is_active = 1 ORDER BY sort_order ASC")
    
    # Load settings for WhatsApp/SMS channels
    settings = db_query_one("SELECT whatsapp_enabled, sms_enabled, integrated_telephony_enabled FROM crm_settings LIMIT 1")
    whatsapp_enabled = settings['whatsapp_enabled'] if settings else 0
    sms_enabled = settings['sms_enabled'] if settings else 0
    telephony_enabled = settings['integrated_telephony_enabled'] if settings else 0
    
    # Load target sales managers for dropdowns
    sales_reps = db_query("SELECT id, name FROM crm_users WHERE role IN ('Manager / Sales Manager', 'Sales Head') AND is_active = 1")
    
    # Load callers list for manager-level filters
    if user['role'] == 'Platform Admin':
        telecallers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1")
    else:
        telecallers = db_query("SELECT id, name FROM crm_users WHERE role = 'Telecaller' AND is_active = 1 AND group_id = ?", (user['group_id'],))
        
    return render_template(
        'telecrm/dialing_workspace.html',
        campaign=campaign,
        products=products,
        partners=partners,
        dispositions=dispositions,
        lost_reasons=lost_reasons,
        sales_reps=sales_reps,
        telecallers=telecallers,
        whatsapp_enabled=whatsapp_enabled,
        sms_enabled=sms_enabled,
        telephony_enabled=telephony_enabled,
        active_page='telecrm_workbench'
    )

# ----------------------------------------------------
# Campaign API endpoints
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/summary')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_campaign_summary(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    # Re-calculate stats
    update_campaign_completion_stats(campaign_id)
    
    campaign = db_query_one('''
        SELECT tl.*, ps.name as product_name, p.name as partner_name, u.name as owner_name
        FROM telecrm_lists tl
        LEFT JOIN product_solutions ps ON tl.product_solution_id = ps.id
        LEFT JOIN partners p ON tl.partner_id = p.id
        LEFT JOIN crm_users u ON tl.campaign_owner_id = u.id
        WHERE tl.id = ?
    ''', (campaign_id,))
    
    # Get assignees with avatars
    assignees = db_query('''
        SELECT u.id, u.name, u.role
        FROM telecrm_allocation_logs al
        JOIN crm_users u ON al.telecaller_id = u.id
        WHERE al.telecrm_list_id = ?
    ''', (campaign_id,))
    
    # Calculate days remaining
    days_remaining = None
    if campaign['end_date']:
        try:
            end_dt = datetime.strptime(campaign['end_date'].split(' ')[0], '%Y-%m-%d')
            delta = end_dt - datetime.utcnow()
            days_remaining = max(0, delta.days)
        except Exception:
            pass
            
    summary_data = {
        'id': campaign['id'],
        'name': campaign['name'],
        'campaign_name': campaign['campaign_name'] or campaign['name'],
        'description': campaign['description'],
        'start_date': campaign['start_date'],
        'end_date': campaign['end_date'],
        'days_remaining': days_remaining,
        'total_contacts': campaign['total_contacts'],
        'assigned_count': campaign['assigned_count'],
        'completed_count': campaign['completed_count'],
        'team_size': len(assignees),
        'product': campaign['product_name'] or 'None',
        'partner': campaign['partner_name'] or 'None',
        'geography': campaign['geography'] or 'All',
        'campaign_owner': campaign['owner_name'] or 'Admin',
        'overall_completion_percentage': campaign['overall_completion_percentage'] or 0.0,
        'attempted_percentage': campaign['attempted_percentage'] or 0.0,
        'finalized_percentage': campaign['finalized_percentage'] or 0.0,
        'conversion_percentage': campaign['conversion_percentage'] or 0.0,
        'sql_percentage': campaign['sql_percentage'] or 0.0,
        'status': campaign['campaign_status'] or 'Active',
        'assignees': assignees
    }
    return jsonify(summary_data)


@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/queue')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_campaign_queue(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    user = g.crm_user
    role = user['role']
    
    # Query parameters
    tab = request.args.get('tab', 'Active') # Active, New, Follow-up, Meeting Scheduled, Converted, Completed, Lost
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status')
    disposition_filter = request.args.get('disposition')
    telecaller_filter = request.args.get('telecaller')
    followup_filter = request.args.get('followup') # today, overdue, future
    interest_filter = request.args.get('interest')
    product_filter = request.args.get('product')
    partner_filter = request.args.get('partner')
    geo_filter = request.args.get('geography')
    sort_by = request.args.get('sort_by', 'priority') # priority, oldest_untouched, recent, followup
    
    params = [campaign_id]
    where_clauses = ["tc.telecrm_list_id = ?"]
    
    # Restrict telecallers to owned contacts
    if role == 'Telecaller':
        where_clauses.append("tc.assigned_telecaller_id = ?")
        params.append(user['id'])
    elif telecaller_filter:
        where_clauses.append("tc.assigned_telecaller_id = ?")
        params.append(telecaller_filter)
        
    # Apply tab partitioning
    if tab == 'New':
        # untouched, no attempts
        where_clauses.append("tc.call_attempt_count = 0 AND tc.is_finalized = 0 AND tc.sql_status = 'Not SQL'")
    elif tab == 'Follow-up':
        where_clauses.append("tc.next_followup_at IS NOT NULL AND tc.is_finalized = 0")
    elif tab == 'Meeting Scheduled':
        where_clauses.append("tc.meeting_status = 'Scheduled'")
    elif tab == 'Converted':
        where_clauses.append("tc.sql_status = 'Converted to Opportunity' OR tc.dialing_status = 'SQL Marked'")
    elif tab == 'Completed':
        where_clauses.append("tc.is_finalized = 1 AND tc.sql_status != 'Converted to Opportunity'")
    elif tab == 'Lost':
        where_clauses.append("tc.lost_reason_id IS NOT NULL OR tc.dialing_status = 'Not Interested' OR tc.dialing_status IN (SELECT name FROM telecrm_dispositions WHERE stage_group = 'Lost')")
    else: # Active tab
        where_clauses.append("tc.call_attempt_count > 0 AND tc.is_finalized = 0 AND tc.sql_status = 'Not SQL'")
        
    # Search
    if search:
        where_clauses.append("(tc.full_name LIKE ? OR tc.company LIKE ? OR tc.phone LIKE ? OR tc.email LIKE ? OR tc.job_title LIKE ?)")
        search_str = f"%{search}%"
        params.extend([search_str, search_str, search_str, search_str, search_str])
        
    # Filters
    if status_filter:
        where_clauses.append("tc.dialing_status = ?")
        params.append(status_filter)
    if disposition_filter:
        where_clauses.append("tc.last_disposition = ?")
        params.append(disposition_filter)
    if interest_filter:
        where_clauses.append("tc.interest_level = ?")
        params.append(interest_filter)
    if product_filter:
        where_clauses.append("tc.product_solution_id = ?")
        params.append(product_filter)
    if partner_filter:
        where_clauses.append("tc.partner_id = ?")
        params.append(partner_filter)
    if geo_filter:
        where_clauses.append("tc.geography = ?")
        params.append(geo_filter)
        
    if followup_filter:
        today_date = datetime.utcnow().strftime('%Y-%m-%d')
        if followup_filter == 'today':
            where_clauses.append("date(tc.next_followup_at) = ?")
            params.append(today_date)
        elif followup_filter == 'overdue':
            where_clauses.append("tc.next_followup_at < ?")
            params.append(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
        elif followup_filter == 'future':
            where_clauses.append("date(tc.next_followup_at) > ?")
            params.append(today_date)
            
    # Ordering sorting
    sort_clause = "tc.id ASC"
    if sort_by == 'priority':
        sort_clause = "CASE tc.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Normal' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END ASC, tc.id ASC"
    elif sort_by == 'oldest_untouched':
        sort_clause = "tc.call_attempt_count ASC, tc.last_call_at ASC, tc.id ASC"
    elif sort_by == 'recent':
        sort_clause = "tc.updated_at DESC, tc.id ASC"
    elif sort_by == 'followup':
        sort_clause = "tc.next_followup_at ASC, tc.id ASC"
        
    query = f'''
        SELECT tc.*, u.name as telecaller_name
        FROM telecrm_contacts tc
        LEFT JOIN crm_users u ON tc.assigned_telecaller_id = u.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {sort_clause}
    '''
    contacts = db_query(query, params)
    
    # Calculate counts for each tab dynamically for responsive counts
    tab_counts = {}
    tabs_to_calc = ['Active', 'New', 'Follow-up', 'Meeting Scheduled', 'Converted', 'Completed', 'Lost']
    
    for t in tabs_to_calc:
        c_params = [campaign_id]
        c_where = ["tc.telecrm_list_id = ?"]
        if role == 'Telecaller':
            c_where.append("tc.assigned_telecaller_id = ?")
            c_params.append(user['id'])
        elif telecaller_filter:
            c_where.append("tc.assigned_telecaller_id = ?")
            c_params.append(telecaller_filter)
            
        if t == 'New':
            c_where.append("tc.call_attempt_count = 0 AND tc.is_finalized = 0 AND tc.sql_status = 'Not SQL'")
        elif t == 'Follow-up':
            c_where.append("tc.next_followup_at IS NOT NULL AND tc.is_finalized = 0")
        elif t == 'Meeting Scheduled':
            c_where.append("tc.meeting_status = 'Scheduled'")
        elif t == 'Converted':
            c_where.append("tc.sql_status = 'Converted to Opportunity' OR tc.dialing_status = 'SQL Marked'")
        elif t == 'Completed':
            c_where.append("tc.is_finalized = 1 AND tc.sql_status != 'Converted to Opportunity'")
        elif t == 'Lost':
            c_where.append("tc.lost_reason_id IS NOT NULL OR tc.dialing_status = 'Not Interested' OR tc.dialing_status IN (SELECT name FROM telecrm_dispositions WHERE stage_group = 'Lost')")
        else:
            c_where.append("tc.call_attempt_count > 0 AND tc.is_finalized = 0 AND tc.sql_status = 'Not SQL'")
            
        count_q = f"SELECT COUNT(*) as cnt FROM telecrm_contacts tc WHERE {' AND '.join(c_where)}"
        tab_counts[t] = db_query_one(count_q, c_params)['cnt']
        
    return jsonify({
        'contacts': contacts,
        'tab_counts': tab_counts
    })


@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/next-contact')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_campaign_next_contact(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    user = g.crm_user
    # Find next contact owned by current caller
    # Skip finalized, duplicates, DNC, SQL converted, lost reasons
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Priority queue:
    # 1. Overdue follow-ups or follow-ups due now
    # 2. Touch untouched leads (call_attempt_count = 0)
    # 3. Rest ordered by priority
    
    # Let's search contacts assigned to caller
    where_clause = "assigned_telecaller_id = ? AND telecrm_list_id = ? AND is_finalized = 0 AND sql_status = 'Not SQL' AND (lost_reason_id IS NULL)"
    params = [user['id'], campaign_id]
    
    # Query all candidates
    contacts = db_query(f"SELECT * FROM telecrm_contacts WHERE {where_clause}", params)
    if not contacts:
        return jsonify({'status': 'empty', 'message': 'No eligible contacts left in your queue.'})
        
    # Sort in memory to correctly balance follow-up time vs untouched logic
    def sort_key(c):
        # 1. Priority scoring
        p_score = {'Urgent': 1, 'High': 2, 'Normal': 3, 'Low': 4}.get(c['priority'], 3)
        
        # 2. Follow-up status
        is_fup = 0
        if c['next_followup_at']:
            if c['next_followup_at'] <= now_str:
                is_fup = -2  # Overdue / due now gets highest precedence
            else:
                is_fup = 2   # Future follow-ups get delayed
        else:
            is_fup = -1 # Untouched / normal queue
            
        # 3. Touch count
        touch_score = 0 if c['call_attempt_count'] == 0 else 1
        
        return (is_fup, touch_score, p_score, c['id'])
        
    sorted_contacts = sorted(contacts, key=sort_key)
    
    # Filters out future follow-ups if they aren't due yet
    next_contact = None
    for c in sorted_contacts:
        if c['next_followup_at'] and c['next_followup_at'] > now_str:
            continue
        next_contact = c
        break
        
    # If all remaining have future follow-up, return the first one as recommendation or wait
    if not next_contact:
        next_contact = sorted_contacts[0]
        
    # Get warning details
    warnings = get_validation_warnings(next_contact['email'], next_contact['phone'], next_contact['website'], next_contact['company'])
    
    # Return details
    return jsonify({
        'status': 'success',
        'contact': next_contact,
        'warnings': warnings
    })

# ----------------------------------------------------
# Contact API Toggles
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/favorite', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_favorite(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    is_fav = 1 if data.get('is_favorite') else 0
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    db_execute("UPDATE telecrm_contacts SET is_favorite = ?, updated_at = ? WHERE id = ?", (is_fav, now_str, contact_id))
    
    log_timeline_activity('telecrm_contact', contact_id, 'Favorite updated', 
                          f"Marked as {'Favorite' if is_fav else 'Not Favorite'}", "", g.crm_user['id'])
                          
    return jsonify({'status': 'success', 'is_favorite': is_fav})


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/priority', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_priority(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    priority = data.get('priority', 'Normal')
    if priority not in ('Low', 'Normal', 'High', 'Urgent'):
        return jsonify({'status': 'error', 'message': 'Invalid priority level.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db_execute("UPDATE telecrm_contacts SET priority = ?, updated_at = ? WHERE id = ?", (priority, now_str, contact_id))
    
    log_timeline_activity('telecrm_contact', contact_id, 'Priority changed', f"Priority updated to {priority}", "", g.crm_user['id'])
    return jsonify({'status': 'success', 'priority': priority})


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/rating', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_rating(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    rating = data.get('rating')
    if rating is not None:
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError()
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Rating must be an integer between 1 and 5.'}), 400
            
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db_execute("UPDATE telecrm_contacts SET lead_quality_rating = ?, updated_at = ? WHERE id = ?", (rating, now_str, contact_id))
    
    log_timeline_activity('telecrm_contact', contact_id, 'Rating updated', f"Lead Quality Rating set to {rating}/5", "", g.crm_user['id'])
    return jsonify({'status': 'success', 'lead_quality_rating': rating})

# ----------------------------------------------------
# Integrated Dialer Actions & Call Tracking
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/start-call', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_start_call(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    direction = data.get('direction', 'Outgoing')
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Fetch campaign list
    contact = db_query_one("SELECT telecrm_list_id FROM telecrm_contacts WHERE id = ?", (contact_id,))
    campaign_id = contact['telecrm_list_id']
    
    # Insert Call record
    call_id = db_execute('''
        INSERT INTO telecrm_calls (
            campaign_id, telecrm_contact_id, telecaller_id, direction, call_status, started_at, created_at
        ) VALUES (?, ?, ?, ?, 'Attempted', ?, ?)
    ''', (campaign_id, contact_id, user_id, direction, now_str, now_str))
    
    # Update first call time if not set on contact
    db_execute('''
        UPDATE telecrm_contacts
        SET first_call_at = COALESCE(first_call_at, ?), last_call_at = ?, updated_at = ?
        WHERE id = ?
    ''', (now_str, now_str, now_str, contact_id))
    
    # Log timeline
    log_timeline_activity('telecrm_contact', contact_id, 'Call attempted', f"Call dialing initiated ({direction})", "", user_id)
    
    # Update daily stats
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    stats_update = {
        'attempted_calls': 1,
        'first_call_at': now_str,
        'last_call_at': now_str
    }
    if direction == 'Outgoing':
        stats_update['outgoing_calls'] = 1
    else:
        stats_update['incoming_calls'] = 1
    update_user_daily_stat(user_id, campaign_id, date_str, stats_update)
    
    return jsonify({'status': 'success', 'call_id': call_id})


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/complete-call', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_complete_call(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    call_id = data.get('call_id')
    ring_sec = int(data.get('ring_duration_seconds', 0))
    talk_sec = int(data.get('talk_duration_seconds', 0))
    call_status = data.get('call_status', 'Connected') # Connected, Missed, Busy etc.
    
    if not call_id:
        return jsonify({'status': 'error', 'message': 'call_id is required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    call = db_query_one("SELECT started_at, campaign_id FROM telecrm_calls WHERE id = ?", (call_id,))
    if not call:
        return jsonify({'status': 'error', 'message': 'Call log not found.'}), 404
        
    start_dt = datetime.strptime(call['started_at'], '%Y-%m-%d %H:%M:%S')
    end_dt = datetime.utcnow()
    total_sec = max(1, int((end_dt - start_dt).total_seconds()))
    
    if talk_sec == 0 and call_status == 'Connected':
        talk_sec = total_sec - ring_sec
        
    db_execute('''
        UPDATE telecrm_calls
        SET ended_at = ?, ring_duration_seconds = ?, talk_duration_seconds = ?, total_duration_seconds = ?, call_status = ?
        WHERE id = ?
    ''', (now_str, ring_sec, talk_sec, total_sec, call_status, call_id))
    
    # Update stats
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    stats_update = {
        'last_call_at': now_str
    }
    
    # Load Campaign limits for min connected seconds
    camp = db_query_one("SELECT minimum_connected_seconds FROM telecrm_lists WHERE id = ?", (call['campaign_id'],))
    min_connected = camp['minimum_connected_seconds'] if camp else 1
    
    is_connected = 0
    if call_status == 'Connected' and talk_sec >= min_connected:
        is_connected = 1
        stats_update['connected_calls'] = 1
        
    if call_status == 'Missed':
        stats_update['missed_calls'] = 1
        
    db_execute('''
        UPDATE telecrm_contacts
        SET connected_call_count = connected_call_count + ?, updated_at = ?
        WHERE id = ?
    ''', (is_connected, now_str, contact_id))
    
    update_user_daily_stat(user_id, call['campaign_id'], date_str, stats_update)
    
    return jsonify({
        'status': 'success',
        'talk_duration_seconds': talk_sec,
        'total_duration_seconds': total_sec,
        'is_connected': is_connected
    })


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/disposition', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_disposition(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    disp_name = data.get('disposition')
    outcome_note = data.get('outcome_note', '')
    lost_reason_id = data.get('lost_reason_id')
    next_followup = data.get('next_followup_date') # YYYY-MM-DD HH:MM:SS
    contact_validated = 1 if data.get('contact_validated') else 0
    
    if not disp_name:
        return jsonify({'status': 'error', 'message': 'disposition is required.'}), 400
        
    # Get disposition details
    disp = db_query_one("SELECT * FROM telecrm_dispositions WHERE name = ?", (disp_name,))
    if not disp:
        return jsonify({'status': 'error', 'message': f"Disposition '{disp_name}' is not configured."}), 400
        
    if disp['requires_lost_reason'] and not lost_reason_id:
        return jsonify({'status': 'error', 'message': 'A lost reason is required for this status.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Load Campaign id
    contact = db_query_one("SELECT telecrm_list_id FROM telecrm_contacts WHERE id = ?", (contact_id,))
    campaign_id = contact['telecrm_list_id']
    
    # Calculate counters based on disposition flags
    counts_attempt = 1 if disp['counts_as_attempted'] else 0
    counts_conn = 1 if disp['counts_as_connected'] else 0
    counts_spoken = 1 if disp['counts_as_spoken'] else 0
    
    validation_status = 'Validated' if contact_validated else 'Not Validated'
    if disp['stage_group'] == 'Lost':
        validation_status = 'Invalid'
        
    # Update contact details
    db_execute('''
        UPDATE telecrm_contacts
        SET dialing_status = ?,
            last_disposition = ?,
            final_disposition = ?,
            contact_validation_status = ?,
            call_attempt_count = call_attempt_count + ?,
            connected_call_count = connected_call_count + ?,
            spoken_call_count = spoken_call_count + ?,
            lost_reason_id = ?,
            is_finalized = ?,
            updated_at = ?
        WHERE id = ?
    ''', (disp['name'], disp['name'], disp['name'] if disp['is_final'] else None,
          validation_status, counts_attempt, counts_conn, counts_spoken,
          lost_reason_id or None, disp['is_final'], now_str, contact_id))
          
    # Bind disposition to the latest call attempt
    latest_call = db_query_one('''
        SELECT id FROM telecrm_calls
        WHERE telecrm_contact_id = ? AND telecaller_id = ?
        ORDER BY id DESC LIMIT 1
    ''', (contact_id, user_id))
    
    if latest_call:
        db_execute('''
            UPDATE telecrm_calls
            SET disposition_id = ?, outcome_note = ?
            WHERE id = ?
        ''', (disp['id'], outcome_note, latest_call['id']))
        
    # Add timeline activity
    log_timeline_activity('telecrm_contact', contact_id, 'Stage changed', 
                          f"Call disposition saved: {disp['name']}", outcome_note, user_id)
                          
    # Handle user daily stats
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    stats_update = {
        'spoken_calls': counts_spoken,
        'contacts_completed': 1 if disp['is_final'] else 0
    }
    update_user_daily_stat(user_id, campaign_id, date_str, stats_update)
    
    # Auto-schedule follow-up task if requested
    if next_followup:
        db_execute('''
            INSERT INTO crm_tasks (
                title, description, task_type, related_entity_type, related_entity_id, telecrm_contact_id,
                assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
            ) VALUES (?, ?, 'Telecalling Follow-up', 'telecrm_contact', ?, ?, ?, ?, ?, ?, 'Medium', 'Open', ?, ?)
        ''', (f"Follow up: {disp['name']}", outcome_note, contact_id, contact_id, user_id, user_id, 
              next_followup.split(' ')[0], next_followup.split(' ')[1] if ' ' in next_followup else '10:00',
              now_str, now_str))
              
        db_execute("UPDATE telecrm_contacts SET next_followup_at = ? WHERE id = ?", (next_followup, contact_id))
        
    update_campaign_completion_stats(campaign_id)
    
    return jsonify({'status': 'success', 'is_final': disp['is_final']})


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/calls')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_calls(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    calls = db_query('''
        SELECT c.*, d.name as disposition_name, u.name as caller_name
        FROM telecrm_calls c
        LEFT JOIN telecrm_dispositions d ON c.disposition_id = d.id
        LEFT JOIN crm_users u ON c.telecaller_id = u.id
        WHERE c.telecrm_contact_id = ?
        ORDER BY c.id DESC
    ''', (contact_id,))
    return jsonify(calls)

# ----------------------------------------------------
# Call Later scheduling
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/call-later', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_call_later(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    followup_date = data.get('followup_date') # YYYY-MM-DD
    followup_time = data.get('followup_time') # HH:MM
    reason = data.get('reason', '')
    note = data.get('note', '')
    
    if not followup_date or not followup_time:
        return jsonify({'status': 'error', 'message': 'Follow-up date and time are required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    fup_dt = f"{followup_date} {followup_time}:00"
    
    # Load Campaign list
    contact = db_query_one("SELECT telecrm_list_id FROM telecrm_contacts WHERE id = ?", (contact_id,))
    campaign_id = contact['telecrm_list_id']
    
    # Update TeleCRM contact
    db_execute('''
        UPDATE telecrm_contacts
        SET dialing_status = 'Call Back Later',
            next_followup_at = ?,
            updated_at = ?
        WHERE id = ?
    ''', (fup_dt, now_str, contact_id))
    
    # Create CRM task
    db_execute('''
        INSERT INTO crm_tasks (
            title, description, task_type, related_entity_type, related_entity_id, telecrm_contact_id,
            assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
        ) VALUES (?, ?, 'Telecalling Follow-up', 'telecrm_contact', ?, ?, ?, ?, ?, ?, 'Medium', 'Open', ?, ?)
    ''', (f"Follow up: {reason}", note, contact_id, contact_id, user_id, user_id, followup_date, followup_time, now_str, now_str))
    
    # Add timeline activity
    log_timeline_activity('telecrm_contact', contact_id, 'Follow-up scheduled', 
                          f"Scheduled call back later for {fup_dt}. Reason: {reason}", note, user_id)
                          
    update_campaign_completion_stats(campaign_id)
    return jsonify({'status': 'success', 'next_followup_at': fup_dt})

# ----------------------------------------------------
# Discovery Meetings Workflow
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/meetings', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_contact_schedule_meeting(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    title = data.get('meeting_title', 'Discovery Meeting')
    start_at = data.get('start_at') # YYYY-MM-DD HH:MM:SS
    end_at = data.get('end_at') # YYYY-MM-DD HH:MM:SS
    timezone = data.get('timezone', 'UTC')
    mode = data.get('meeting_mode', 'Online')
    link = data.get('meeting_link', '')
    attendees = data.get('attendees', []) # List of emails
    sales_rep = data.get('assigned_sales_user_id')
    
    if not start_at or not end_at:
        return jsonify({'status': 'error', 'message': 'Start and End date/time are required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    contact = db_query_one("SELECT telecrm_list_id, email, full_name FROM telecrm_contacts WHERE id = ?", (contact_id,))
    campaign_id = contact['telecrm_list_id']
    
    # Ensure client email is in attendees
    if contact['email'] not in attendees:
        attendees.append(contact['email'])
    attendee_json = json.dumps(attendees)
    
    # Create Meeting
    meeting_id = db_execute('''
        INSERT INTO telecrm_meetings (
            telecrm_contact_id, campaign_id, meeting_title, start_at, end_at, timezone, meeting_mode,
            meeting_link, attendee_json, assigned_sales_user_id, status, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Scheduled', ?, ?, ?)
    ''', (contact_id, campaign_id, title, start_at, end_at, timezone, mode, link, attendee_json, sales_rep or None, user_id, now_str, now_str))
    
    # Create CRM task
    db_execute('''
        INSERT INTO crm_tasks (
            title, description, task_type, related_entity_type, related_entity_id, telecrm_contact_id,
            assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
        ) VALUES (?, ?, 'Client Meeting Discovery', 'telecrm_contact', ?, ?, ?, ?, ?, ?, 'High', 'Open', ?, ?)
    ''', (f"Discovery Meeting: {contact['full_name']}", f"Mode: {mode}. Link: {link}", contact_id, contact_id, 
          sales_rep or user_id, user_id, start_at.split(' ')[0], start_at.split(' ')[1] if ' ' in start_at else '10:00',
          now_str, now_str))
          
    # Update contact details
    db_execute('''
        UPDATE telecrm_contacts
        SET meeting_status = 'Scheduled',
            meeting_scheduled_at = ?,
            discovery_meeting_date = ?,
            dialing_status = 'Meeting Scheduled',
            updated_at = ?
        WHERE id = ?
    ''', (start_at, start_at, now_str, contact_id))
    
    # Add timeline activity
    log_timeline_activity('telecrm_contact', contact_id, 'Meeting scheduled', 
                          f"Discovery Meeting Scheduled: {title} ({start_at})", f"Mode: {mode}. Rep ID: {sales_rep}", user_id)
                          
    # Update daily stats
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    update_user_daily_stat(user_id, campaign_id, date_str, {'meetings_scheduled': 1})
    
    update_campaign_completion_stats(campaign_id)
    return jsonify({'status': 'success', 'meeting_id': meeting_id})


@crm_bp.route('/api/telecrm/meetings/<int:meeting_id>', methods=['PUT'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_edit_meeting(meeting_id):
    data = request.json or {}
    title = data.get('meeting_title')
    start_at = data.get('start_at')
    end_at = data.get('end_at')
    mode = data.get('meeting_mode')
    link = data.get('meeting_link')
    sales_rep = data.get('assigned_sales_user_id')
    
    meeting = db_query_one("SELECT * FROM telecrm_meetings WHERE id = ?", (meeting_id,))
    if not meeting:
        return jsonify({'status': 'error', 'message': 'Meeting not found.'}), 404
        
    if not check_telecrm_contact_access(meeting['telecrm_contact_id']):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    set_clauses = []
    params = []
    
    for k, v in [('meeting_title', title), ('start_at', start_at), ('end_at', end_at), ('meeting_mode', mode), ('meeting_link', link), ('assigned_sales_user_id', sales_rep)]:
        if v is not None:
            set_clauses.append(f"{k} = ?")
            params.append(v)
            
    if not set_clauses:
        return jsonify({'status': 'success', 'message': 'No changes made.'})
        
    query = f"UPDATE telecrm_meetings SET {', '.join(set_clauses)}, updated_at = ? WHERE id = ?"
    params.extend([now_str, meeting_id])
    db_execute(query, params)
    
    # If start_at changed, update contact too
    if start_at:
        db_execute("UPDATE telecrm_contacts SET discovery_meeting_date = ?, meeting_scheduled_at = ? WHERE id = ?", (start_at, start_at, meeting['telecrm_contact_id']))
        
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/meetings/<int:meeting_id>/complete', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_complete_meeting(meeting_id):
    data = request.json or {}
    mom = data.get('mom')
    notes = data.get('notes', '')
    sql_recommendation = 1 if data.get('sql_recommendation') else 0
    prod_id = data.get('product_solution_id')
    partner_id = data.get('partner_id')
    pain = data.get('pain', '')
    
    if not mom:
        return jsonify({'status': 'error', 'message': 'Minutes of Meeting (MOM) are required to complete a meeting.'}), 400
        
    meeting = db_query_one("SELECT * FROM telecrm_meetings WHERE id = ?", (meeting_id,))
    if not meeting:
        return jsonify({'status': 'error', 'message': 'Meeting not found.'}), 404
        
    contact_id = meeting['telecrm_contact_id']
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Update meeting
    db_execute('''
        UPDATE telecrm_meetings
        SET status = 'Completed', mom = ?, next_action = ?, sql_recommendation = ?, updated_at = ?
        WHERE id = ?
    ''', (mom, notes, sql_recommendation, now_str, meeting_id))
    
    # Update contact details
    db_execute('''
        UPDATE telecrm_contacts
        SET meeting_status = 'Completed',
            meeting_completed_at = ?,
            mom = ?,
            notes = ?,
            product_solution_id = COALESCE(?, product_solution_id),
            partner_id = COALESCE(?, partner_id),
            dialing_status = 'Meeting Completed',
            updated_at = ?
        WHERE id = ?
    ''', (now_str, mom, notes, prod_id or None, partner_id or None, now_str, contact_id))
    
    # Log timeline
    log_timeline_activity('telecrm_contact', contact_id, 'Meeting completed', 
                          "Discovery Meeting Completed", f"MOM: {mom}. Pain points: {pain}", user_id)
                          
    # Update daily stats
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    update_user_daily_stat(user_id, meeting['campaign_id'], date_str, {'meetings_completed': 1})
    
    update_campaign_completion_stats(meeting['campaign_id'])
    
    return jsonify({'status': 'success'})


# ----------------------------------------------------
# TeleCRM SQL Staging & Review Section
# ----------------------------------------------------
@crm_bp.route('/telecrm/sql')
@crm_bp.route('/crm/telecrm-sql')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head', 'Telecaller')
def telecrm_sql_staging_list_page():
    return render_template('crm/telecrm_sql/list.html', active_page='telecrm_sql')


@crm_bp.route('/telecrm/sql/<int:sql_id>')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head', 'Telecaller')
def telecrm_sql_detail_page(sql_id):
    return render_template('crm/telecrm_sql/detail.html', active_page='telecrm_sql', sql_id=sql_id)


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/mark-sql', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_mark_sql(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    
    # Fetch Contact Details
    contact = db_query_one("SELECT * FROM telecrm_contacts WHERE id = ?", (contact_id,))
    if not contact:
        return jsonify({'status': 'error', 'message': 'Contact not found.'}), 404
        
    # Gather qualification fields from request or contact
    business_pain = data.get('business_pain', '').strip()
    problem_statement = data.get('problem_statement', '').strip()
    interest_level = data.get('interest_level', '').strip() or contact['interest_level']
    next_action = data.get('next_action', '').strip()
    urgency_level = data.get('urgency_level', 'Medium').strip()
    decision_maker_involved = int(data.get('decision_maker_involved', 0))
    budget_indication = data.get('budget_indication', '').strip()
    timeline_indication = data.get('timeline_indication', '').strip()
    economic_buyer_hint = data.get('economic_buyer_hint', '').strip()
    
    # Check if there is a completed meeting in telecrm_meetings
    meeting_row = db_query_one(
        "SELECT * FROM telecrm_meetings WHERE telecrm_contact_id = ? AND status = 'Completed' ORDER BY id DESC LIMIT 1",
        (contact_id,)
    )
    
    # Run validations
    missing_fields = []
    
    # Contact name exists
    if not contact['full_name'] and not (contact['first_name'] or contact['last_name']):
        missing_fields.append("Contact name exists")
        
    # Phone or email exists
    if not contact['phone'] and not contact['email']:
        missing_fields.append("Phone or email exists")
        
    # Company name exists
    if not contact['company']:
        missing_fields.append("Company name exists")
        
    # Product/Solution is selected
    if not contact['product_solution_id']:
        missing_fields.append("Product/Solution is selected")
        
    # Meeting is completed
    has_meeting = (contact['meeting_status'] == 'Completed' or contact['meeting_completed_at'] is not None or meeting_row is not None)
    if not has_meeting:
        missing_fields.append("Meeting is completed")
        
    # MOM is added
    mom_text = contact['mom'] or (meeting_row['mom'] if meeting_row else '')
    if not mom_text or not mom_text.strip():
        missing_fields.append("MOM is added")
        
    # Business pain/problem captured
    if not business_pain and not problem_statement:
        missing_fields.append("Business pain/problem is captured")
        
    # Interest level Medium or High
    if interest_level not in ('Medium', 'High'):
        missing_fields.append("Interest level is Medium or High")
        
    # Next action is captured
    if not next_action:
        missing_fields.append("Next action is captured")
        
    if missing_fields:
        return jsonify({
            'status': 'error',
            'message': 'Mandatory fields missing for SQL qualification.',
            'missing_fields': missing_fields
        }), 400

    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Check for duplicates using check_sql_duplicates helper
    dup_info = check_sql_duplicates(
        contact['email'], 
        contact['phone'], 
        contact['company'], 
        contact['product_solution_id']
    )
    
    possible_dup_contacts = ",".join(map(str, dup_info['contact_ids']))
    possible_dup_accounts = ",".join(map(str, dup_info['account_ids']))
    possible_dup_opportunities = ",".join(map(str, dup_info['opportunity_ids']))
    duplicate_status = dup_info['status']

    # Get meeting details from contact or meeting row
    meeting_status = contact['meeting_status'] or (meeting_row['status'] if meeting_row else 'Completed')
    meeting_scheduled_at = contact['meeting_scheduled_at'] or (meeting_row['start_at'] if meeting_row else None)
    meeting_completed_at = contact['meeting_completed_at'] or (meeting_row['updated_at'] if meeting_row else now_str)
    meeting_mode = meeting_row['meeting_mode'] if meeting_row else 'Online'
    meeting_link = meeting_row['meeting_link'] if meeting_row else ''
    meeting_attendees = meeting_row['attendee_json'] if meeting_row else ''
    
    # Check if there is an existing staging SQL record for this contact in non-final status
    existing_sql = db_query_one(
        "SELECT id, status FROM telecrm_sql WHERE telecrm_contact_id = ? AND status IN ('New SQL', 'Pending Review', 'More Info Required') ORDER BY id DESC LIMIT 1",
        (contact_id,)
    )
    
    if existing_sql:
        sql_id = existing_sql['id']
        prev_status = existing_sql['status']
        db_execute('''
            UPDATE telecrm_sql
            SET contact_name = ?, first_name = ?, last_name = ?, email = ?, phone = ?, alternate_phone = ?,
                company = ?, website = ?, domain = ?, job_title = ?, geography = ?, country = ?, industry = ?,
                product_solution_id = ?, partner_id = ?, partner_influence_type = ?,
                meeting_status = ?, meeting_scheduled_at = ?, meeting_completed_at = ?, meeting_mode = ?, meeting_link = ?, meeting_attendees = ?,
                mom = ?, business_pain = ?, problem_statement = ?, urgency_level = ?, interest_level = ?, lead_quality_rating = ?,
                decision_maker_involved = ?, economic_buyer_hint = ?, budget_indication = ?, timeline_indication = ?, next_action = ?,
                recommended_owner_id = ?, status = 'New SQL', duplicate_status = ?,
                possible_duplicate_contact_ids = ?, possible_duplicate_account_ids = ?, possible_duplicate_opportunity_ids = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            contact['full_name'] or f"{contact['first_name'] or ''} {contact['last_name'] or ''}".strip(), contact['first_name'], contact['last_name'],
            contact['email'], contact['phone'], contact['alternate_phone'] or contact['phone'], contact['company'], contact['website'],
            contact['website'].replace('http://', '').replace('https://', '').split('/')[0] if contact['website'] else '',
            contact['job_title'], contact['geography'], contact['country'], contact['industry'], contact['product_solution_id'],
            contact['partner_id'], 'None', meeting_status, meeting_scheduled_at, meeting_completed_at, meeting_mode, meeting_link, meeting_attendees,
            mom_text, business_pain, problem_statement, urgency_level, interest_level, contact['lead_quality_rating'] or 3,
            decision_maker_involved, economic_buyer_hint, budget_indication, timeline_indication, next_action,
            contact['assigned_manager_id'] or user_id, duplicate_status, possible_dup_contacts, possible_dup_accounts, possible_dup_opportunities,
            now_str, sql_id
        ))
        
        # Log update review log
        db_execute('''
            INSERT INTO telecrm_sql_review_logs (
                telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
            ) VALUES (?, 'Updated by telecaller', 'SQL record details updated and resubmitted by telecaller', ?, 'New SQL', ?, ?)
        ''', (sql_id, prev_status, user_id, now_str))
    else:
        sql_id = db_execute('''
            INSERT INTO telecrm_sql (
                telecrm_contact_id, telecrm_campaign_id, telecrm_list_id, telecaller_id, telecaller_manager_id,
                contact_name, first_name, last_name, email, phone, alternate_phone, company, website, domain, job_title,
                geography, country, industry, product_solution_id, partner_id, partner_influence_type,
                meeting_status, meeting_scheduled_at, meeting_completed_at, meeting_mode, meeting_link, meeting_attendees,
                mom, business_pain, problem_statement, urgency_level, interest_level, lead_quality_rating,
                decision_maker_involved, economic_buyer_hint, budget_indication, timeline_indication, next_action,
                recommended_owner_id, status, duplicate_status, possible_duplicate_contact_ids, possible_duplicate_account_ids, possible_duplicate_opportunity_ids,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New SQL', ?, ?, ?, ?, ?, ?)
        ''', (
            contact_id, contact['telecrm_list_id'], contact['telecrm_list_id'], contact['assigned_telecaller_id'], contact['assigned_manager_id'],
            contact['full_name'] or f"{contact['first_name'] or ''} {contact['last_name'] or ''}".strip(), contact['first_name'], contact['last_name'],
            contact['email'], contact['phone'], contact['alternate_phone'] or contact['phone'], contact['company'], contact['website'],
            contact['website'].replace('http://', '').replace('https://', '').split('/')[0] if contact['website'] else '',
            contact['job_title'], contact['geography'], contact['country'], contact['industry'], contact['product_solution_id'],
            contact['partner_id'], 'None', meeting_status, meeting_scheduled_at, meeting_completed_at, meeting_mode, meeting_link, meeting_attendees,
            mom_text, business_pain, problem_statement, urgency_level, interest_level, contact['lead_quality_rating'] or 3,
            decision_maker_involved, economic_buyer_hint, budget_indication, timeline_indication, next_action,
            contact['assigned_manager_id'] or user_id, duplicate_status, possible_dup_contacts, possible_dup_accounts, possible_dup_opportunities,
            now_str, now_str
        ))
        
        # Log creation review log
        db_execute('''
            INSERT INTO telecrm_sql_review_logs (
                telecrm_sql_id, action_type, description, new_status, performed_by, created_at
            ) VALUES (?, 'SQL created', 'SQL record generated from dialing workspace', 'New SQL', ?, ?)
        ''', (sql_id, user_id, now_str))
        
    # Update Contact Status
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Marked',
            dialing_status = 'SQL Marked',
            sql_record_id = ?,
            sql_marked_at = ?,
            sql_marked_by = ?,
            updated_at = ?
        WHERE id = ?
    ''', (sql_id, now_str, user_id, now_str, contact_id))
    
    # Log activity
    log_timeline_activity('telecrm_contact', contact_id, 'SQL marked', 
                           f"Contact marked as SQL by caller. Staging Record ID: {sql_id}", 
                           f"Pain points: {business_pain}. Next Action: {next_action}", user_id)
    
    # If duplicate found, log it in review logs as well
    if duplicate_status == 'Duplicate':
        db_execute('''
            INSERT INTO telecrm_sql_review_logs (
                telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
            ) VALUES (?, 'Duplicate detected', ?, 'New SQL', 'New SQL', ?, ?)
        ''', (sql_id, f"Possible duplicates found. Contacts: {possible_dup_contacts}, Accounts: {possible_dup_accounts}", user_id, now_str))
        
    update_campaign_completion_stats(contact['telecrm_list_id'])
    
    return jsonify({'status': 'success', 'sql_id': sql_id})


@crm_bp.route('/api/telecrm/sql', methods=['GET'])
@crm_login_required
def api_get_telecrm_sqls():
    user = g.crm_user
    role = user['role']
    
    where_clauses = []
    params = []
    
    if role == 'Telecaller':
        where_clauses.append("telecaller_id = ?")
        params.append(user['id'])
    elif role in ('Group Admin', 'Telecaller Manager'):
        where_clauses.append("telecaller_manager_id = ? OR telecaller_id = ?")
        params.extend([user['id'], user['id']])
        
    # Gather other query parameters for search/filtering
    status = request.args.get('status', '').strip()
    campaign_id = request.args.get('campaign_id', '').strip()
    telecaller_id = request.args.get('telecaller_id', '').strip()
    product_solution_id = request.args.get('product_solution_id', '').strip()
    partner_id = request.args.get('partner_id', '').strip()
    industry = request.args.get('industry', '').strip()
    geography = request.args.get('geography', '').strip()
    lead_quality_rating = request.args.get('lead_quality_rating', '').strip()
    interest_level = request.args.get('interest_level', '').strip()
    meeting_completed_date = request.args.get('meeting_completed_date', '').strip()
    duplicate_status = request.args.get('duplicate_status', '').strip()
    assigned_owner_id = request.args.get('assigned_owner_id', '').strip()
    unassigned = request.args.get('unassigned', '').strip()
    
    # Build filter clauses dynamically
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if campaign_id:
        where_clauses.append("telecrm_campaign_id = ?")
        params.append(int(campaign_id))
    if telecaller_id:
        where_clauses.append("telecaller_id = ?")
        params.append(int(telecaller_id))
    if product_solution_id:
        where_clauses.append("product_solution_id = ?")
        params.append(int(product_solution_id))
    if partner_id:
        where_clauses.append("partner_id = ?")
        params.append(int(partner_id))
    if industry:
        where_clauses.append("industry = ?")
        params.append(industry)
    if geography:
        where_clauses.append("geography = ?")
        params.append(geography)
    if lead_quality_rating:
        where_clauses.append("lead_quality_rating = ?")
        params.append(int(lead_quality_rating))
    if interest_level:
        where_clauses.append("interest_level = ?")
        params.append(interest_level)
    if meeting_completed_date:
        where_clauses.append("DATE(meeting_completed_at) = ?")
        params.append(meeting_completed_date)
    if duplicate_status:
        where_clauses.append("duplicate_status = ?")
        params.append(duplicate_status)
    if assigned_owner_id:
        where_clauses.append("assigned_owner_id = ?")
        params.append(int(assigned_owner_id))
    if unassigned == 'true' or unassigned == '1':
        where_clauses.append("assigned_owner_id IS NULL")
        
    # Search
    search = request.args.get('search', '').strip()
    if search:
        search_clause = '''(
            contact_name LIKE ? OR
            email LIKE ? OR
            phone LIKE ? OR
            company LIKE ? OR
            domain LIKE ? OR
            job_title LIKE ?
        )'''
        where_clauses.append(search_clause)
        search_param = f"%{search}%"
        params.extend([search_param] * 6)
        
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    query = f'''
        SELECT s.*, 
               u.name as telecaller_name,
               ps.name as product_name,
               p.name as partner_name,
               c.name as campaign_name
        FROM telecrm_sql s
        LEFT JOIN crm_users u ON s.telecaller_id = u.id
        LEFT JOIN product_solutions ps ON s.product_solution_id = ps.id
        LEFT JOIN partners p ON s.partner_id = p.id
        LEFT JOIN telecrm_lists c ON s.telecrm_campaign_id = c.id
        {where_sql}
        ORDER BY s.id DESC
    '''
    rows = db_query(query, params)
    return jsonify(rows)


@crm_bp.route('/api/telecrm/sql/analytics', methods=['GET'])
@crm_login_required
def api_telecrm_sql_analytics():
    from crm.api import get_date_range_bounds
    
    date_filter = request.args.get('date_filter', 'This Month').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    
    start_dt, end_dt = get_date_range_bounds(date_filter, start_date, end_date)
    
    user = g.crm_user
    role = user['role']
    
    role_clause = ""
    role_params = []
    if role == 'Telecaller':
        role_clause = "AND telecaller_id = ?"
        role_params = [user['id']]
    elif role in ('Group Admin', 'Telecaller Manager'):
        role_clause = "AND (telecaller_manager_id = ? OR telecaller_id = ?)"
        role_params = [user['id'], user['id']]

    def get_count(status_list, date_col):
        where_clauses = []
        params = []
        
        if status_list:
            placeholders = ','.join(['?'] * len(status_list))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend(status_list)
            
        if role_clause:
            where_clauses.append(role_clause.replace("AND ", ""))
            params.extend(role_params)
            
        if start_dt and end_dt:
            where_clauses.append(f"{date_col} BETWEEN ? AND ?")
            params.extend([start_dt.strftime('%Y-%m-%d %H:%M:%S'), end_dt.strftime('%Y-%m-%d %H:%M:%S')])
            
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT COUNT(*) as cnt FROM telecrm_sql {where_sql}"
        res = db_query_one(query, params)
        return res['cnt'] if res else 0

    total_sqls = get_count([], 'created_at')
    pending = get_count(['New SQL', 'Pending Review', 'More Info Required'], 'created_at')
    approved = get_count(['Approved for CRM'], 'reviewed_at')
    converted = get_count(['Converted to CRM'], 'converted_at')
    rejected = get_count(['Rejected'], 'rejected_at')
    duplicate = get_count(['Duplicate'], 'duplicate_marked_at')
    
    conv_rate = 0.0
    if total_sqls > 0:
        conv_rate = round((converted / total_sqls) * 100, 1)
        
    return jsonify({
        'total_sqls': total_sqls,
        'pending_review': pending,
        'approved_for_crm': approved,
        'converted_to_crm': converted,
        'rejected': rejected,
        'duplicate': duplicate,
        'conversion_rate': conv_rate
    })


@crm_bp.route('/api/telecrm/sql/<int:sql_id>', methods=['GET'])
@crm_login_required
def api_telecrm_sql_detail(sql_id):
    sql_rec = db_query_one('''
        SELECT s.*, 
               u.name as telecaller_name,
               ps.name as product_name,
               p.name as partner_name,
               c.name as campaign_name,
               r.name as reviewer_name,
               o.name as recommended_owner_name,
               ao.name as assigned_owner_name
        FROM telecrm_sql s
        LEFT JOIN crm_users u ON s.telecaller_id = u.id
        LEFT JOIN product_solutions ps ON s.product_solution_id = ps.id
        LEFT JOIN partners p ON s.partner_id = p.id
        LEFT JOIN telecrm_lists c ON s.telecrm_campaign_id = c.id
        LEFT JOIN crm_users r ON s.reviewed_by = r.id
        LEFT JOIN crm_users o ON s.recommended_owner_id = o.id
        LEFT JOIN crm_users ao ON s.assigned_owner_id = ao.id
        WHERE s.id = ?
    ''', (sql_id,))
    
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    user = g.crm_user
    if user['role'] == 'Telecaller' and sql_rec['telecaller_id'] != user['id']:
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    # Get review logs
    logs = db_query('''
        SELECT l.*, u.name as performed_by_name
        FROM telecrm_sql_review_logs l
        LEFT JOIN crm_users u ON l.performed_by = u.id
        WHERE l.telecrm_sql_id = ?
        ORDER BY l.created_at DESC
    ''', (sql_id,))
    
    # Get duplicates checks detail
    possible_contacts = []
    possible_accounts = []
    possible_opportunities = []
    
    if sql_rec['possible_duplicate_contact_ids']:
        ids = [int(x) for x in sql_rec['possible_duplicate_contact_ids'].split(',') if x.strip().isdigit()]
        if ids:
            placeholders = ','.join(['?'] * len(ids))
            possible_contacts = db_query(f'''
                SELECT c.id, c.full_name, c.email, c.phone, c.job_title, a.account_name as company_name
                FROM contacts c
                LEFT JOIN accounts a ON c.account_id = a.id
                WHERE c.id IN ({placeholders})
            ''', ids)
            
    if sql_rec['possible_duplicate_account_ids']:
        ids = [int(x) for x in sql_rec['possible_duplicate_account_ids'].split(',') if x.strip().isdigit()]
        if ids:
            placeholders = ','.join(['?'] * len(ids))
            possible_accounts = db_query(f'''
                SELECT a.id, a.account_name, a.website, a.industry, a.geography, u.name as owner_name
                FROM accounts a
                LEFT JOIN crm_users u ON a.owner_id = u.id
                WHERE a.id IN ({placeholders})
            ''', ids)
            
    if sql_rec['possible_duplicate_opportunity_ids']:
        ids = [int(x) for x in sql_rec['possible_duplicate_opportunity_ids'].split(',') if x.strip().isdigit()]
        if ids:
            placeholders = ','.join(['?'] * len(ids))
            possible_opportunities = db_query(f'''
                SELECT o.id, o.opportunity_name, o.company, o.stage, o.status, u.name as owner_name, o.estimated_value
                FROM opportunities o
                LEFT JOIN crm_users u ON o.owner_id = u.id
                WHERE o.id IN ({placeholders})
            ''', ids)
            
    # Include default rejection reasons
    rejection_reasons = db_query("SELECT * FROM telecrm_sql_rejection_reasons WHERE is_active = 1 ORDER BY sort_order ASC")
    
    # Active CRM Users for owner assignment
    active_users = db_query("SELECT id, name, role FROM crm_users WHERE is_active = 1 ORDER BY name ASC")
    
    return jsonify({
        'sql': sql_rec,
        'logs': logs,
        'duplicates': {
            'contacts': possible_contacts,
            'accounts': possible_accounts,
            'opportunities': possible_opportunities
        },
        'rejection_reasons': rejection_reasons,
        'active_users': active_users
    })


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/approve', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_approve_sql_staging(sql_id):
    data = request.json or {}
    notes = data.get('notes', '').strip()
    
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL staging record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_sql
        SET status = 'Approved for CRM',
            reviewed_by = ?,
            reviewed_at = ?,
            review_notes = ?
        WHERE id = ?
    ''', (user_id, now_str, notes, sql_id))
    
    # Update Contact Status
    db_execute("UPDATE telecrm_contacts SET sql_status = 'Approved for CRM', updated_at = ? WHERE id = ?", (now_str, sql_rec['telecrm_contact_id']))
    
    # Log review log
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
        ) VALUES (?, 'Approved for CRM', ?, ?, 'Approved for CRM', ?, ?)
    ''', (sql_id, f"SQL approved for CRM by reviewer. Notes: {notes}", sql_rec['status'], user_id, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/move-to-crm', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_move_sql_to_crm(sql_id):
    data = request.json or {}
    assigned_owner_id = data.get('assigned_owner_id')
    contact_mapping = data.get('contact_mapping')
    account_mapping = data.get('account_mapping')
    opportunity_mapping = data.get('opportunity_mapping')
    
    if not assigned_owner_id:
        return jsonify({'status': 'error', 'message': 'Owner assignment is mandatory.'}), 400
        
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL staging record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Check if contact needs to be linked or created
    contact_id = None
    if contact_mapping and contact_mapping != 'new':
        contact_id = int(contact_mapping)
    else:
        # Check if email already exists
        if sql_rec['email']:
            existing_cont = db_query_one("SELECT id FROM contacts WHERE LOWER(email) = ?", (sql_rec['email'].lower().strip(),))
            if existing_cont:
                contact_id = existing_cont['id']
        if not contact_id:
            # Create contact
            full_name = sql_rec['contact_name'] or f"{sql_rec['first_name'] or ''} {sql_rec['last_name'] or ''}".strip()
            contact_id = db_execute('''
                INSERT INTO contacts (
                    first_name, last_name, full_name, email, phone, alternate_phone, job_title, geography, country, linkedin_profile, source, validation_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TeleCRM SQL', 'Not Validated', ?, ?)
            ''', (
                sql_rec['first_name'], sql_rec['last_name'], full_name, sql_rec['email'], sql_rec['phone'], sql_rec['alternate_phone'],
                sql_rec['job_title'], sql_rec['geography'], sql_rec['country'], '', now_str, now_str
            ))
            log_timeline_activity('contact', contact_id, 'Contact created', f"Contact {full_name} created from SQL review", f"Email: {sql_rec['email']}", user_id)
            
    # Check if account needs to be linked or created
    account_id = None
    if account_mapping and account_mapping != 'new':
        account_id = int(account_mapping)
    else:
        # Check if company already exists
        if sql_rec['company']:
            existing_acct = db_query_one("SELECT id FROM accounts WHERE LOWER(account_name) = ?", (sql_rec['company'].lower().strip(),))
            if existing_acct:
                account_id = existing_acct['id']
        if not account_id and sql_rec['company']:
            # Create account
            account_id = db_execute('''
                INSERT INTO accounts (
                    account_name, website, domain, industry, geography, country, owner_id, partner_id, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'TeleCRM SQL', ?, ?)
            ''', (
                sql_rec['company'], sql_rec['website'], sql_rec['domain'], sql_rec['industry'], sql_rec['geography'], sql_rec['country'],
                assigned_owner_id, sql_rec['partner_id'], now_str, now_str
            ))
            log_timeline_activity('account', account_id, 'Account created', f"Account {sql_rec['company']} created from SQL review", "", user_id)

    # Link contact to account
    if contact_id and account_id:
        db_execute("UPDATE contacts SET account_id = ? WHERE id = ?", (account_id, contact_id))

    # Link or Create Opportunity
    opp_id = None
    if opportunity_mapping and opportunity_mapping != 'new':
        opp_id = int(opportunity_mapping)
        log_timeline_activity('opportunity', opp_id, 'SQL Linked', f"SQL from TeleCRM linked to existing opportunity", f"MOM: {sql_rec['mom']}", user_id)
    else:
        # Create Opportunity
        prod_row = db_query_one("SELECT name FROM product_solutions WHERE id = ?", (sql_rec['product_solution_id'],))
        prod_name = prod_row['name'] if prod_row else "Solutions"
        opp_name = f"{sql_rec['company'] or 'New Account'} - {prod_name} Opportunity"
        
        expected_close = (datetime.utcnow() + timedelta(days=90)).strftime('%Y-%m-%d')
        
        opp_id = db_execute('''
            INSERT INTO opportunities (
                account_id, contact_id, opportunity_name, company, primary_contact_name, primary_contact_email,
                owner_id, sales_manager_id, group_id, industry, geography, primary_product_solution_id, partner_id, partner_influence_type,
                estimated_value, currency, expected_close_date, stage, bucket, probability, meddic_score, status, sql_source, telecrm_contact_id, meeting_date, mom, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'USD', ?, 'Discovery', 'Prospecting', 10, 0, 'Open', 'TeleCRM SQL', ?, ?, ?, ?, ?)
        ''', (
            account_id, contact_id, opp_name, sql_rec['company'], sql_rec['contact_name'], sql_rec['email'],
            assigned_owner_id, assigned_owner_id, sql_rec['telecaller_manager_id'], sql_rec['industry'], sql_rec['geography'], sql_rec['product_solution_id'],
            sql_rec['partner_id'], sql_rec['partner_influence_type'] or 'None',
            expected_close, sql_rec['telecrm_contact_id'], sql_rec['meeting_completed_at'], sql_rec['mom'], now_str, now_str
        ))
        log_timeline_activity('opportunity', opp_id, 'SQL Handoff', "SQL converted from TeleCRM calling", f"MOM: {sql_rec['mom']}", user_id)
        
    # Prefill MEDDIC from SQL qualification
    buyer_identified = 1 if sql_rec['economic_buyer_hint'] else 0
    decision_known = 1 if sql_rec['timeline_indication'] else 0
    
    meddic_exist = db_query_one("SELECT id FROM meddic_qualifications WHERE entity_type = 'opportunity' AND entity_id = ?", (opp_id,))
    if meddic_exist:
        db_execute('''
            UPDATE meddic_qualifications
            SET primary_pain = ?,
                business_challenge = ?,
                economic_buyer_identified = ?,
                decision_process_known = ?,
                metrics_note = ?,
                updated_by = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            sql_rec['business_pain'] or 'Captured Business Pain', sql_rec['problem_statement'] or 'Problem statement',
            buyer_identified, decision_known, sql_rec['budget_indication'] or '',
            user_id, now_str, meddic_exist['id']
        ))
    else:
        db_execute('''
            INSERT INTO meddic_qualifications (
                entity_type, entity_id, metrics_identified, metrics_note, economic_buyer_identified, decision_process_known,
                primary_pain, business_challenge, pain_severity, pain_validated, champion_identified, score, updated_by, created_at, updated_at
            ) VALUES ('opportunity', ?, 0, ?, ?, ?, ?, ?, 'Medium', 1, 0, 20, ?, ?, ?)
        ''', (
            opp_id, sql_rec['budget_indication'] or '', buyer_identified, decision_known,
            sql_rec['business_pain'] or 'Captured Business Pain', sql_rec['problem_statement'] or 'Problem statement',
            user_id, now_str, now_str
        ))
    db_execute("UPDATE opportunities SET meddic_score = 20 WHERE id = ?", (opp_id,))

    # Create follow-up task for the assigned CRM owner
    tomorrow = datetime.utcnow() + timedelta(days=1)
    if tomorrow.weekday() >= 5:
        tomorrow = tomorrow + timedelta(days=7 - tomorrow.weekday())
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    db_execute('''
        INSERT INTO crm_tasks (
            title, description, task_type, related_entity_type, related_entity_id, opportunity_id, telecrm_contact_id,
            assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
        ) VALUES (?, ?, 'Follow-up', 'opportunity', ?, ?, ?, ?, ?, ?, '10:00', 'High', 'Open', ?, ?)
    ''', (
        "Follow up on TeleCRM SQL", f"SQL Handover from TeleCRM dialing workspace. MOM: {sql_rec['mom']}", opp_id, opp_id, sql_rec['telecrm_contact_id'],
        assigned_owner_id, user_id, tomorrow_str, now_str, now_str
    ))

    # Update Staging SQL record status
    db_execute('''
        UPDATE telecrm_sql
        SET status = 'Converted to CRM',
            assigned_owner_id = ?,
            crm_contact_id = ?,
            crm_account_id = ?,
            crm_opportunity_id = ?,
            converted_by = ?,
            converted_at = ?
        WHERE id = ?
    ''', (assigned_owner_id, contact_id, account_id, opp_id, user_id, now_str, sql_id))

    # Update TeleCRM Contact
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Converted',
            dialing_status = 'SQL Marked',
            converted_opportunity_id = ?,
            account_id = ?,
            contact_id = ?,
            is_finalized = 1,
            updated_at = ?
        WHERE id = ?
    ''', (opp_id, account_id, contact_id, now_str, sql_rec['telecrm_contact_id']))

    # Log review log
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, new_owner_id, performed_by, created_at
        ) VALUES (?, 'Converted to CRM', 'SQL staging record successfully converted and mapped in CRM', ?, 'Converted to CRM', ?, ?, ?)
    ''', (sql_id, sql_rec['status'], assigned_owner_id, user_id, now_str))

    log_timeline_activity('contact', contact_id, 'SQL Converted', "Contact converted from TeleCRM SQL Staging", f"MOM: {sql_rec['mom']}", user_id)
    if account_id:
        log_timeline_activity('account', account_id, 'SQL Converted', "Account linked to converted TeleCRM SQL Opportunity", f"MOM: {sql_rec['mom']}", user_id)

    # Copy call logs
    call_logs = db_query("SELECT * FROM telecrm_call_logs WHERE telecrm_contact_id = ?", (sql_rec['telecrm_contact_id'],))
    for cl in call_logs:
        log_timeline_activity('opportunity', opp_id, 'Call Log Import', 
                              f"Call attempt by Telecaller. Status: {cl['call_status']}. Duration: {cl['talk_duration']}s",
                              cl['outcome_note'] or '', cl['telecaller_id'])
        log_timeline_activity('contact', contact_id, 'Call Log Import', 
                              f"Call attempt by Telecaller. Status: {cl['call_status']}. Duration: {cl['talk_duration']}s",
                              cl['outcome_note'] or '', cl['telecaller_id'])

    return jsonify({'status': 'success', 'opportunity_id': opp_id})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/assign-owner', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_assign_owner_sql(sql_id):
    data = request.json or {}
    owner_id = data.get('assigned_owner_id')
    if not owner_id:
        return jsonify({'status': 'error', 'message': 'Owner is required.'}), 400
    
    sql_rec = db_query_one("SELECT status, assigned_owner_id FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute("UPDATE telecrm_sql SET assigned_owner_id = ? WHERE id = ?", (owner_id, sql_id))
    
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_owner_id, new_owner_id, performed_by, created_at
        ) VALUES (?, 'Owner assigned', 'Assigned owner updated', ?, ?, ?, ?)
    ''', (sql_id, sql_rec['assigned_owner_id'], owner_id, user_id, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/return-for-more-info', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_return_sql_staging(sql_id):
    data = request.json or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'status': 'error', 'message': 'Reason for return is required.'}), 400
        
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_sql
        SET status = 'More Info Required',
            returned_at = ?,
            returned_by = ?,
            review_notes = ?
        WHERE id = ?
    ''', (now_str, user_id, reason, sql_id))
    
    db_execute("UPDATE telecrm_contacts SET sql_status = 'More Info Required', updated_at = ? WHERE id = ?", (now_str, sql_rec['telecrm_contact_id']))
    
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
        ) VALUES (?, 'Returned for more info', ?, ?, 'More Info Required', ?, ?)
    ''', (sql_id, f"SQL returned to telecaller. Feedback: {reason}", sql_rec['status'], user_id, now_str))
    
    db_execute('''
        INSERT INTO crm_tasks (
            title, description, task_type, related_entity_type, related_entity_id, telecrm_contact_id,
            assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
        ) VALUES (?, ?, 'Follow-up', 'telecrm_contact', ?, ?, ?, ?, ?, '12:00', 'Medium', 'Open', ?, ?)
    ''', (
        "Update Qualification Info", f"Reviewer requested additional info: {reason}", sql_rec['telecrm_contact_id'], sql_rec['telecrm_contact_id'],
        sql_rec['telecaller_id'], user_id, datetime.utcnow().strftime('%Y-%m-%d'), now_str, now_str
    ))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/reject', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_reject_sql_staging(sql_id):
    data = request.json or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'status': 'error', 'message': 'Rejection reason is required.'}), 400
        
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_sql
        SET status = 'Rejected',
            rejected_at = ?,
            rejected_by = ?,
            review_notes = ?
        WHERE id = ?
    ''', (now_str, user_id, reason, sql_id))
    
    db_execute("UPDATE telecrm_contacts SET sql_status = 'SQL Rejected', updated_at = ? WHERE id = ?", (now_str, sql_rec['telecrm_contact_id']))
    
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
        ) VALUES (?, 'Rejected', ?, ?, 'Rejected', ?, ?)
    ''', (sql_id, f"SQL rejected. Reason: {reason}", sql_rec['status'], user_id, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/mark-duplicate', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager', 'Sales Head')
def api_mark_duplicate_sql(sql_id):
    data = request.json or {}
    reason = data.get('reason', 'Marked as duplicate').strip()
    
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_sql
        SET status = 'Duplicate',
            duplicate_marked_at = ?,
            duplicate_marked_by = ?,
            review_notes = ?
        WHERE id = ?
    ''', (now_str, user_id, reason, sql_id))
    
    db_execute("UPDATE telecrm_contacts SET sql_status = 'SQL Duplicate', updated_at = ? WHERE id = ?", (now_str, sql_rec['telecrm_contact_id']))
    
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
        ) VALUES (?, 'Marked duplicate', ?, ?, 'Duplicate', ?, ?)
    ''', (sql_id, f"SQL marked as duplicate. Notes: {reason}", sql_rec['status'], user_id, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/review-note', methods=['POST'])
@crm_login_required
def api_sql_review_note(sql_id):
    data = request.json or {}
    note = data.get('note', '').strip()
    if not note:
        return jsonify({'status': 'error', 'message': 'Note text is required.'}), 400
        
    sql_rec = db_query_one("SELECT status FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute('''
        UPDATE telecrm_sql
        SET review_notes = ?
        WHERE id = ?
    ''', (note, sql_id))
    
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, performed_by, created_at
        ) VALUES (?, 'Review note added', ?, ?, ?)
    ''', (sql_id, f"Review note: {note}", user_id, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/link-existing-contact', methods=['POST'])
@crm_login_required
def api_link_contact_sql(sql_id):
    data = request.json or {}
    contact_id = data.get('contact_id')
    if not contact_id:
        return jsonify({'status': 'error', 'message': 'Contact ID is required.'}), 400
    db_execute("UPDATE telecrm_sql SET crm_contact_id = ? WHERE id = ?", (contact_id, sql_id))
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/link-existing-account', methods=['POST'])
@crm_login_required
def api_link_account_sql(sql_id):
    data = request.json or {}
    account_id = data.get('account_id')
    if not account_id:
        return jsonify({'status': 'error', 'message': 'Account ID is required.'}), 400
    db_execute("UPDATE telecrm_sql SET crm_account_id = ? WHERE id = ?", (account_id, sql_id))
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql/<int:sql_id>/link-existing-opportunity', methods=['POST'])
@crm_login_required
def api_link_opp_sql(sql_id):
    data = request.json or {}
    opp_id = data.get('opportunity_id')
    if not opp_id:
        return jsonify({'status': 'error', 'message': 'Opportunity ID is required.'}), 400
        
    sql_rec = db_query_one("SELECT * FROM telecrm_sql WHERE id = ?", (sql_id,))
    if not sql_rec:
        return jsonify({'status': 'error', 'message': 'SQL record not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Update staging
    db_execute('''
        UPDATE telecrm_sql
        SET crm_opportunity_id = ?,
            status = 'Converted to CRM',
            converted_by = ?,
            converted_at = ?
        WHERE id = ?
    ''', (opp_id, user_id, now_str, sql_id))
    
    # Update contact
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Converted',
            converted_opportunity_id = ?,
            updated_at = ?
        WHERE id = ?
    ''', (opp_id, now_str, sql_rec['telecrm_contact_id']))
    
    # Append details to opportunity timeline
    log_timeline_activity('opportunity', opp_id, 'SQL Linked', 
                           f"SQL Staging record #{sql_id} linked to existing opportunity by reviewer. MOM: {sql_rec['mom']}", 
                           f"Business Pain: {sql_rec['business_pain']}. Next Action: {sql_rec['next_action']}", user_id)
                           
    # Log review log
    db_execute('''
        INSERT INTO telecrm_sql_review_logs (
            telecrm_sql_id, action_type, description, previous_status, new_status, performed_by, created_at
        ) VALUES (?, 'Linked to existing opportunity', ?, ?, 'Converted to CRM', ?, ?)
    ''', (sql_id, f"SQL linked to existing opportunity ID: {opp_id}", sql_rec['status'], user_id, now_str))
    
    return jsonify({'status': 'success'})


# Rejection Reasons Admin APIs
@crm_bp.route('/api/admin/telecrm/sql-rejection-reasons', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def api_admin_rejection_reasons():
    if request.method == 'GET':
        reasons = db_query("SELECT * FROM telecrm_sql_rejection_reasons ORDER BY sort_order ASC, id ASC")
        return jsonify(reasons)
        
    # POST - Create reason
    data = request.json or {}
    reason = data.get('reason', '').strip()
    desc = data.get('description', '').strip()
    sort_order = int(data.get('sort_order', 10))
    is_active = int(data.get('is_active', 1))
    
    if not reason:
        return jsonify({'status': 'error', 'message': 'Reason is required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    db_execute('''
        INSERT INTO telecrm_sql_rejection_reasons (reason, description, is_active, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (reason, desc, is_active, sort_order, now_str, now_str))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/admin/telecrm/sql-rejection-reasons/<int:reason_id>', methods=['PUT', 'DELETE'])
@crm_login_required
@role_required('Platform Admin')
def api_admin_rejection_reason_detail(reason_id):
    if request.method == 'DELETE':
        db_execute("DELETE FROM telecrm_sql_rejection_reasons WHERE id = ?", (reason_id,))
        return jsonify({'status': 'success'})
        
    # PUT - Update reason
    data = request.json or {}
    reason = data.get('reason', '').strip()
    desc = data.get('description', '').strip()
    sort_order = int(data.get('sort_order', 10))
    is_active = int(data.get('is_active', 1))
    
    if not reason:
        return jsonify({'status': 'error', 'message': 'Reason is required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    db_execute('''
        UPDATE telecrm_sql_rejection_reasons
        SET reason = ?, description = ?, is_active = ?, sort_order = ?, updated_at = ?
        WHERE id = ?
    ''', (reason, desc, is_active, sort_order, now_str, reason_id))
    
    return jsonify({'status': 'success'})


@crm_bp.route('/telecrm/reports')
@crm_login_required
def telecrm_reports():
    return redirect(url_for('crm.telecrm_analytics'))


# ----------------------------------------------------
# Telecaller Leaderboard
# ----------------------------------------------------
@crm_bp.route('/telecrm/leaderboard')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_leaderboard_page():
    # Load campaigns list
    user = g.crm_user
    if user['role'] == 'Platform Admin':
        campaigns = db_query("SELECT id, name FROM telecrm_lists ORDER BY id DESC")
    else:
        campaigns = db_query("SELECT id, name FROM telecrm_lists WHERE group_id = ? ORDER BY id DESC", (user['group_id'],))
        
    return render_template('telecrm/leaderboard.html', campaigns=campaigns, active_page='telecrm_leaderboard')


@crm_bp.route('/api/telecrm/leaderboard')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_get_leaderboard():
    user = g.crm_user
    role = user['role']
    
    period = request.args.get('period', 'Day') # Day, Week, Month, Year, Custom
    campaign_filter = request.args.get('campaign')
    metric = request.args.get('metric', 'Calls') # Calls, Connected, Spoken, Talk duration, Meetings scheduled, SQLs
    
    where_clauses = ["u.role = 'Telecaller'"]
    params = []
    
    if role in ('Group Admin', 'Telecaller Manager'):
        where_clauses.append("u.group_id = ?")
        params.append(user['group_id'])
        
    if campaign_filter:
        where_clauses.append("ds.campaign_id = ?")
        params.append(campaign_filter)
        
    # Apply date constraints
    now = datetime.utcnow()
    if period == 'Day':
        where_clauses.append("ds.stat_date = ?")
        params.append(now.strftime('%Y-%m-%d'))
    elif period == 'Week':
        start_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_week)
    elif period == 'Month':
        start_month = now.strftime('%Y-%m-01')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_month)
    elif period == 'Year':
        start_year = now.strftime('%Y-01-01')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_year)
        
    metric_col_mapping = {
        'Calls': 'SUM(ds.attempted_calls)',
        'Connected': 'SUM(ds.connected_calls)',
        'Spoken': 'SUM(ds.spoken_calls)',
        'Talk duration': 'SUM(ds.total_talk_duration_seconds)',
        'Meetings scheduled': 'SUM(ds.meetings_scheduled)',
        'SQLs': 'SUM(ds.sqls)'
    }
    metric_col = metric_col_mapping.get(metric, 'SUM(ds.attempted_calls)')
    
    query = f'''
        SELECT u.id, u.name,
               MIN(ds.first_call_at) as first_call_time,
               MAX(ds.last_call_at) as last_call_time,
               SUM(ds.attempted_calls) as calls_attempted,
               SUM(ds.connected_calls) as calls_connected,
               SUM(ds.spoken_calls) as spoken_calls,
               SUM(ds.total_talk_duration_seconds) as talk_duration,
               SUM(ds.meetings_scheduled) as meetings_scheduled,
               SUM(ds.sqls) as sqls_created,
               SUM(ds.opportunities_created) as opportunities,
               {metric_col} as rank_metric_value
        FROM crm_users u
        LEFT JOIN telecrm_user_daily_stats ds ON u.id = ds.user_id
        WHERE {' AND '.join(where_clauses)}
        GROUP BY u.id
        ORDER BY rank_metric_value DESC, u.name ASC
    '''
    standings = db_query(query, params)
    
    # Calculate list completion percentages for standings
    for idx, row in enumerate(standings):
        row['rank'] = idx + 1
        # Calculate list completion
        c_stats = db_query_one('''
            SELECT COUNT(id) as total, SUM(is_finalized) as comp
            FROM telecrm_contacts
            WHERE assigned_telecaller_id = ?
        ''', (row['id'],))
        row['completion_percentage'] = round((c_stats['comp'] / c_stats['total'] * 100), 1) if c_stats['total'] > 0 else 0.0
        
    # Get team stats
    team_stats = {
        'team_size': len(standings),
        'total_calls': sum(s['calls_attempted'] or 0 for s in standings),
        'total_duration': sum(s['talk_duration'] or 0 for s in standings),
        'total_meetings': sum(s['meetings_scheduled'] or 0 for s in standings),
        'total_sqls': sum(s['sqls_created'] or 0 for s in standings),
        'total_opportunities': sum(s['opportunities'] or 0 for s in standings)
    }
    
    return jsonify({
        'standings': standings,
        'team_stats': team_stats
    })


@crm_bp.route('/api/telecrm/users/<int:user_id>/statistics')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_user_statistics(user_id):
    # Restrict telecaller access to their own stats
    user = g.crm_user
    if user['role'] == 'Telecaller' and user['id'] != user_id:
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    campaign_filter = request.args.get('campaign')
    
    where_clauses = ["user_id = ?"]
    params = [user_id]
    if campaign_filter:
        where_clauses.append("campaign_id = ?")
        params.append(campaign_filter)
        
    query = f'''
        SELECT MIN(first_call_at) as first_call,
               MAX(last_call_at) as last_call,
               SUM(attempted_calls) as attempted,
               SUM(incoming_calls) as incoming,
               SUM(outgoing_calls) as outgoing,
               SUM(missed_calls) as missed,
               SUM(connected_calls) as connected,
               SUM(spoken_calls) as spoken,
               SUM(total_talk_duration_seconds) as total_duration,
               SUM(emails_sent) as emails_sent,
               SUM(meetings_scheduled) as meetings_scheduled,
               SUM(meetings_completed) as meetings_completed,
               SUM(conversions) as conversions,
               SUM(sqls) as sqls
        FROM telecrm_user_daily_stats
        WHERE {' AND '.join(where_clauses)}
    '''
    stats = db_query_one(query, params)
    
    # Task statistics
    tasks = db_query('''
        SELECT status, due_date
        FROM crm_tasks
        WHERE assigned_to = ?
    ''', (user_id,))
    
    task_stats = {'Late': 0, 'Pending': 0, 'Done': 0, 'Created': len(tasks)}
    today = datetime.utcnow().strftime('%Y-%m-%d')
    for t in tasks:
        if t['status'] == 'Completed':
            task_stats['Done'] += 1
        else:
            task_stats['Pending'] += 1
            if t['due_date'] < today:
                task_stats['Late'] += 1
                
    # Lead stages stats
    stages = db_query('''
        SELECT dialing_status, COUNT(*) as cnt
        FROM telecrm_contacts
        WHERE assigned_telecaller_id = ?
        GROUP BY dialing_status
    ''', (user_id,))
    stage_stats = {row['dialing_status']: row['cnt'] for row in stages}
    
    # Meeting status stats
    meetings = db_query('''
        SELECT status, COUNT(*) as cnt
        FROM telecrm_meetings
        WHERE created_by = ?
        GROUP BY status
    ''', (user_id,))
    meeting_stats = {row['status']: row['cnt'] for row in meetings}
    
    return jsonify({
        'calls': stats,
        'tasks': task_stats,
        'stages': stage_stats,
        'meetings': meeting_stats
    })


@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/assignee-performance')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def api_assignee_performance(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    performance = db_query('''
        SELECT u.id as telecaller_id, u.name as telecaller,
               al.allocation_percentage,
               al.assigned_count as assigned,
               SUM(CASE WHEN tc.call_attempt_count = 0 THEN 1 ELSE 0 END) as untouched,
               SUM(CASE WHEN tc.call_attempt_count > 0 THEN 1 ELSE 0 END) as attempted,
               SUM(tc.is_finalized) as completed,
               SUM(tc.connected_call_count) as connected,
               SUM(tc.spoken_call_count) as spoken,
               SUM(CASE WHEN tc.meeting_status = 'Scheduled' THEN 1 ELSE 0 END) as meetings_scheduled,
               SUM(CASE WHEN tc.sql_status = 'SQL Approved' THEN 1 ELSE 0 END) as sqls_created
        FROM telecrm_allocation_logs al
        JOIN crm_users u ON al.telecaller_id = u.id
        LEFT JOIN telecrm_contacts tc ON tc.assigned_telecaller_id = u.id AND tc.telecrm_list_id = al.telecrm_list_id
        WHERE al.telecrm_list_id = ?
        GROUP BY u.id
    ''', (campaign_id,))
    
    # Calculate percentages
    for row in performance:
        tot = row['assigned'] or 0
        row['completion_percentage'] = round((row['completed'] / tot * 100), 1) if tot > 0 else 0.0
        row['conversion_percentage'] = round((row['sqls_created'] / tot * 100), 1) if tot > 0 else 0.0
        
    return jsonify(performance)

# ----------------------------------------------------
# Reallocation logic
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/reallocate', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def api_reallocate_campaign_contacts(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    source_caller_id = data.get('source_caller_id')
    target_caller_id = data.get('target_caller_id')
    reallocate_type = data.get('reallocate_type', 'all_untouched') # all_untouched, percentage, specific
    reallocate_pct = int(data.get('percentage', 0))
    specific_contact_ids = data.get('contact_ids', [])
    force = data.get('force', False)
    
    if not target_caller_id:
        return jsonify({'status': 'error', 'message': 'Target telecaller is required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Base WHERE clause
    where = "telecrm_list_id = ?"
    params = [campaign_id]
    
    if source_caller_id:
        where += " AND assigned_telecaller_id = ?"
        params.append(source_caller_id)
        
    # Types partitioning
    if reallocate_type == 'all_untouched':
        where += " AND call_attempt_count = 0 AND is_finalized = 0"
    elif reallocate_type == 'percentage':
        where += " AND is_finalized = 0"
    elif reallocate_type == 'specific':
        if not specific_contact_ids:
            return jsonify({'status': 'error', 'message': 'No contact ids provided.'}), 400
        where += f" AND id IN ({','.join(['?'] * len(specific_contact_ids))})"
        params.extend(specific_contact_ids)
        
    # Query targets candidates
    candidates = db_query(f"SELECT * FROM telecrm_contacts WHERE {where}", params)
    if not candidates:
        return jsonify({'status': 'success', 'message': 'No contacts matched the reallocation filters.'})
        
    if reallocate_type == 'percentage' and reallocate_pct > 0:
        limit = int(len(candidates) * (reallocate_pct / 100))
        candidates = candidates[:limit]
        
    # Check for warnings: meetings scheduled, SQL reviews, or future follow-ups
    warn_contacts = []
    clean_contacts = []
    for c in candidates:
        has_issue = False
        if c['sql_status'] == 'SQL Review':
            has_issue = True
        elif c['meeting_status'] == 'Scheduled':
            has_issue = True
        elif c['next_followup_at'] and c['next_followup_at'] > now_str:
            has_issue = True
            
        if has_issue:
            warn_contacts.append(c)
        else:
            clean_contacts.append(c)
            
    if warn_contacts and not force:
        # Prompt for manager confirmation
        return jsonify({
            'status': 'warning_required',
            'message': f"Found {len(warn_contacts)} contacts with future follow-ups, scheduled meetings, or active SQL reviews. Confirm reassignment?",
            'warn_contact_ids': [c['id'] for c in warn_contacts],
            'total_matched': len(candidates)
        })
        
    # Execute update
    to_update = candidates if force else clean_contacts
    if not to_update:
        return jsonify({'status': 'success', 'message': 'No clean contacts to transfer.'})
        
    update_ids = [c['id'] for c in to_update]
    ids_placeholders = ','.join(['?'] * len(update_ids))
    
    # Save assignment history
    for c in to_update:
        db_execute('''
            INSERT INTO lead_assignment_history (telecrm_contact_id, previous_owner_id, new_owner_id, changed_by, reason, created_at)
            VALUES (?, ?, ?, ?, 'Campaign Manager Reallocation', ?)
        ''', (c['id'], c['assigned_telecaller_id'], target_caller_id, user_id, now_str))
        
    # Perform update
    db_execute(f'''
        UPDATE telecrm_contacts
        SET assigned_telecaller_id = ?, updated_at = ?
        WHERE id IN ({ids_placeholders})
    ''', [target_caller_id, now_str] + update_ids)
    
    # Re-calculate allocation counts
    # Reset counts for source & target
    for cid in set([source_caller_id, target_caller_id]):
        if not cid:
            continue
        cnt = db_query_one("SELECT COUNT(*) as cnt FROM telecrm_contacts WHERE telecrm_list_id = ? AND assigned_telecaller_id = ?", (campaign_id, cid))['cnt']
        db_execute("UPDATE telecrm_allocation_logs SET assigned_count = ? WHERE telecrm_list_id = ? AND telecaller_id = ?", (cnt, campaign_id, cid))
        
    update_campaign_completion_stats(campaign_id)
    return jsonify({'status': 'success', 'message': f"Successfully reallocated {len(to_update)} contacts to target telecaller."})

# ----------------------------------------------------
# Campaign Report Endpoints
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/reports')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def api_campaign_reports(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    # Day/Week/Month/Year filters
    period = request.args.get('period', 'Month')
    where_clauses = ["campaign_id = ?"]
    params = [campaign_id]
    
    now = datetime.utcnow()
    if period == 'Day':
        where_clauses.append("stat_date = ?")
        params.append(now.strftime('%Y-%m-%d'))
    elif period == 'Week':
        start_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        where_clauses.append("stat_date >= ?")
        params.append(start_week)
    elif period == 'Month':
        start_month = now.strftime('%Y-%m-01')
        where_clauses.append("stat_date >= ?")
        params.append(start_month)
    elif period == 'Year':
        start_year = now.strftime('%Y-01-01')
        where_clauses.append("stat_date >= ?")
        params.append(start_year)
        
    # Calling Report
    calling_rep = db_query_one(f'''
        SELECT SUM(attempted_calls) as total_calls,
               SUM(incoming_calls) as incoming_calls,
               SUM(outgoing_calls) as outgoing_calls,
               SUM(connected_calls) as connected_calls,
               SUM(spoken_calls) as spoken_calls,
               SUM(missed_calls) as missed_calls,
               SUM(total_talk_duration_seconds) as total_duration,
               AVG(total_talk_duration_seconds) as avg_duration,
               MIN(first_call_at) as first_call,
               MAX(last_call_at) as last_call
        FROM telecrm_user_daily_stats
        WHERE {' AND '.join(where_clauses)}
    ''', params)
    
    # Lead Status Report
    stages = db_query('''
        SELECT dialing_status, COUNT(*) as cnt
        FROM telecrm_contacts
        WHERE telecrm_list_id = ?
        GROUP BY dialing_status
    ''', (campaign_id,))
    
    lead_status_rep = {
        'fresh': 0, 'call_unanswered': 0, 'followup': 0, 'spoken': 0, 'converted': 0, 'lost': 0
    }
    for row in stages:
        status = row['dialing_status']
        cnt = row['cnt']
        if status in ('New', 'Fresh', 'Not Dialed'):
            lead_status_rep['fresh'] += cnt
        elif status in ('Call Unanswered', 'Busy', 'Gatekeeper', 'Relevant Person Unavailable'):
            lead_status_rep['call_unanswered'] += cnt
        elif status in ('Call Back Later', 'Information Requested'):
            lead_status_rep['followup'] += cnt
        elif status in ('Spoken', 'Interested', 'Meeting Scheduled', 'Meeting Completed'):
            lead_status_rep['spoken'] += cnt
        elif status in ('SQL Marked', 'SQL Approved', 'Converted to Opportunity'):
            lead_status_rep['converted'] += cnt
        else: # Lost
            lead_status_rep['lost'] += cnt
            
    # Lost reasons report
    lost_reasons = db_query('''
        SELECT lr.name, COUNT(tc.id) as cnt
        FROM telecrm_contacts tc
        JOIN telecrm_lost_reasons lr ON tc.lost_reason_id = lr.id
        WHERE tc.telecrm_list_id = ?
        GROUP BY lr.id
    ''', (campaign_id,))
    lost_reasons_rep = {row['name']: row['cnt'] for row in lost_reasons}
    
    return jsonify({
        'calling': calling_rep,
        'stages': lead_status_rep,
        'lost_reasons': lost_reasons_rep
    })

# ----------------------------------------------------
# CSV Export Utilities
# ----------------------------------------------------
@crm_bp.route('/api/telecrm/campaigns/<int:campaign_id>/export')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def api_campaign_export(campaign_id):
    if not check_campaign_access(campaign_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    contacts = db_query('''
        SELECT tc.id, tc.full_name, tc.company, tc.email, tc.phone, tc.job_title,
               tc.dialing_status, tc.last_disposition, tc.interest_level, tc.priority,
               tc.call_attempt_count, tc.connected_call_count, tc.spoken_call_count,
               tc.meeting_status, tc.discovery_meeting_date, tc.sql_status, u.name as assignee
        FROM telecrm_contacts tc
        LEFT JOIN crm_users u ON tc.assigned_telecaller_id = u.id
        WHERE tc.telecrm_list_id = ?
    ''', (campaign_id,))
    
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow(['ID', 'Name', 'Company', 'Email', 'Phone', 'Job Title', 'Dialing Status', 'Last Disposition', 'Interest Level', 'Priority', 'Attempt Count', 'Connected Count', 'Spoken Count', 'Meeting Status', 'Discovery Date', 'SQL Status', 'Assignee'])
    
    for c in contacts:
        writer.writerow([c['id'], c['full_name'], c['company'], c['email'], c['phone'], c['job_title'], c['dialing_status'], c['last_disposition'], c['interest_level'], c['priority'], c['call_attempt_count'], c['connected_call_count'], c['spoken_call_count'], c['meeting_status'], c['discovery_meeting_date'], c['sql_status'], c['assignee']])
        
    return Response(
        dest.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=campaign_{campaign_id}_report.csv"}
    )


@crm_bp.route('/api/telecrm/leaderboard/export')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def api_leaderboard_export():
    user = g.crm_user
    period = request.args.get('period', 'Day')
    metric = request.args.get('metric', 'Calls')
    
    where_clauses = ["u.role = 'Telecaller'"]
    params = []
    
    if user['role'] in ('Group Admin', 'Telecaller Manager'):
        where_clauses.append("u.group_id = ?")
        params.append(user['group_id'])
        
    # Apply date constraints
    now = datetime.utcnow()
    if period == 'Day':
        where_clauses.append("ds.stat_date = ?")
        params.append(now.strftime('%Y-%m-%d'))
    elif period == 'Week':
        start_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_week)
    elif period == 'Month':
        start_month = now.strftime('%Y-%m-01')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_month)
    elif period == 'Year':
        start_year = now.strftime('%Y-01-01')
        where_clauses.append("ds.stat_date >= ?")
        params.append(start_year)
        
    metric_col_mapping = {
        'Calls': 'SUM(ds.attempted_calls)',
        'Connected': 'SUM(ds.connected_calls)',
        'Spoken': 'SUM(ds.spoken_calls)',
        'Talk duration': 'SUM(ds.total_talk_duration_seconds)',
        'Meetings scheduled': 'SUM(ds.meetings_scheduled)',
        'SQLs': 'SUM(ds.sqls)'
    }
    metric_col = metric_col_mapping.get(metric, 'SUM(ds.attempted_calls)')
    
    query = f'''
        SELECT u.name,
               SUM(ds.attempted_calls) as calls_attempted,
               SUM(ds.connected_calls) as calls_connected,
               SUM(ds.spoken_calls) as spoken_calls,
               SUM(ds.total_talk_duration_seconds) as talk_duration,
               SUM(ds.meetings_scheduled) as meetings_scheduled,
               SUM(ds.sqls) as sqls_created,
               {metric_col} as rank_metric_value
        FROM crm_users u
        LEFT JOIN telecrm_user_daily_stats ds ON u.id = ds.user_id
        WHERE {' AND '.join(where_clauses)}
        GROUP BY u.id
        ORDER BY rank_metric_value DESC, u.name ASC
    '''
    standings = db_query(query, params)
    
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow(['Rank', 'Name', 'Attempted Calls', 'Connected Calls', 'Spoken Calls', 'Talk Duration (Sec)', 'Meetings Scheduled', 'SQLs Created', 'Selected Metric Value'])
    
    for idx, s in enumerate(standings):
        writer.writerow([idx + 1, s['name'], s['calls_attempted'], s['calls_connected'], s['spoken_calls'], s['talk_duration'], s['meetings_scheduled'], s['sqls_created'], s['rank_metric_value']])
        
    return Response(
        dest.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=telecaller_leaderboard_{period}.csv"}
    )


# ----------------------------------------------------
# TeleCRM Templates CRUD & Rendering Section
# ----------------------------------------------------

@crm_bp.route('/telecrm/templates', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_templates_mgmt():
    user = g.crm_user
    if request.method == 'POST':
        action = request.form.get('action')
        template_id = request.form.get('template_id')
        template_type = request.form.get('type')
        name = request.form.get('name')
        subject = request.form.get('subject') if template_type == 'Email' else None
        body = request.form.get('body')
        is_active = int(request.form.get('is_active', 1))
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        if action == 'create':
            db_execute('''
                INSERT INTO telecrm_templates (type, name, subject, body, created_by, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (template_type, name, subject, body, user['id'], is_active, now_str, now_str))
            flash(f"Template '{name}' created successfully.", "success")
        elif action == 'edit':
            db_execute('''
                UPDATE telecrm_templates
                SET type = ?, name = ?, subject = ?, body = ?, is_active = ?, updated_at = ?
                WHERE id = ?
            ''', (template_type, name, subject, body, is_active, now_str, template_id))
            flash(f"Template '{name}' updated successfully.", "success")
        return redirect(url_for('crm.telecrm_templates_mgmt'))

    templates = db_query('''
        SELECT t.*, u.name as creator_name
        FROM telecrm_templates t
        LEFT JOIN crm_users u ON t.created_by = u.id
        ORDER BY t.type ASC, t.name ASC
    ''')
    return render_template('crm/telecrm/templates.html', templates=templates, active_page='telecrm_templates')

@crm_bp.route('/telecrm/templates/delete/<int:template_id>', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_template_delete(template_id):
    db_execute("DELETE FROM telecrm_templates WHERE id = ?", (template_id,))
    flash("Template deleted successfully.", "success")
    return redirect(url_for('crm.telecrm_templates_mgmt'))

@crm_bp.route('/api/telecrm/templates')
@crm_login_required
def api_get_templates():
    template_type = request.args.get('type')  # 'SMS' or 'Email'
    if template_type:
        templates = db_query("SELECT id, type, name, subject, body FROM telecrm_templates WHERE type = ? AND is_active = 1 ORDER BY name ASC", (template_type,))
    else:
        templates = db_query("SELECT id, type, name, subject, body FROM telecrm_templates WHERE is_active = 1 ORDER BY type ASC, name ASC")
    return jsonify({'status': 'success', 'templates': templates})

@crm_bp.route('/api/telecrm/templates/render/<int:template_id>')
@crm_login_required
def api_render_template(template_id):
    contact_id = request.args.get('contact_id')
    template = db_query_one("SELECT * FROM telecrm_templates WHERE id = ?", (template_id,))
    if not template:
        return jsonify({'status': 'error', 'message': 'Template not found'}), 404
    
    subject = template.get('subject') or ''
    body = template.get('body') or ''
    
    # If contact_id is provided, resolve placeholders
    if contact_id:
        contact = db_query_one("SELECT * FROM telecrm_contacts WHERE id = ?", (contact_id,))
        if contact:
            # Let's resolve placeholders
            # placeholder mapping helper
            def resolve(text, c, u):
                if not text:
                    return ""
                # Compute first_name from full_name if first_name not in contact
                first_name = c.get('full_name', '').split(' ')[0] if c.get('full_name') else ''
                replacements = {
                    '{first_name}': first_name,
                    '{full_name}': c.get('full_name') or '',
                    '{company}': c.get('company') or '',
                    '{phone}': c.get('phone') or '',
                    '{email}': c.get('email') or '',
                    '{job_title}': c.get('job_title') or '',
                    '{user_name}': u.get('name') or '',
                    '{user_email}': u.get('email') or '',
                }
                for k, v in replacements.items():
                    text = text.replace(k, str(v))
                return text
            
            subject = resolve(subject, contact, g.crm_user)
            body = resolve(body, contact, g.crm_user)
            
    return jsonify({
        'status': 'success',
        'template_id': template_id,
        'subject': subject,
        'body': body
    })

@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/send-sms', methods=['POST'])
@crm_login_required
def api_send_sms(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    message_body = request.form.get('message_body') or request.json.get('message_body') if request.is_json else request.form.get('message_body')
    if not message_body:
        return jsonify({'status': 'error', 'message': 'Message body is required.'}), 400
        
    contact = db_query_one("SELECT * FROM telecrm_contacts WHERE id = ?", (contact_id,))
    if not contact:
        return jsonify({'status': 'error', 'message': 'Contact not found.'}), 404
        
    recipient_phone = contact['phone']
    user_id = g.crm_user['id']
    campaign_id = contact['telecrm_list_id']
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Insert SMS log
    db_execute('''
        INSERT INTO telecrm_sms_logs (telecrm_contact_id, sender_user_id, recipient_phone, message_body, status, sent_at)
        VALUES (?, ?, ?, ?, 'Sent', ?)
    ''', (contact_id, user_id, recipient_phone, message_body, now_str))
    
    # Also log to channel logs for unified tracking
    db_execute('''
        INSERT INTO telecrm_channel_logs (
            telecrm_contact_id, campaign_id, user_id, channel, direction, recipient, subject, body, status, sent_at, created_at
        ) VALUES (?, ?, ?, 'SMS', 'Outgoing', ?, NULL, ?, 'Sent', ?, ?)
    ''', (contact_id, campaign_id, user_id, recipient_phone, message_body, now_str, now_str))
    
    # Update daily sms_sent stat
    update_user_daily_stat(user_id, campaign_id, now_str[:10], {'sms_sent': 1})
    
    # Log timeline activity
    log_timeline_activity('telecrm_contact', contact_id, 'SMS Sent', "SMS Outgoing", message_body[:150], user_id)
    
    return jsonify({'status': 'success', 'message': 'SMS successfully logged and sent.'})


# ----------------------------------------------------
# TeleCRM Settings & Configurations Section
# ----------------------------------------------------

@crm_bp.route('/telecrm/settings', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_settings():
    user = g.crm_user
    group_id = user['group_id']
    
    if request.method == 'POST':
        tgt_group_id = request.form.get('group_id')
        # If user is not Platform Admin, they can only edit their own group settings
        if user['role'] != 'Platform Admin':
            tgt_group_id = group_id
            
        autodialer_delay = int(request.form.get('autodialer_delay_seconds', 5))
        call_timeout = int(request.form.get('call_timeout_seconds', 30))
        sms_provider = request.form.get('sms_gateway_provider', 'MockGateway')
        sms_key = request.form.get('sms_api_key', '')
        smtp_host = request.form.get('group_smtp_host', '')
        smtp_port = int(request.form.get('group_smtp_port', 587))
        smtp_username = request.form.get('group_smtp_username', '')
        smtp_password = request.form.get('group_smtp_password', '')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if settings exist for target group
        existing = db_query_one("SELECT id FROM telecrm_settings WHERE group_id = ?", (tgt_group_id,))
        if existing:
            db_execute('''
                UPDATE telecrm_settings
                SET autodialer_delay_seconds = ?, call_timeout_seconds = ?, sms_gateway_provider = ?, sms_api_key = ?,
                    group_smtp_host = ?, group_smtp_port = ?, group_smtp_username = ?, group_smtp_password = ?, updated_at = ?
                WHERE group_id = ?
            ''', (autodialer_delay, call_timeout, sms_provider, sms_key, smtp_host, smtp_port, smtp_username, smtp_password, now_str, tgt_group_id))
        else:
            db_execute('''
                INSERT INTO telecrm_settings (group_id, autodialer_delay_seconds, call_timeout_seconds, sms_gateway_provider, sms_api_key, group_smtp_host, group_smtp_port, group_smtp_username, group_smtp_password, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tgt_group_id, autodialer_delay, call_timeout, sms_provider, sms_key, smtp_host, smtp_port, smtp_username, smtp_password, now_str))
            
        flash("TeleCRM Settings updated successfully.", "success")
        return redirect(url_for('crm.telecrm_settings'))
        
    # GET method
    groups = db_query("SELECT id, name FROM crm_groups ORDER BY name ASC")
    
    # Query current group settings
    if user['role'] == 'Platform Admin':
        # Admin can view settings for all groups or select a group, we will query all settings
        group_settings = db_query('''
            SELECT s.*, g.name as group_name
            FROM telecrm_settings s
            JOIN crm_groups g ON s.group_id = g.id
        ''')
    else:
        group_settings = db_query('''
            SELECT s.*, g.name as group_name
            FROM telecrm_settings s
            JOIN crm_groups g ON s.group_id = g.id
            WHERE s.group_id = ?
        ''', (group_id,))
        
    return render_template(
        'crm/telecrm/settings.html',
        settings=group_settings,
        groups=groups,
        active_page='telecrm_settings'
    )

@crm_bp.route('/api/telecrm/settings')
@crm_login_required
def api_get_settings():
    group_id = g.crm_user['group_id']
    settings = db_query_one("SELECT * FROM telecrm_settings WHERE group_id = ?", (group_id,))
    if not settings:
        # Return default values
        settings = {
            'autodialer_delay_seconds': 5,
            'call_timeout_seconds': 30,
            'sms_gateway_provider': 'MockGateway',
            'sms_api_key': '',
            'group_smtp_host': '',
            'group_smtp_port': 587,
            'group_smtp_username': '',
            'group_smtp_password': ''
        }
    return jsonify({'status': 'success', 'settings': dict(settings)})


# ----------------------------------------------------
# TeleCRM Sample Templates Download Section
# ----------------------------------------------------

@crm_bp.route('/telecrm/import/sample-csv')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_sample_csv():
    headers = [
        'First Name', 'Last Name', 'Full Name', 'Email', 'Phone',
        'Company', 'Job Title', 'Geography', 'Country', 'Industry',
        'Website', 'LinkedIn', 'Alternate Phone', 'Notes'
    ]
    sample_data = [
        ['John', 'Doe', 'John Doe', 'john.doe@examplecorp.com', '+15550199234', 'Example Corp', 'Sales Manager', 'North America', 'United States', 'Technology', 'examplecorp.com', 'linkedin.com/in/johndoe', '+15550199235', 'Interested in AI services.'],
        ['Jane', 'Smith', 'Jane Smith', 'jane.smith@healthtech.org', '+15550199888', 'HealthTech Org', 'CTO', 'Europe', 'United Kingdom', 'Healthcare', 'healthtech.org', 'linkedin.com/in/janesmith', '', 'Needs backup contact info.']
    ]
    
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow(headers)
    for row in sample_data:
        writer.writerow(row)
        
    return Response(
        dest.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=sample_lead_import_template.csv"}
    )

@crm_bp.route('/telecrm/import/sample-xlsx')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_sample_xlsx():
    headers = [
        'First Name', 'Last Name', 'Full Name', 'Email', 'Phone',
        'Company', 'Job Title', 'Geography', 'Country', 'Industry',
        'Website', 'LinkedIn', 'Alternate Phone', 'Notes'
    ]
    sample_data = [
        ['John', 'Doe', 'John Doe', 'john.doe@examplecorp.com', '+15550199234', 'Example Corp', 'Sales Manager', 'North America', 'United States', 'Technology', 'examplecorp.com', 'linkedin.com/in/johndoe', '+15550199235', 'Interested in AI services.'],
        ['Jane', 'Smith', 'Jane Smith', 'jane.smith@healthtech.org', '+15550199888', 'HealthTech Org', 'CTO', 'Europe', 'United Kingdom', 'Healthcare', 'healthtech.org', 'linkedin.com/in/janesmith', '', 'Needs backup contact info.']
    ]
    
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sample Template"
        
        ws.append(headers)
        for row in sample_data:
            ws.append(row)
            
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        
        return Response(
            out.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-disposition": "attachment; filename=sample_lead_import_template.xlsx"}
        )
    except ImportError:
        # Fallback to CSV if openpyxl not installed
        dest = io.StringIO()
        writer = csv.writer(dest)
        writer.writerow(headers)
        for row in sample_data:
            writer.writerow(row)
            
        return Response(
            dest.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=sample_lead_import_template.csv"}
        )


