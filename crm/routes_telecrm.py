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
# TeleCRM Dashboard / Home
# ----------------------------------------------------
@crm_bp.route('/telecrm')
@crm_bp.route('/telecrm/dashboard')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def telecrm_dashboard():
    user = g.crm_user
    role = user['role']
    
    # Render standard dashboard page
    # Fetch campaigns list
    if role == 'Platform Admin':
        campaigns = db_query("SELECT * FROM telecrm_lists ORDER BY id DESC")
    else:
        campaigns = db_query("SELECT * FROM telecrm_lists WHERE group_id = ? ORDER BY id DESC", (user['group_id'],))
        
    return render_template(
        'telecrm/dashboard.html',
        campaigns=campaigns,
        active_page='telecrm_dashboard'
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
    
    if sql_recommendation == 1:
        # Submit automatically for SQL review
        # Check if already submitted
        exist = db_query_one("SELECT id FROM telecrm_sql_reviews WHERE telecrm_contact_id = ? AND campaign_id = ?", (contact_id, meeting['campaign_id']))
        if not exist:
            db_execute('''
                INSERT INTO telecrm_sql_reviews (
                    telecrm_contact_id, campaign_id, submitted_by, submitted_at, review_status, notes
                ) VALUES (?, ?, ?, ?, 'Pending', ?)
            ''', (contact_id, meeting['campaign_id'], user_id, now_str, f"MOM: {mom}. Pain: {pain}"))
            
            db_execute("UPDATE telecrm_contacts SET sql_status = 'SQL Review', dialing_status = 'SQL Marked' WHERE id = ?", (contact_id,))
            log_timeline_activity('telecrm_contact', contact_id, 'SQL requested', "Submitted for Manager SQL review", "", user_id)
            
    update_campaign_completion_stats(meeting['campaign_id'])
    
    return jsonify({'status': 'success'})

# ----------------------------------------------------
# SQL Submit & Review Queues
# ----------------------------------------------------
@crm_bp.route('/telecrm/sql-review')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager')
def telecrm_sql_review_page():
    return render_template('telecrm/sql_review.html', active_page='telecrm_sql_review')


@crm_bp.route('/api/telecrm/contacts/<int:contact_id>/submit-sql', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Telecaller')
def api_submit_sql(contact_id):
    if not check_telecrm_contact_access(contact_id):
        return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
        
    data = request.json or {}
    notes = data.get('notes', '')
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    contact = db_query_one("SELECT telecrm_list_id, sql_status FROM telecrm_contacts WHERE id = ?", (contact_id,))
    if contact['sql_status'] != 'Not SQL':
        return jsonify({'status': 'error', 'message': 'Contact has already been qualified or submitted for SQL review.'}), 400
        
    # Create SQL Review entry
    db_execute('''
        INSERT INTO telecrm_sql_reviews (
            telecrm_contact_id, campaign_id, submitted_by, submitted_at, review_status, notes
        ) VALUES (?, ?, ?, ?, 'Pending', ?)
    ''', (contact_id, contact['telecrm_list_id'], user_id, now_str, notes))
    
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Review', dialing_status = 'SQL Marked', updated_at = ?
        WHERE id = ?
    ''', (now_str, contact_id))
    
    log_timeline_activity('telecrm_contact', contact_id, 'SQL requested', "Contact submitted for Manager SQL review", notes, user_id)
    update_campaign_completion_stats(contact['telecrm_list_id'])
    
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql-review')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager')
def api_get_sql_review_queue():
    user = g.crm_user
    role = user['role']
    
    params = []
    where_clauses = ["sr.review_status = 'Pending'"]
    
    # Filter based on scope
    if role in ('Group Admin', 'Telecaller Manager'):
        where_clauses.append("tc.group_id = ?")
        params.append(user['group_id'])
    elif role == 'Manager / Sales Manager':
        # Sales managers can view review entries recommended for them
        where_clauses.append("(sr.assigned_sales_manager_id = ? OR sr.assigned_sales_manager_id IS NULL)")
        params.append(user['id'])
        
    query = f'''
        SELECT sr.*, tc.full_name as contact_name, tc.company, tc.email, tc.phone, tc.job_title,
               tc.lead_quality_rating, tc.discovery_meeting_date, tc.mom, tc.notes as contact_notes,
               cl.name as campaign_name, u.name as telecaller_name, ps.name as product_name, p.name as partner_name
        FROM telecrm_sql_reviews sr
        JOIN telecrm_contacts tc ON sr.telecrm_contact_id = tc.id
        JOIN telecrm_lists cl ON sr.campaign_id = cl.id
        JOIN crm_users u ON sr.submitted_by = u.id
        LEFT JOIN product_solutions ps ON tc.product_solution_id = ps.id
        LEFT JOIN partners p ON tc.partner_id = p.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY sr.submitted_at ASC
    '''
    reviews = db_query(query, params)
    
    # Inject warnings for existing records mapping
    for r in reviews:
        r['warnings'] = get_validation_warnings(r['email'], r['phone'], '', r['company'])
        
    return jsonify(reviews)


@crm_bp.route('/api/telecrm/sql-review/<int:review_id>/approve', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager')
def api_approve_sql(review_id):
    data = request.json or {}
    sales_manager_id = data.get('assigned_sales_manager_id')
    notes = data.get('notes', '')
    
    review = db_query_one("SELECT * FROM telecrm_sql_reviews WHERE id = ?", (review_id,))
    if not review:
        return jsonify({'status': 'error', 'message': 'SQL review entry not found.'}), 404
        
    contact_id = review['telecrm_contact_id']
    contact = db_query_one("SELECT * FROM telecrm_contacts WHERE id = ?", (contact_id,))
    
    user = g.crm_user
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if not sales_manager_id:
        sales_manager_id = user['id']
        
    # 1. Create or Map Account and Contact in CRM Core
    account_id, core_contact_id = get_or_create_account_and_contact(
        company_name=contact['company'],
        email=contact['email'],
        phone=contact['phone'],
        first_name=contact['first_name'],
        last_name=contact['last_name'],
        job_title=contact['job_title'],
        geography=contact['geography'],
        country=contact['country'],
        industry=contact['industry'],
        website=contact['website'],
        linkedin_profile=contact['linkedin_profile'],
        source='TeleCRM SQL Handoff',
        owner_id=sales_manager_id
    )
    
    # 2. Create Lead in CRM Core
    lead_list = db_query_one("SELECT id FROM lead_lists WHERE name = 'TeleCRM Dialing Lists'")
    lead_list_id = lead_list['id'] if lead_list else None
    
    lead_id = db_execute('''
        INSERT INTO leads (
            first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry, website, linkedin_profile,
            lead_source, lead_list_id, account_id, contact_id, owner_id, group_id, status, primary_product_solution_id, partner_id, consent_status, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TeleCRM', ?, ?, ?, ?, ?, 'Qualified', ?, ?, ?, ?, ?, ?)
    ''', (
        contact['first_name'], contact['last_name'], contact['full_name'], contact['company'], contact['email'], contact['phone'], contact['job_title'], contact['geography'], contact['country'], contact['industry'], contact['website'], contact['linkedin_profile'],
        lead_list_id, account_id, core_contact_id, sales_manager_id, contact['group_id'], contact['product_solution_id'], contact['partner_id'], 1, contact['notes'], now_str, now_str
    ))
    
    # 3. Create Opportunity in CRM Core
    prod_row = db_query_one("SELECT name FROM product_solutions WHERE id = ?", (contact['product_solution_id'],))
    prod_name = prod_row['name'] if prod_row else "Solutions"
    opp_name = f"{contact['company'] or 'New Account'} - {prod_name} Opportunity"
    
    opp_id = db_execute('''
        INSERT INTO opportunities (
            lead_id, account_id, contact_id, opportunity_name, company, primary_contact_name, primary_contact_email,
            owner_id, sales_manager_id, group_id, industry, geography, primary_product_solution_id, partner_id, partner_influence_type,
            estimated_value, currency, expected_close_date, stage, bucket, probability, meddic_score, status, sql_source, telecrm_contact_id, meeting_date, mom, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'None', 0.0, 'USD', ?, 'Discovery', 'Prospecting', 10, 0, 'Open', 'TeleCRM', ?, ?, ?, ?, ?)
    ''', (
        lead_id, account_id, core_contact_id, opp_name, contact['company'], contact['full_name'], contact['email'],
        sales_manager_id, sales_manager_id, contact['group_id'], contact['industry'], contact['geography'], contact['product_solution_id'], contact['partner_id'],
        (datetime.utcnow() + timedelta(days=90)).strftime('%Y-%m-%d'), contact_id, contact['meeting_scheduled_at'], contact['mom'], now_str, now_str
    ))
    
    # 4. Initialize partially-filled MEDDIC qualification using business pain
    db_execute('''
        INSERT INTO meddic_qualifications (
            entity_type, entity_id, metrics_identified, metrics_note, economic_buyer_identified, decision_process_known,
            primary_pain, business_challenge, pain_severity, pain_validated, champion_identified, score, updated_by, created_at, updated_at
        ) VALUES ('opportunity', ?, 0, '', 0, 0, ?, ?, 'Medium', 1, 0, 20, ?, ?, ?)
    ''', (opp_id, contact['mom'] or 'Captured Business Pain', contact['notes'] or 'MOM notes', sales_manager_id, now_str, now_str))
    
    db_execute("UPDATE opportunities SET meddic_score = 20 WHERE id = ?", (opp_id,))
    
    # 5. Update SQL Review entry
    db_execute('''
        UPDATE telecrm_sql_reviews
        SET review_status = 'Approved',
            reviewed_by = ?,
            reviewed_at = ?,
            assigned_sales_manager_id = ?,
            created_opportunity_id = ?,
            notes = ?
        WHERE id = ?
    ''', (user['id'], now_str, sales_manager_id, opp_id, notes, review_id))
    
    # 6. Update TeleCRM Contact
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Approved',
            dialing_status = 'SQL Marked',
            converted_opportunity_id = ?,
            account_id = ?,
            contact_id = ?,
            lead_id = ?,
            is_finalized = 1,
            updated_at = ?
        WHERE id = ?
    ''', (opp_id, account_id, core_contact_id, lead_id, now_str, contact_id))
    
    # 7. Log timeline & tasks
    log_timeline_activity('telecrm_contact', contact_id, 'SQL approved', "SQL Handoff approved by Manager", f"Assigned sales manager ID: {sales_manager_id}", user['id'])
    log_timeline_activity('opportunity', opp_id, 'SQL Handoff', "SQL converted from TeleCRM calling", f"Telecaller notes: {contact['notes']}", user['id'])
    
    # Create follow-up task for Sales Manager due next business day
    tomorrow = datetime.utcnow() + timedelta(days=1)
    if tomorrow.weekday() >= 5:
        tomorrow = tomorrow + timedelta(days=7 - tomorrow.weekday())
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    db_execute('''
        INSERT INTO crm_tasks (
            title, description, task_type, related_entity_type, related_entity_id, lead_id, opportunity_id, telecrm_contact_id,
            assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at
        ) VALUES (?, ?, 'SQL Follow-up', 'opportunity', ?, ?, ?, ?, ?, ?, ?, '10:00', 'High', 'Open', ?, ?)
    ''', ("Follow up on SQL from TeleCRM", f"Discovery call scheduled. MOM: {contact['mom']}", opp_id, lead_id, opp_id, contact_id, sales_manager_id, user['id'], tomorrow_str, now_str, now_str))
    
    # Update Daily Stats for the telecaller who submitted it
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    update_user_daily_stat(review['submitted_by'], review['campaign_id'], date_str, {'sqls': 1, 'conversions': 1})
    
    update_campaign_completion_stats(review['campaign_id'])
    return jsonify({'status': 'success', 'opportunity_id': opp_id})


@crm_bp.route('/api/telecrm/sql-review/<int:review_id>/reject', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager')
def api_reject_sql(review_id):
    data = request.json or {}
    reason = data.get('rejection_reason')
    
    if not reason:
        return jsonify({'status': 'error', 'message': 'Rejection reason is required.'}), 400
        
    review = db_query_one("SELECT * FROM telecrm_sql_reviews WHERE id = ?", (review_id,))
    if not review:
        return jsonify({'status': 'error', 'message': 'SQL review entry not found.'}), 404
        
    user = g.crm_user
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Update SQL review
    db_execute('''
        UPDATE telecrm_sql_reviews
        SET review_status = 'Rejected',
            reviewed_by = ?,
            reviewed_at = ?,
            rejection_reason = ?
        WHERE id = ?
    ''', (user['id'], now_str, reason, review_id))
    
    # Update Contact
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'SQL Rejected',
            dialing_status = 'Meeting Completed',
            updated_at = ?
        WHERE id = ?
    ''', (now_str, review['telecrm_contact_id']))
    
    log_timeline_activity('telecrm_contact', review['telecrm_contact_id'], 'SQL rejected', 
                          f"SQL submission rejected by Manager. Reason: {reason}", "", user['id'])
                          
    update_campaign_completion_stats(review['campaign_id'])
    return jsonify({'status': 'success'})


@crm_bp.route('/api/telecrm/sql-review/<int:review_id>/return', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager', 'Manager / Sales Manager')
def api_return_sql(review_id):
    data = request.json or {}
    notes = data.get('notes', '')
    
    review = db_query_one("SELECT * FROM telecrm_sql_reviews WHERE id = ?", (review_id,))
    if not review:
        return jsonify({'status': 'error', 'message': 'SQL review entry not found.'}), 404
        
    user = g.crm_user
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Update SQL review
    db_execute('''
        UPDATE telecrm_sql_reviews
        SET review_status = 'Returned',
            reviewed_by = ?,
            reviewed_at = ?,
            notes = ?
        WHERE id = ?
    ''', (user['id'], now_str, notes, review_id))
    
    # Update Contact
    db_execute('''
        UPDATE telecrm_contacts
        SET sql_status = 'Not SQL',
            dialing_status = 'Meeting Completed',
            updated_at = ?
        WHERE id = ?
    ''', (now_str, review['telecrm_contact_id']))
    
    log_timeline_activity('telecrm_contact', review['telecrm_contact_id'], 'SQL returned', 
                          f"SQL submission returned for more information: {notes}", "", user['id'])
                          
    update_campaign_completion_stats(review['campaign_id'])
    return jsonify({'status': 'success'})

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
