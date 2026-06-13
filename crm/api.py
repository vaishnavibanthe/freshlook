from flask import request, jsonify, g, session, current_app, flash, redirect, url_for
from datetime import datetime, timedelta
import csv
import io
import json
import sqlite3
from crm import crm_bp
from crm.auth import crm_login_required, role_required
from crm.models import db_query, db_query_one, db_execute, log_timeline_activity
from crm.utils import check_duplicates, allocate_contacts_to_telecallers

# In-memory IP rate limiting for lead capture endpoint: {ip: [timestamps]}
LEAD_RATE_LIMITS = {}

PERSONAL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'msn.com',
    'comcast.net', 'icloud.com', 'live.com', 'mail.com', 'gmx.com', 'yandex.com', 'zoho.com'
}

# ----------------------------------------------------
# Public Rate-Limited Lead Capture Endpoint
# ----------------------------------------------------
@crm_bp.route('/api/crm/capture-lead', methods=['POST'])
def capture_lead():
    # 1. Rate Limiting Check (Max 5 submissions per minute per IP)
    ip = request.remote_addr or 'unknown'
    now = datetime.utcnow()
    
    if ip not in LEAD_RATE_LIMITS:
        LEAD_RATE_LIMITS[ip] = []
        
    # Filter out timestamps older than 60 seconds
    LEAD_RATE_LIMITS[ip] = [ts for ts in LEAD_RATE_LIMITS[ip] if now - ts < timedelta(seconds=60)]
    
    if len(LEAD_RATE_LIMITS[ip]) >= 5:
        return jsonify({'status': 'error', 'message': 'Too many requests. Please try again later.'}), 429
        
    LEAD_RATE_LIMITS[ip].append(now)
    
    # 2. Extract settings
    settings = db_query_one("SELECT careers_capture_enabled, default_group_id, default_sql_owner_id FROM crm_settings LIMIT 1")
    careers_enabled = settings['careers_capture_enabled'] if settings else 0
    default_group = settings['default_group_id'] if settings else 1
    default_owner = settings['default_sql_owner_id'] if settings else 1
    
    # Check if this is a career application
    source_form = request.form.get('source_form', '')
    if 'career' in source_form.lower() or 'job' in source_form.lower():
        if not careers_enabled:
            return jsonify({'status': 'success', 'message': 'Application received (not forwarded to CRM).'})
            
    # Extract lead details
    email = request.form.get('business_email', request.form.get('email', '')).strip().lower()
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    full_name = request.form.get('full_name', f"{first_name} {last_name}".strip())
    company = request.form.get('company', '')
    phone = request.form.get('phone', '')
    job_title = request.form.get('job_title', '')
    geography = request.form.get('geography', '')
    country = request.form.get('country', '')
    industry = request.form.get('industry', '')
    message = request.form.get('message', '')
    source_page = request.form.get('source_page', '')
    cta_clicked = request.form.get('cta_clicked', '')
    lead_source = request.form.get('lead_source', 'Website')
    consent_status = 1 if request.form.get('consent') == 'yes' or request.form.get('consent') == '1' else 0
    
    # UTM parameters
    utm_source = request.form.get('utm_source', '')
    utm_medium = request.form.get('utm_medium', '')
    utm_campaign = request.form.get('utm_campaign', '')
    utm_term = request.form.get('utm_term', '')
    utm_content = request.form.get('utm_content', '')
    referrer = request.form.get('referrer', '')
    user_agent = request.headers.get('User-Agent', '')
    
    if not email or not full_name:
        return jsonify({'status': 'error', 'message': 'Email and name are required.'}), 400
        
    # Email domain check
    domain = email.split('@')[1] if '@' in email else ''
    if domain in PERSONAL_DOMAINS:
        return jsonify({'status': 'error', 'message': 'Please use a valid corporate/business email address.'}), 400

    # 3. Determine List Name based on form rules
    # Healthcare forms → Healthcare Microsite Leads, etc.
    form_lower = source_form.lower()
    list_name = 'Website Contact Leads'
    
    if 'healthcare' in form_lower:
        list_name = 'Healthcare Microsite Leads'
    elif 'manufacturing' in form_lower:
        list_name = 'Manufacturing Microsite Leads'
    elif 'bfsi' in form_lower or 'bank' in form_lower:
        list_name = 'BFSI Microsite Leads'
    elif 'retail' in form_lower:
        list_name = 'Retail Microsite Leads'
    elif 'case study' in form_lower or 'download' in form_lower:
        list_name = 'Case Study Downloads'
    elif 'readiness' in form_lower or 'assessment' in form_lower:
        list_name = 'Data Readiness Assessment Leads'
    elif 'webinar' in form_lower or 'resource' in form_lower:
        list_name = 'Resource Leads'
        
    # Fetch list ID
    list_row = db_query_one("SELECT id FROM lead_lists WHERE name = ?", (list_name,))
    list_id = list_row['id'] if list_row else 1
    
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    
    # 4. Insert into Core CRM Leads table
    lead_id = db_execute('''
        INSERT INTO leads (
            first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
            website, lead_source, source_form, source_page, cta_clicked, lead_list_id, owner_id, group_id, status,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
        domain, lead_source, source_form, source_page, cta_clicked, list_id, default_owner, default_group,
        utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip, user_agent, consent_status, now_str, now_str
    ))
    
    # Initialize MEDDIC profile
    db_execute("INSERT INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('lead', ?, ?, ?)", (lead_id, now_str, now_str))
    
    log_timeline_activity('lead', lead_id, 'Website lead captured', f"Lead captured from form: {source_form}", f"Source page: {source_page}", default_owner)
    
    return jsonify({'status': 'success', 'message': 'Lead captured successfully.'})

# ----------------------------------------------------
# TeleCRM Importer with Duplicate Check Preview
# ----------------------------------------------------
@crm_bp.route('/api/admin/telecrm/import-preview', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_import_preview():
    uploaded_file = request.files.get('upload_file')
    if not uploaded_file:
        return jsonify({'status': 'error', 'message': 'No file uploaded.'}), 400
        
    filename = uploaded_file.filename
    content = ""
    
    # Read sheets
    if filename.endswith('.csv'):
        # Parse CSV
        stream = io.StringIO(uploaded_file.stream.read().decode("utf-8"), newline=None)
        reader = csv.DictReader(stream)
        rows = list(reader)
    elif filename.endswith('.xlsx'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(uploaded_file)
            sheet = wb.active
            rows = []
            headers = [cell.value for cell in sheet[1]]
            for row_cells in sheet.iter_rows(min_row=2, values_only=True):
                if any(row_cells): # skip empty rows
                    row_dict = dict(zip(headers, row_cells))
                    rows.append(row_dict)
        except ImportError:
            return jsonify({'status': 'error', 'message': 'To upload .xlsx files, the openpyxl library is required. Please install it with "pip install openpyxl" or export your sheet as a CSV file to upload.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Excel parsing error: {e}'}), 400
    else:
        return jsonify({'status': 'error', 'message': 'Unsupported file format. Please upload CSV or XLSX.'}), 400

    # Parse rows and perform duplicate scan
    conn = sqlite3.connect('blog.db', timeout=30.0)
    conn.row_factory = sqlite3.Row
    
    scanned_rows = []
    duplicate_count = 0
    invalid_count = 0
    valid_rows = []
    
    for idx, row in enumerate(rows):
        # Extract fields matching headers (handles various capitalizations)
        def get_field(keys_list, default=""):
            for k in keys_list:
                for row_key in row.keys():
                    if row_key and row_key.strip().lower() == k.lower():
                        return str(row.get(row_key) or "").strip()
            return default

        first_name = get_field(['first name', 'firstname', 'first_name'])
        last_name = get_field(['last name', 'lastname', 'last_name'])
        full_name = get_field(['full name', 'fullname', 'full_name', 'name'], f"{first_name} {last_name}".strip())
        email = get_field(['email', 'business email', 'business_email', 'email address'])
        phone = get_field(['phone', 'phone number', 'phonenumber', 'telephone'])
        company = get_field(['company', 'company name', 'companyname', 'organization'])
        job_title = get_field(['job title', 'jobtitle', 'job_title', 'role'])
        geography = get_field(['geography', 'region', 'geo'])
        country = get_field(['country'])
        industry = get_field(['industry'])
        website = get_field(['website', 'domain', 'website url'])
        linkedin = get_field(['linkedin', 'linkedin profile', 'linkedin_profile'])
        alternate_phone = get_field(['alternate phone', 'alternate_phone', 'office phone', 'office number', 'officenumber', 'alternate_number'])
        notes = get_field(['notes', 'message', 'comment'])
        
        # Validation
        if not email and not phone:
            invalid_count += 1
            scanned_rows.append({
                'row_index': idx + 1,
                'full_name': full_name,
                'email': email,
                'phone': phone,
                'company': company,
                'status': 'Invalid (No Email or Phone)',
                'duplicates': []
            })
            continue
            
        # Check duplicates
        dups = check_duplicates(conn, email, phone, company, first_name, last_name)
        status_str = 'Valid'
        if dups:
            duplicate_count += 1
            status_str = 'Duplicate'
            
        scanned_row = {
            'row_index': idx + 1,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name or email.split('@')[0],
            'email': email,
            'phone': phone,
            'company': company,
            'job_title': job_title,
            'geography': geography,
            'country': country,
            'industry': industry,
            'website': website,
            'linkedin_profile': linkedin,
            'alternate_phone': alternate_phone,
            'notes': notes,
            'status': status_str,
            'duplicates': dups
        }
        scanned_rows.append(scanned_row)
        if status_str == 'Valid':
            valid_rows.append(scanned_row)
            
    conn.close()
    
    # Store parsed data in session temporarily for import confirmation
    session['telecrm_import_preview_rows'] = scanned_rows
    
    return jsonify({
        'status': 'success',
        'total_rows': len(rows),
        'new_count': len(valid_rows),
        'duplicate_count': duplicate_count,
        'invalid_count': invalid_count,
        'preview_rows': scanned_rows[:100] # return first 100 for display
    })

# Final import commit route
@crm_bp.route('/api/admin/telecrm/lists/confirm-import', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def telecrm_confirm_import():
    list_name = request.form.get('list_name')
    campaign_name = request.form.get('campaign_name')
    product_solution_id = request.form.get('product_solution_id') or None
    partner_id = request.form.get('partner_id') or None
    geography = request.form.get('geography')
    industry = request.form.get('industry')
    lead_source = request.form.get('lead_source', 'Import')
    dup_action = request.form.get('duplicate_action', 'Skip') # Skip, Overwrite, Keep Both
    
    # Percentage allocation maps
    allocation_input = request.form.get('allocation_json') # e.g. '{"5": 40, "6": 60}'
    
    rows = session.get('telecrm_import_preview_rows')
    if not rows:
        flash("No upload session found. Please upload file first.", "error")
        return redirect(url_for('crm.telecrm_import_page'))
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    group_id = g.crm_user['group_id']
    
    # Create TeleCRMList
    list_id = db_execute('''
        INSERT INTO telecrm_lists (name, campaign_name, description, geography, industry, lead_source, product_solution_id, partner_id, uploaded_by, group_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?, ?)
    ''', (list_name, campaign_name, f"Imported list {list_name}", geography, industry, lead_source, product_solution_id, partner_id, user_id, group_id, now_str, now_str))

    imported_count = 0
    skipped_count = 0
    duplicate_count = 0
    overwritten_count = 0
    
    conn = sqlite3.connect('blog.db', timeout=30.0)
    conn.row_factory = sqlite3.Row
    
    contact_ids = []
    
    for r in rows:
        email = r['email']
        phone = r['phone']
        
        if r['status'] == 'Invalid (No Email or Phone)':
            skipped_count += 1
            continue
            
        # Check duplicate again (thread safety)
        dups = check_duplicates(conn, email, phone, r['company'], r['first_name'], r['last_name'])
        
        is_dup = len(dups) > 0
        if is_dup:
            duplicate_count += 1
            if dup_action == 'Skip':
                skipped_count += 1
                continue
            elif dup_action == 'Overwrite':
                # Update existing telecrm contact if exists, otherwise overwrite leads
                t_con = conn.execute("SELECT id FROM telecrm_contacts WHERE email = ? OR phone = ?", (email, phone)).fetchone()
                if t_con:
                    conn.execute('''
                        UPDATE telecrm_contacts 
                        SET first_name=?, last_name=?, full_name=?, company=?, alternate_phone=?, job_title=?, geography=?, country=?, industry=?, website=?, linkedin_profile=?, notes=?, updated_at=?
                        WHERE id = ?
                    ''', (r['first_name'], r['last_name'], r['full_name'], r['company'], r.get('alternate_phone', ''), r['job_title'], r['geography'], r['country'], r['industry'], r['website'], r['linkedin_profile'], r['notes'], now_str, t_con['id']))
                    contact_ids.append(t_con['id'])
                    overwritten_count += 1
                    continue
                    
        # Insert new TeleCRMContact
        contact_id = conn.execute('''
            INSERT INTO telecrm_contacts (
                telecrm_list_id, first_name, last_name, full_name, company, email, phone, alternate_phone, job_title, geography, country, industry, website, linkedin_profile,
                group_id, product_solution_id, partner_id, dialing_status, contact_validation_status, meeting_status, sql_status, notes, source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Not Dialed', 'Not Validated', 'Not Required', 'Not SQL', ?, ?, ?, ?)
        ''', (
            list_id, r['first_name'], r['last_name'], r['full_name'], r['company'], email, phone, r.get('alternate_phone', ''), r['job_title'], r['geography'], r['country'], r['industry'], r['website'], r['linkedin_profile'],
            group_id, product_solution_id, partner_id, r['notes'], 'Import', now_str, now_str
        )).lastrowid
        
        contact_ids.append(contact_id)
        imported_count += 1
        
    conn.commit()
    conn.close()
    
    # 5. Handle Allocations if requested
    if allocation_input:
        try:
            allocation_map = json.loads(allocation_input)
            # convert keys to int
            allocation_map = {int(k): int(v) for k, v in allocation_map.items()}
            assignments = allocate_contacts_to_telecallers(contact_ids, allocation_map)
            
            # Update database
            for cid, caller_id in assignments.items():
                db_execute("UPDATE telecrm_contacts SET assigned_telecaller_id = ?, updated_at = ? WHERE id = ?", (caller_id, now_str, cid))
                # Create timeline activity for assign
                log_timeline_activity('telecrm_contact', cid, 'TeleCRM contact assigned', f"Assigned to telecaller", f"Assigned to User ID: {caller_id}", user_id)
                
            # Log allocation log details
            for caller_id, pct in allocation_map.items():
                assigned_cnt = sum(1 for cid, cl_id in assignments.items() if cl_id == caller_id)
                db_execute('''
                    INSERT INTO telecrm_allocation_logs (telecrm_list_id, allocated_by, telecaller_id, allocation_percentage, assigned_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (list_id, user_id, caller_id, pct, assigned_cnt, now_str))
                
        except Exception as e:
            flash(f"Error executing allocations: {e}", "warning")

    # Update counts on TeleCRMList
    db_execute('''
        UPDATE telecrm_lists 
        SET total_contacts = ?, duplicate_count = ?, assigned_count = ?, updated_at = ?
        WHERE id = ?
    ''', (imported_count + overwritten_count, duplicate_count, len(contact_ids), now_str, list_id))
    
    # Write Import Log
    db_execute('''
        INSERT INTO telecrm_import_logs (telecrm_list_id, file_name, uploaded_by, duplicate_action, total_rows, imported_rows, duplicate_rows, skipped_rows, failed_rows, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    ''', (list_id, list_name, user_id, dup_action, len(rows), imported_count, duplicate_count, skipped_count, now_str))
    
    # Clear temp preview data from session
    session.pop('telecrm_import_preview_rows', None)
    
    flash(f"Import complete: {imported_count} contacts added, {overwritten_count} updated, {skipped_count} skipped.", "success")
    return redirect(url_for('crm.telecrm_campaign_detail', campaign_id=list_id))

# ----------------------------------------------------
# Allocation API for existing lists
# ----------------------------------------------------
@crm_bp.route('/api/admin/telecrm/lists/<int:list_id>/allocate', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Telecaller Manager')
def allocate_list_contacts(list_id):
    data = request.get_json()
    allocation_map = data.get('allocation') # dict of {caller_id: percentage}
    
    if not allocation_map:
        return jsonify({'status': 'error', 'message': 'No allocation map provided.'}), 400
        
    # convert keys to int
    allocation_map = {int(k): int(v) for k, v in allocation_map.items()}
    
    # Fetch unassigned contacts in the list
    contacts = db_query("SELECT id FROM telecrm_contacts WHERE telecrm_list_id = ? AND assigned_telecaller_id IS NULL", (list_id,))
    if not contacts:
        # fetch all contacts in list to reallocate
        contacts = db_query("SELECT id FROM telecrm_contacts WHERE telecrm_list_id = ?", (list_id,))
        
    contact_ids = [c['id'] for c in contacts]
    if not contact_ids:
        return jsonify({'status': 'error', 'message': 'No contacts found to allocate.'}), 400
        
    assignments = allocate_contacts_to_telecallers(contact_ids, allocation_map)
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    for cid, caller_id in assignments.items():
        db_execute("UPDATE telecrm_contacts SET assigned_telecaller_id = ?, updated_at = ? WHERE id = ?", (caller_id, now_str, cid))
        log_timeline_activity('telecrm_contact', cid, 'TeleCRM contact assigned', f"Assigned to telecaller", f"Assigned to User ID: {caller_id}", user_id)
        
    # Save allocation logs
    for caller_id, pct in allocation_map.items():
        assigned_cnt = sum(1 for cid, cl_id in assignments.items() if cl_id == caller_id)
        db_execute('''
            INSERT INTO telecrm_allocation_logs (telecrm_list_id, allocated_by, telecaller_id, allocation_percentage, assigned_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (list_id, user_id, caller_id, pct, assigned_cnt, now_str))
        
    # Update assigned count
    assigned_total = db_query_one("SELECT COUNT(*) as cnt FROM telecrm_contacts WHERE telecrm_list_id = ? AND assigned_telecaller_id IS NOT NULL", (list_id,))['cnt']
    db_execute("UPDATE telecrm_lists SET assigned_count = ?, updated_at = ? WHERE id = ?", (assigned_total, now_str, list_id))
    
    return jsonify({'status': 'success', 'allocated_count': len(assignments)})

# ============================================================
#  WEBSITE LEADS STAGING MODULE - PUBLIC CAPTURE & CRM APIs
# ============================================================

# 1. Public Rate-Limited & Honeypot-Protected Staging Capture
@crm_bp.route('/api/website-leads/capture', methods=['POST'])
def capture_website_lead():
    # A. Rate Limiting Check (Max 5 submissions per minute per IP)
    ip = request.remote_addr or 'unknown'
    now = datetime.utcnow()
    
    if ip not in LEAD_RATE_LIMITS:
        LEAD_RATE_LIMITS[ip] = []
        
    LEAD_RATE_LIMITS[ip] = [ts for ts in LEAD_RATE_LIMITS[ip] if now - ts < timedelta(seconds=60)]
    if len(LEAD_RATE_LIMITS[ip]) >= 5:
        return jsonify({'status': 'error', 'message': 'Too many requests. Please try again later.'}), 429
        
    LEAD_RATE_LIMITS[ip].append(now)
    
    # B. Honeypot Spam Check
    honeypot = request.form.get('honeypot', '').strip()
    is_spam = bool(honeypot) # If honeypot is filled, it's a bot submission!
    
    # Extract fields
    email = request.form.get('business_email', request.form.get('email', '')).strip().lower()
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    full_name = request.form.get('full_name', f"{first_name} {last_name}".strip()).strip()
    company = request.form.get('company', '').strip()
    phone = request.form.get('phone', '').strip()
    job_title = request.form.get('job_title', '').strip()
    geography = request.form.get('geography', '').strip()
    country = request.form.get('country', '').strip()
    industry = request.form.get('industry', '').strip()
    message = request.form.get('message', '').strip()
    source_form = request.form.get('source_form', '').strip()
    source_page = request.form.get('source_page', '').strip()
    cta_clicked = request.form.get('cta_clicked', '').strip()
    consent_status = 1 if request.form.get('consent') in ('yes', '1', 'on') else 0
    
    # UTM and extra fields
    utm_source = request.form.get('utm_source', '').strip()
    utm_medium = request.form.get('utm_medium', '').strip()
    utm_campaign = request.form.get('utm_campaign', '').strip()
    utm_term = request.form.get('utm_term', '').strip()
    utm_content = request.form.get('utm_content', '').strip()
    referrer = request.form.get('referrer', '').strip()
    user_agent = request.headers.get('User-Agent', '')
    
    # Extra staging fields
    product_solution_interest = request.form.get('product_solution_interest', request.form.get('product_interest', '')).strip()
    partner_interest = request.form.get('partner_interest', request.form.get('partner', '')).strip()
    case_study_downloaded = request.form.get('case_study_downloaded', '').strip()
    resource_downloaded = request.form.get('resource_downloaded', '').strip()
    assessment_type = request.form.get('assessment_type', '').strip()
    
    if not email or not full_name:
        return jsonify({'status': 'error', 'message': 'Email and name are required.'}), 400
        
    is_career = 'career' in source_form.lower() or 'job' in source_form.lower()
    
    # Reject personal domains for corporate forms (unless career submission)
    if not is_career:
        domain = email.split('@')[1] if '@' in email else ''
        if domain in PERSONAL_DOMAINS:
            return jsonify({'status': 'error', 'message': 'Please use a valid corporate/business email address.'}), 400
            
    # Forward lead to crm helper
    from crm.models import forward_lead_to_crm, log_website_lead_review_log
    
    lead_id = forward_lead_to_crm(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone,
        job_title=job_title, geography=geography, country=country, industry=industry, message=message,
        source_form=source_form, source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign,
        utm_term=utm_term, utm_content=utm_content, referrer=referrer, ip_address=ip, user_agent=user_agent,
        consent_status=consent_status,
        product_solution_interest=product_solution_interest, partner_interest=partner_interest,
        case_study_downloaded=case_study_downloaded, resource_downloaded=resource_downloaded,
        assessment_type=assessment_type
    )
    
    if is_spam and lead_id and not is_career:
        # Update lead status to Spam immediately if honeypot was filled
        db_execute(
            "UPDATE website_leads SET status = 'Spam', duplicate_status = 'Spam Filtered', spam_marked_at = ?, spam_marked_by = NULL WHERE id = ?",
            (now.strftime('%Y-%m-%d %H:%M:%S'), lead_id)
        )
        log_website_lead_review_log(
            website_lead_id=lead_id,
            action_type='Marked Spam',
            description="Automatically flagged as Spam via honeypot spam protection.",
            previous_status='New',
            new_status='Spam'
        )
        
    return jsonify({'status': 'success', 'message': 'Submission received successfully.', 'lead_id': lead_id})

# Helper to get visibility filter based on user role for website leads
def get_website_leads_visibility_clause(table_prefix="wl"):
    role = g.crm_user.get('role')
    user_id = g.crm_user.get('id')
    group_id = g.crm_user.get('group_id')
    
    p = f"{table_prefix}." if table_prefix else ""
    
    if role == 'Platform Admin':
        return "1=1", []
    elif role in ('Group Admin', 'Sales Head'):
        # Can view assigned to group or unassigned leads
        return f"({p}assigned_owner_id IS NULL OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?))", [group_id]
    elif role == 'Manager / Sales Manager':
        # Can view assigned to self/team or unassigned leads in group
        return f"({p}assigned_owner_id = ? OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?) OR ({p}assigned_owner_id IS NULL AND {p}geography IN (SELECT geography FROM crm_users WHERE id = ?)))", [user_id, user_id, user_id]
    elif role == 'Sales User':
        # Sales users see after assigned
        return f"{p}assigned_owner_id = ?", [user_id]
    else:
        return "1=0", []

# 2. CRM Website Leads JSON APIs
@crm_bp.route('/api/crm/website-leads', methods=['GET'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User')
def api_website_leads():
    where_clause, params = get_website_leads_visibility_clause("wl")
    
    status = request.args.get('status')
    source_form = request.args.get('source_form')
    industry = request.args.get('industry')
    
    filters = []
    if status:
        filters.append("wl.status = ?")
        params.append(status)
    if source_form:
        filters.append("wl.source_form = ?")
        params.append(source_form)
    if industry:
        filters.append("wl.industry = ?")
        params.append(industry)
        
    if filters:
        where_clause += " AND " + " AND ".join(filters)
        
    query = f'''
        SELECT wl.*, u.name as owner_name 
        FROM website_leads wl
        LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id
        WHERE {where_clause}
        ORDER BY wl.id DESC
    '''
    leads = db_query(query, params)
    return jsonify({'status': 'success', 'data': leads})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>', methods=['GET'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User')
def api_website_lead_detail(lead_id):
    lead = db_query_one("SELECT wl.*, u.name as owner_name FROM website_leads wl LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id WHERE wl.id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    logs = db_query("SELECT l.*, u.name as performed_by_name FROM website_lead_review_logs l LEFT JOIN crm_users u ON l.performed_by = u.id WHERE l.website_lead_id = ? ORDER BY l.id DESC", (lead_id,))
    return jsonify({'status': 'success', 'data': lead, 'review_logs': logs})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>', methods=['PUT'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_update_website_lead(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    review_notes = data.get('review_notes')
    status = data.get('status')
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    if status and status != lead['status']:
        from crm.models import log_website_lead_review_log
        db_execute("UPDATE website_leads SET status = ?, updated_at = ? WHERE id = ?", (status, now_str, lead_id))
        log_website_lead_review_log(
            website_lead_id=lead_id,
            action_type='Status changed',
            description=f"Updated status to {status}",
            previous_status=lead['status'],
            new_status=status,
            performed_by=user_id
        )
        
    if review_notes is not None:
        db_execute("UPDATE website_leads SET review_notes = ?, updated_at = ? WHERE id = ?", (review_notes, now_str, lead_id))
        
    return jsonify({'status': 'success', 'message': 'Lead updated successfully.'})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/assign-owner', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_assign_lead_owner(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    owner_id = data.get('owner_id')
    
    if not owner_id:
        return jsonify({'status': 'error', 'message': 'owner_id is required.'}), 400
        
    # Check if selected owner exists and is active
    owner = db_query_one("SELECT id, name FROM crm_users WHERE id = ? AND is_active = 1", (owner_id,))
    if not owner:
        return jsonify({'status': 'error', 'message': 'Owner is invalid or inactive.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    previous_owner_id = lead['assigned_owner_id']
    previous_status = lead['status']
    new_status = 'Assigned' if lead['status'] == 'New' else lead['status']
    
    db_execute("UPDATE website_leads SET assigned_owner_id = ?, status = ?, updated_at = ? WHERE id = ?", (owner_id, new_status, now_str, lead_id))
    
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Owner assigned',
        description=f"Assigned owner to {owner['name']}",
        previous_status=previous_status,
        new_status=new_status,
        previous_owner_id=previous_owner_id,
        new_owner_id=owner_id,
        performed_by=user_id
    )
    
    return jsonify({'status': 'success', 'message': f"Assigned to {owner['name']} successfully."})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/convert-to-contact', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_convert_lead_to_contact(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    owner_id = data.get('owner_id')
    ignore_duplicates = data.get('ignore_duplicates', False)
    create_account = data.get('create_account', False)
    create_opportunity = data.get('create_opportunity', False)
    opportunity_name = data.get('opportunity_name')
    estimated_value = data.get('estimated_value', 0.0)
    
    if not owner_id:
        return jsonify({'status': 'error', 'message': 'Owner assignment is required.'}), 400
        
    owner = db_query_one("SELECT id, group_id FROM crm_users WHERE id = ? AND is_active = 1", (owner_id,))
    if not owner:
        return jsonify({'status': 'error', 'message': 'Selected owner is invalid or inactive.'}), 400
        
    from crm.models import detect_contact_duplicates, log_website_lead_review_log
    
    # Check duplicates
    if not ignore_duplicates:
        duplicates = detect_contact_duplicates(
            email=lead['business_email'],
            phone=lead['phone'],
            company=lead['company'],
            first_name=lead['first_name'],
            last_name=lead['last_name']
        )
        if duplicates:
            return jsonify({
                'status': 'warning',
                'message': 'Possible duplicates found.',
                'duplicates': duplicates
            }), 200
            
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    group_id = owner['group_id']
    
    domain = ""
    if lead['business_email'] and '@' in lead['business_email']:
        domain = lead['business_email'].split('@')[1].lower().strip()
        
    # Check if we should create/link an Account
    account_id = None
    if create_account and lead['company']:
        acct = db_query_one("SELECT id FROM accounts WHERE LOWER(account_name) = ? OR (domain = ? AND domain != '')", (lead['company'].lower().strip(), domain))
        if acct:
            account_id = acct['id']
        else:
            account_id = db_execute('''
                INSERT INTO accounts (account_name, website, domain, industry, geography, country, owner_id, group_id, source, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead['company'], lead['source_page'], domain, lead['industry'], lead['geography'], lead['country'],
                owner_id, group_id, 'Website Lead', f"Created from Website Lead conversion. Notes: {lead['message']}", now_str, now_str
            ))
            log_timeline_activity('account', account_id, 'Account created', f"Account {lead['company']} created", "Converted from Website Lead", user_id)
            
    # Create Contact
    contact_id = db_execute('''
        INSERT INTO contacts (
            account_id, first_name, last_name, full_name, email, phone, job_title, geography, country, 
            source, validation_status, consent_status, created_at, updated_at,
            source_website_lead_id, source_form, source_page, cta_clicked,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, owner_id, group_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Website', 'Not Validated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        account_id, lead['first_name'], lead['last_name'], lead['full_name'], lead['business_email'], lead['phone'],
        lead['job_title'], lead['geography'], lead['country'], lead['consent_status'], now_str, now_str,
        lead_id, lead['source_form'], lead['source_page'], lead['cta_clicked'],
        lead['utm_source'], lead['utm_medium'], lead['utm_campaign'], lead['utm_term'], lead['utm_content'], lead['referrer'],
        owner_id, group_id
    ))
    
    log_timeline_activity('contact', contact_id, 'Contact created', f"Contact {lead['full_name']} created", "Created from Website Lead", user_id)
    db_execute("INSERT OR IGNORE INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('contact', ?, ?, ?)", (contact_id, now_str, now_str))
    
    # Log timeline entry: “Created from Website Lead”
    log_timeline_activity('contact', contact_id, 'Created from Website Lead', f"Contact {lead['full_name']} created from Website Lead", f"Source form: {lead['source_form']}", user_id)
    
    if account_id:
        db_execute("UPDATE contacts SET account_id = ? WHERE id = ?", (account_id, contact_id))
        
    # Check if we should create an Opportunity
    if create_opportunity:
        opp_name = opportunity_name or f"{lead['company'] or lead['full_name']} - Opp"
        opp_id = db_execute('''
            INSERT INTO opportunities (
                lead_id, account_id, contact_id, opportunity_name, company, primary_contact_name, primary_contact_email,
                owner_id, group_id, industry, geography, estimated_value, stage, bucket, status, sql_source, created_at, updated_at
            ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Prospecting', 'Prospecting', 'Open', 'Website Lead Conversion', ?, ?)
        ''', (
            account_id, contact_id, opp_name, lead['company'] or lead['full_name'], lead['full_name'], lead['business_email'],
            owner_id, group_id, lead['industry'], lead['geography'], estimated_value, now_str, now_str
        ))
        log_timeline_activity('opportunity', opp_id, 'Opportunity created', f"Opportunity {opp_name} created", "Converted from Website Lead", user_id)
        
    # Update Staging Lead
    db_execute('''
        UPDATE website_leads 
        SET status = 'Converted to Contact', crm_contact_id = ?, converted_at = ?, converted_by = ?, assigned_owner_id = ?, updated_at = ?
        WHERE id = ?
    ''', (contact_id, now_str, user_id, owner_id, now_str, lead_id))
    
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Converted to Contact',
        description=f"Converted Website Lead to Contact ID: {contact_id}",
        previous_status=lead['status'],
        new_status='Converted to Contact',
        previous_owner_id=lead['assigned_owner_id'],
        new_owner_id=owner_id,
        performed_by=user_id,
        metadata_dict={'contact_id': contact_id, 'account_id': account_id}
    )
    
    return jsonify({'status': 'success', 'message': 'Lead successfully converted to Contact.', 'contact_id': contact_id})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/link-existing-contact', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_link_existing_contact(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    contact_id = data.get('contact_id')
    owner_id = data.get('owner_id')
    overwrite = data.get('overwrite', False)
    
    if not contact_id or not owner_id:
        return jsonify({'status': 'error', 'message': 'contact_id and owner_id are required.'}), 400
        
    contact = db_query_one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if not contact:
        return jsonify({'status': 'error', 'message': 'Contact not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    if overwrite:
        # Overwrite contact fields with lead details
        db_execute('''
            UPDATE contacts 
            SET first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name), 
                phone = COALESCE(?, phone), job_title = COALESCE(?, job_title), 
                geography = COALESCE(?, geography), country = COALESCE(?, country),
                source_website_lead_id = ?, source_form = ?, source_page = ?, cta_clicked = ?,
                utm_source = ?, utm_medium = ?, utm_campaign = ?, utm_term = ?, utm_content = ?, referrer = ?,
                owner_id = ?, updated_at = ?
            WHERE id = ?
        ''', (
            lead['first_name'], lead['last_name'], lead['phone'], lead['job_title'], lead['geography'], lead['country'],
            lead_id, lead['source_form'], lead['source_page'], lead['cta_clicked'],
            lead['utm_source'], lead['utm_medium'], lead['utm_campaign'], lead['utm_term'], lead['utm_content'], lead['referrer'],
            owner_id, now_str, contact_id
        ))
    else:
        # Just update link and owner
        db_execute('''
            UPDATE contacts 
            SET source_website_lead_id = ?, owner_id = ?, updated_at = ? 
            WHERE id = ?
        ''', (lead_id, owner_id, now_str, contact_id))
        
    # Update Staging Lead
    db_execute('''
        UPDATE website_leads 
        SET status = 'Converted to Contact', crm_contact_id = ?, converted_at = ?, converted_by = ?, assigned_owner_id = ?, updated_at = ?
        WHERE id = ?
    ''', (contact_id, now_str, user_id, owner_id, now_str, lead_id))
    
    # Log timeline activity on contact
    log_timeline_activity('contact', contact_id, 'Linked to Website Lead', f"Contact linked to Website Lead #{lead_id}", f"Source form: {lead['source_form']}", user_id)
    
    # Log Website Lead review log
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Linked to existing Contact',
        description=f"Linked Website Lead to existing Contact ID: {contact_id} (Overwrote details: {overwrite})",
        previous_status=lead['status'],
        new_status='Converted to Contact',
        previous_owner_id=lead['assigned_owner_id'],
        new_owner_id=owner_id,
        performed_by=user_id,
        metadata_dict={'contact_id': contact_id, 'overwrite': overwrite}
    )
    
    return jsonify({'status': 'success', 'message': 'Lead linked to Contact successfully.'})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/mark-duplicate', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_mark_lead_duplicate(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    notes = data.get('review_notes', 'Marked as duplicate manually.')
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute(
        "UPDATE website_leads SET status = 'Duplicate', review_notes = ?, duplicate_marked_at = ?, duplicate_marked_by = ?, updated_at = ? WHERE id = ?",
        (notes, now_str, user_id, now_str, lead_id)
    )
    
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Marked Duplicate',
        description=notes,
        previous_status=lead['status'],
        new_status='Duplicate',
        performed_by=user_id
    )
    
    return jsonify({'status': 'success', 'message': 'Lead marked as duplicate.'})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/mark-rejected', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_mark_lead_rejected(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    notes = data.get('review_notes', 'Rejected manual qualification.')
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute(
        "UPDATE website_leads SET status = 'Rejected', review_notes = ?, rejected_at = ?, rejected_by = ?, updated_at = ? WHERE id = ?",
        (notes, now_str, user_id, now_str, lead_id)
    )
    
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Marked Rejected',
        description=notes,
        previous_status=lead['status'],
        new_status='Rejected',
        performed_by=user_id
    )
    
    return jsonify({'status': 'success', 'message': 'Lead marked as rejected.'})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/mark-spam', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_mark_lead_spam(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    notes = data.get('review_notes', 'Marked as spam manually.')
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    db_execute(
        "UPDATE website_leads SET status = 'Spam', review_notes = ?, spam_marked_at = ?, spam_marked_by = ?, updated_at = ? WHERE id = ?",
        (notes, now_str, user_id, now_str, lead_id)
    )
    
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Marked Spam',
        description=notes,
        previous_status=lead['status'],
        new_status='Spam',
        performed_by=user_id
    )
    
    return jsonify({'status': 'success', 'message': 'Lead marked as spam.'})

@crm_bp.route('/api/crm/website-leads/<int:lead_id>/review-note', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_add_lead_review_note(lead_id):
    lead = db_query_one("SELECT * FROM website_leads WHERE id = ?", (lead_id,))
    if not lead:
        return jsonify({'status': 'error', 'message': 'Lead not found.'}), 404
        
    data = request.get_json() or {}
    note = data.get('note', '').strip()
    
    if not note:
        return jsonify({'status': 'error', 'message': 'Note text is required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    user_id = g.crm_user['id']
    
    # Append to existing review notes or create
    new_notes = f"{lead['review_notes']}\n[{now_str}] {note}" if lead['review_notes'] else f"[{now_str}] {note}"
    db_execute("UPDATE website_leads SET review_notes = ?, updated_at = ? WHERE id = ?", (new_notes, now_str, lead_id))
    
    from crm.models import log_website_lead_review_log
    log_website_lead_review_log(
        website_lead_id=lead_id,
        action_type='Review note added',
        description=f"Added review note: {note}",
        performed_by=user_id
    )
    
    return jsonify({'status': 'success', 'message': 'Review note added.'})

# ============================================================
#  ADMIN ASSIGNMENT RULES APIs
# ============================================================

@crm_bp.route('/api/admin/crm/website-lead-assignment-rules', methods=['GET'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin')
def api_get_assignment_rules():
    rules = db_query("SELECT r.*, u.name as owner_name, g.name as group_name FROM website_lead_assignment_rules r LEFT JOIN crm_users u ON r.assigned_owner_id = u.id LEFT JOIN crm_groups g ON r.assigned_group_id = g.id ORDER BY r.priority DESC, r.id ASC")
    return jsonify({'status': 'success', 'data': rules})

@crm_bp.route('/api/admin/crm/website-lead-assignment-rules', methods=['POST'])
@crm_login_required
@role_required('Platform Admin')
def api_create_assignment_rule():
    data = request.get_json() or {}
    rule_name = data.get('rule_name')
    priority = int(data.get('priority', 0))
    source_form = data.get('source_form')
    source_page_contains = data.get('source_page_contains')
    geography = data.get('geography')
    industry = data.get('industry')
    product_solution_id = data.get('product_solution_id')
    partner_id = data.get('partner_id')
    assigned_owner_id = data.get('assigned_owner_id')
    assigned_group_id = data.get('assigned_group_id')
    assignment_type = data.get('assignment_type', 'fixed_owner') # fixed_owner, group_queue, round_robin
    is_active = int(data.get('is_active', 1))
    
    if not rule_name or not assignment_type:
        return jsonify({'status': 'error', 'message': 'rule_name and assignment_type are required.'}), 400
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    rule_id = db_execute('''
        INSERT INTO website_lead_assignment_rules (
            rule_name, priority, source_form, source_page_contains, geography, industry,
            product_solution_id, partner_id, assigned_owner_id, assigned_group_id,
            assignment_type, is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        rule_name, priority, source_form, source_page_contains, geography, industry,
        product_solution_id, partner_id, assigned_owner_id, assigned_group_id,
        assignment_type, is_active, now_str, now_str
    ))
    
    return jsonify({'status': 'success', 'message': 'Rule created successfully.', 'rule_id': rule_id})

@crm_bp.route('/api/admin/crm/website-lead-assignment-rules/<int:rule_id>', methods=['PUT'])
@crm_login_required
@role_required('Platform Admin')
def api_update_assignment_rule(rule_id):
    rule = db_query_one("SELECT * FROM website_lead_assignment_rules WHERE id = ?", (rule_id,))
    if not rule:
        return jsonify({'status': 'error', 'message': 'Rule not found.'}), 404
        
    data = request.get_json() or {}
    rule_name = data.get('rule_name', rule['rule_name'])
    priority = int(data.get('priority', rule['priority']))
    source_form = data.get('source_form', rule['source_form'])
    source_page_contains = data.get('source_page_contains', rule['source_page_contains'])
    geography = data.get('geography', rule['geography'])
    industry = data.get('industry', rule['industry'])
    product_solution_id = data.get('product_solution_id', rule['product_solution_id'])
    partner_id = data.get('partner_id', rule['partner_id'])
    assigned_owner_id = data.get('assigned_owner_id', rule['assigned_owner_id'])
    assigned_group_id = data.get('assigned_group_id', rule['assigned_group_id'])
    assignment_type = data.get('assignment_type', rule['assignment_type'])
    is_active = int(data.get('is_active', rule['is_active']))
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    db_execute('''
        UPDATE website_lead_assignment_rules 
        SET rule_name = ?, priority = ?, source_form = ?, source_page_contains = ?, geography = ?, industry = ?,
            product_solution_id = ?, partner_id = ?, assigned_owner_id = ?, assigned_group_id = ?,
            assignment_type = ?, is_active = ?, updated_at = ?
        WHERE id = ?
    ''', (
        rule_name, priority, source_form, source_page_contains, geography, industry,
        product_solution_id, partner_id, assigned_owner_id, assigned_group_id,
        assignment_type, is_active, now_str, rule_id
    ))
    
    return jsonify({'status': 'success', 'message': 'Rule updated successfully.'})

@crm_bp.route('/api/admin/crm/website-lead-assignment-rules/<int:rule_id>', methods=['DELETE'])
@crm_login_required
@role_required('Platform Admin')
def api_delete_assignment_rule(rule_id):
    rule = db_query_one("SELECT * FROM website_lead_assignment_rules WHERE id = ?", (rule_id,))
    if not rule:
        return jsonify({'status': 'error', 'message': 'Rule not found.'}), 404
        
    db_execute("DELETE FROM website_lead_assignment_rules WHERE id = ?", (rule_id,))
    return jsonify({'status': 'success', 'message': 'Rule deleted successfully.'})


# ============================================================
#  WEBSITE LEADS ANALYTICS API
# ============================================================

def get_date_range_bounds(date_filter, start_date_str=None, end_date_str=None):
    import datetime
    now = datetime.datetime.utcnow()
    today = now.date()
    
    start_dt = None
    end_dt = None
    
    if date_filter == 'This Week':
        monday = today - datetime.timedelta(days=today.weekday())
        start_dt = datetime.datetime.combine(monday, datetime.time.min)
        end_dt = now
    elif date_filter == 'Last Week':
        monday = today - datetime.timedelta(days=today.weekday())
        monday_last = monday - datetime.timedelta(days=7)
        sunday_last = monday - datetime.timedelta(days=1)
        start_dt = datetime.datetime.combine(monday_last, datetime.time.min)
        end_dt = datetime.datetime.combine(sunday_last, datetime.time.max)
    elif date_filter == 'This Month':
        first_this_month = today.replace(day=1)
        start_dt = datetime.datetime.combine(first_this_month, datetime.time.min)
        end_dt = now
    elif date_filter == 'Last Month':
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - datetime.timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        start_dt = datetime.datetime.combine(first_prev_month, datetime.time.min)
        end_dt = datetime.datetime.combine(last_prev_month, datetime.time.max)
    elif date_filter == 'This Year':
        first_this_year = today.replace(month=1, day=1)
        start_dt = datetime.datetime.combine(first_this_year, datetime.time.min)
        end_dt = now
    elif date_filter == 'Last Year':
        first_last_year = today.replace(year=today.year - 1, month=1, day=1)
        last_last_year = today.replace(year=today.year - 1, month=12, day=31)
        start_dt = datetime.datetime.combine(first_last_year, datetime.time.min)
        end_dt = datetime.datetime.combine(last_last_year, datetime.time.max)
    elif date_filter == 'Custom' and start_date_str and end_date_str:
        try:
            start_d = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_d = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            start_dt = datetime.datetime.combine(start_d, datetime.time.min)
            end_dt = datetime.datetime.combine(end_d, datetime.time.max)
        except ValueError:
            pass
            
    return start_dt, end_dt

def get_previous_period_bounds(date_filter, start_dt, end_dt):
    import datetime
    if not start_dt or not end_dt:
        return None, None
        
    if date_filter == 'This Week' or date_filter == 'Last Week':
        prev_start = start_dt - datetime.timedelta(days=7)
        prev_end = end_dt - datetime.timedelta(days=7)
    elif date_filter == 'This Month':
        first_this_month = start_dt.date()
        last_prev_month = first_this_month - datetime.timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        prev_start = datetime.datetime.combine(first_prev_month, datetime.time.min)
        elapsed_days = (end_dt.date() - first_this_month).days + 1
        prev_end_date = first_prev_month + datetime.timedelta(days=elapsed_days - 1)
        if prev_end_date > last_prev_month:
            prev_end_date = last_prev_month
        prev_end = datetime.datetime.combine(prev_end_date, end_dt.time())
    elif date_filter == 'Last Month':
        first_prev_month = start_dt.date()
        last_prev_prev_month = first_prev_month - datetime.timedelta(days=1)
        first_prev_prev_month = last_prev_prev_month.replace(day=1)
        prev_start = datetime.datetime.combine(first_prev_prev_month, datetime.time.min)
        prev_end = datetime.datetime.combine(last_prev_prev_month, datetime.time.max)
    elif date_filter == 'This Year' or date_filter == 'Last Year':
        try:
            prev_start = start_dt.replace(year=start_dt.year - 1)
            prev_end = end_dt.replace(year=end_dt.year - 1)
        except ValueError:
            prev_start = start_dt - datetime.timedelta(days=365)
            prev_end = end_dt - datetime.timedelta(days=365)
    else:
        duration = end_dt - start_dt
        prev_end = start_dt - datetime.timedelta(seconds=1)
        prev_start = prev_end - duration
        
    return prev_start, prev_end

@crm_bp.route('/api/crm/website-leads/analytics', methods=['GET'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager')
def api_website_leads_analytics():
    role = g.crm_user.get('role')
    user_id = g.crm_user.get('id')
    group_id = g.crm_user.get('group_id')
    
    date_filter = request.args.get('date_filter', 'This Month')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    product_solution_id = request.args.get('product_solution_id')
    partner_id = request.args.get('partner_id')
    
    product_name = None
    if product_solution_id:
        p_row = db_query_one("SELECT name FROM product_solutions WHERE id = ?", (product_solution_id,))
        if p_row:
            product_name = p_row['name']
            
    partner_name = None
    if partner_id:
        part_row = db_query_one("SELECT name FROM partners WHERE id = ?", (partner_id,))
        if part_row:
            partner_name = part_row['name']
            
    req_group_id = request.args.get('group_id')
    req_owner_id = request.args.get('owner_id')
    source_form = request.args.get('source_form')
    industry = request.args.get('industry')
    geography = request.args.get('geography')
    
    visibility_clause = ""
    visibility_params = []
    if role == 'Platform Admin':
        visibility_clause = "1=1"
    elif role in ('Group Admin', 'Sales Head'):
        visibility_clause = "(wl.assigned_owner_id IS NULL OR wl.assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?))"
        visibility_params.append(group_id)
    elif role == 'Manager / Sales Manager':
        visibility_clause = "(wl.assigned_owner_id = ? OR wl.assigned_owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?) OR (wl.assigned_owner_id IS NULL AND wl.geography IN (SELECT geography FROM crm_users WHERE id = ?)))"
        visibility_params.extend([user_id, user_id, user_id])
    else:
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
        
    filters = []
    if req_group_id:
        if role == 'Platform Admin' or (role in ('Group Admin', 'Sales Head') and int(req_group_id) == group_id):
            filters.append("wl.assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?)")
            visibility_params.append(int(req_group_id))
        else:
            return jsonify({'status': 'error', 'message': 'Permission denied for requested group filter.'}), 403
            
    if req_owner_id:
        owner_val = int(req_owner_id)
        if role == 'Platform Admin':
            filters.append("wl.assigned_owner_id = ?")
            visibility_params.append(owner_val)
        elif role in ('Group Admin', 'Sales Head'):
            filters.append("(wl.assigned_owner_id = ? AND wl.assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?))")
            visibility_params.extend([owner_val, group_id])
        elif role == 'Manager / Sales Manager':
            filters.append("(wl.assigned_owner_id = ? AND (wl.assigned_owner_id = ? OR wl.assigned_owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?)))")
            visibility_params.extend([owner_val, user_id, user_id])
        else:
            return jsonify({'status': 'error', 'message': 'Permission denied for requested owner filter.'}), 403
            
    if source_form:
        filters.append("wl.source_form = ?")
        visibility_params.append(source_form)
    if industry:
        filters.append("wl.industry = ?")
        visibility_params.append(industry)
    if geography:
        filters.append("wl.geography = ?")
        visibility_params.append(geography)
    if product_name:
        filters.append("wl.product_solution_interest = ?")
        visibility_params.append(product_name)
    if partner_name:
        filters.append("wl.partner_interest = ?")
        visibility_params.append(partner_name)
        
    if filters:
        base_clause = visibility_clause + " AND " + " AND ".join(filters)
    else:
        base_clause = visibility_clause
        
    start_dt, end_dt = get_date_range_bounds(date_filter, start_date_str, end_date_str)
    
    def get_counts(s_dt, e_dt, clause, params):
        t_clause = clause
        t_params = list(params)
        if s_dt and e_dt:
            t_clause += " AND wl.created_at >= ? AND wl.created_at <= ?"
            t_params.extend([s_dt.strftime('%Y-%m-%d %H:%M:%S'), e_dt.strftime('%Y-%m-%d %H:%M:%S')])
        total_count = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {t_clause}", t_params)['cnt']
        
        p_clause = clause + " AND wl.status IN ('New', 'Reviewed', 'Assigned')"
        p_params = list(params)
        if s_dt and e_dt:
            p_clause += " AND wl.created_at >= ? AND wl.created_at <= ?"
            p_params.extend([s_dt.strftime('%Y-%m-%d %H:%M:%S'), e_dt.strftime('%Y-%m-%d %H:%M:%S')])
        pending_count = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {p_clause}", p_params)['cnt']
        
        c_clause = clause + " AND wl.status = 'Converted to Contact'"
        c_params = list(params)
        if s_dt and e_dt:
            c_clause += " AND wl.converted_at >= ? AND wl.converted_at <= ?"
            c_params.extend([s_dt.strftime('%Y-%m-%d %H:%M:%S'), e_dt.strftime('%Y-%m-%d %H:%M:%S')])
        converted_count = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {c_clause}", c_params)['cnt']
        
        s_clause = clause + " AND wl.status = 'Spam'"
        s_params = list(params)
        if s_dt and e_dt:
            s_clause += " AND COALESCE(wl.spam_marked_at, wl.created_at) >= ? AND COALESCE(wl.spam_marked_at, wl.created_at) <= ?"
            s_params.extend([s_dt.strftime('%Y-%m-%d %H:%M:%S'), e_dt.strftime('%Y-%m-%d %H:%M:%S')])
        spam_count = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {s_clause}", s_params)['cnt']
        
        conversion_rate = 0.0
        if total_count > 0:
            conversion_rate = round((converted_count / total_count) * 100, 1)
            
        return {
            'total_website_leads': total_count,
            'pending_for_review': pending_count,
            'converted_to_contact': converted_count,
            'spam': spam_count,
            'conversion_rate': conversion_rate
        }

    current_res = get_counts(start_dt, end_dt, base_clause, visibility_params)
    
    trends = None
    if start_dt and end_dt:
        prev_start_dt, prev_end_dt = get_previous_period_bounds(date_filter, start_dt, end_dt)
        if prev_start_dt and prev_end_dt:
            prev_res = get_counts(prev_start_dt, prev_end_dt, base_clause, visibility_params)
            
            def get_trend_pct(curr, prev):
                if prev == 0:
                    return 100 if curr > 0 else 0
                return round(((curr - prev) / prev) * 100, 1)
                
            trends = {
                'total_website_leads': get_trend_pct(current_res['total_website_leads'], prev_res['total_website_leads']),
                'pending_for_review': get_trend_pct(current_res['pending_for_review'], prev_res['pending_for_review']),
                'converted_to_contact': get_trend_pct(current_res['converted_to_contact'], prev_res['converted_to_contact']),
                'spam': get_trend_pct(current_res['spam'], prev_res['spam']),
                'conversion_rate': round(current_res['conversion_rate'] - prev_res['conversion_rate'], 1)
            }
            
    res_payload = {
        'total_website_leads': current_res['total_website_leads'],
        'pending_for_review': current_res['pending_for_review'],
        'converted_to_contact': current_res['converted_to_contact'],
        'spam': current_res['spam'],
        'conversion_rate': current_res['conversion_rate'],
        'date_range_start': start_dt.strftime('%Y-%m-%d %H:%M:%S') if start_dt else None,
        'date_range_end': end_dt.strftime('%Y-%m-%d %H:%M:%S') if end_dt else None,
        'trends': trends
    }
    
    return jsonify(res_payload)


