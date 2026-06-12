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
