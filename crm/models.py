import sqlite3
import json
from datetime import datetime

# DB helper connection
def get_db_connection():
    conn = sqlite3.connect('blog.db', timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

# Execute insert/update/delete
def db_execute(query, params=()):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        lastrowid = cursor.lastrowid
        return lastrowid
    except Exception as e:
        print(f"Database execute error: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

# Execute select returning list of dicts
def db_query(query, params=()):
    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        print(f"Database query error: {e}")
        raise e
    finally:
        conn.close()

# Execute select returning single row as dict
def db_query_one(query, params=()):
    conn = get_db_connection()
    try:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Database query one error: {e}")
        raise e
    finally:
        conn.close()

# Log timeline activity
def log_timeline_activity(entity_type, entity_id, activity_type, title, description, created_by=None, related_task_id=None, metadata_dict=None):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Initialize link variables
    account_id = None
    contact_id = None
    lead_id = None
    opportunity_id = None
    telecrm_contact_id = None
    
    if entity_type == 'lead':
        lead_id = entity_id
    elif entity_type == 'opportunity':
        opportunity_id = entity_id
    elif entity_type == 'account':
        account_id = entity_id
    elif entity_type == 'contact':
        contact_id = entity_id
    elif entity_type == 'telecrm_contact':
        telecrm_contact_id = entity_id
        
    metadata_json = json.dumps(metadata_dict) if metadata_dict else None
    
    query = '''
        INSERT INTO timeline_activities (
            entity_type, entity_id, account_id, contact_id, lead_id, opportunity_id, telecrm_contact_id,
            activity_type, title, description, created_by, related_task_id, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    db_execute(query, (
        entity_type, entity_id, account_id, contact_id, lead_id, opportunity_id, telecrm_contact_id,
        activity_type, title, description, created_by, related_task_id, metadata_json, now_str
    ))

# Helper to automatically create or map Account and Contact on conversion
def get_or_create_account_and_contact(company_name, email, phone, first_name, last_name, job_title, geography, country, industry, website, linkedin_profile, source, owner_id):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Extract domain
    domain = ""
    if email and '@' in email:
        domain = email.split('@')[1].lower().strip()
    elif website:
        # crude domain extraction
        domain = website.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        
    account_id = None
    contact_id = None
    
    # 1. Check if Account exists
    if company_name:
        if domain:
            acct = db_query_one("SELECT id FROM accounts WHERE LOWER(account_name) = ? OR LOWER(domain) = ?", (company_name.lower().strip(), domain))
        else:
            acct = db_query_one("SELECT id FROM accounts WHERE LOWER(account_name) = ?", (company_name.lower().strip(),))
            
        if acct:
            account_id = acct['id']
        else:
            # Create Account
            account_id = db_execute('''
                INSERT INTO accounts (account_name, website, domain, industry, geography, country, owner_id, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (company_name, website, domain, industry, geography, country, owner_id, source, now_str, now_str))
            log_timeline_activity('account', account_id, 'Account created', f"Account {company_name} created", f"Source: {source}", owner_id)
            
    # 2. Check if Contact exists
    if email:
        cont = db_query_one("SELECT id FROM contacts WHERE LOWER(email) = ?", (email.lower().strip(),))
        if cont:
            contact_id = cont['id']
            # update account mapping if contact had no account
            db_execute("UPDATE contacts SET account_id = COALESCE(account_id, ?) WHERE id = ?", (account_id, contact_id))
        else:
            full_name = f"{first_name or ''} {last_name or ''}".strip()
            if not full_name:
                full_name = email.split('@')[0]
            # Create Contact
            contact_id = db_execute('''
                INSERT INTO contacts (account_id, first_name, last_name, full_name, email, phone, job_title, geography, country, linkedin_profile, source, validation_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Not Validated', ?, ?)
            ''', (account_id, first_name, last_name, full_name, email, phone, job_title, geography, country, linkedin_profile, source, now_str, now_str))
            log_timeline_activity('contact', contact_id, 'Contact created', f"Contact {full_name} created", f"Email: {email}", owner_id)
            
    return account_id, contact_id

# ----------------------------------------------------
# Global Lead Capture forwarder (used by app.py forms)
# ----------------------------------------------------
PERSONAL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'msn.com',
    'comcast.net', 'icloud.com', 'live.com', 'mail.com', 'gmx.com', 'yandex.com', 'zoho.com'
}

def detect_contact_duplicates(email, phone, company, first_name, last_name):
    duplicates = []
    
    email = (email or "").strip().lower()
    phone = (phone or "").strip()
    company = (company or "").strip()
    full_name = f"{first_name or ''} {last_name or ''}".strip().lower()
    
    def extract_domain(text):
        if not text:
            return ""
        if '@' in text:
            return text.split('@')[1].lower().strip()
        return ""
        
    domain = extract_domain(email) if email else ""
    
    # 1. Exact email match
    if email:
        results = db_query('''
            SELECT c.id, c.full_name, c.email, c.phone, a.account_name as company, 'Exact Email Match' as reason 
            FROM contacts c 
            LEFT JOIN accounts a ON c.account_id = a.id 
            WHERE LOWER(c.email) = ?
        ''', (email,))
        duplicates.extend(results)
        
    # 2. Exact phone match
    if phone:
        results = db_query('''
            SELECT c.id, c.full_name, c.email, c.phone, a.account_name as company, 'Exact Phone Match' as reason 
            FROM contacts c 
            LEFT JOIN accounts a ON c.account_id = a.id 
            WHERE c.phone = ? OR c.alternate_phone = ?
        ''', (phone, phone))
        for r in results:
            if not any(d['id'] == r['id'] for d in duplicates):
                duplicates.append(r)
                
    # 3. Company domain + person name
    if domain and full_name and domain not in PERSONAL_DOMAINS:
        results = db_query('''
            SELECT c.id, c.full_name, c.email, c.phone, a.account_name as company, 'Company Domain + Person Name Match' as reason 
            FROM contacts c 
            JOIN accounts a ON c.account_id = a.id 
            WHERE LOWER(c.full_name) = ? AND (LOWER(a.domain) = ? OR LOWER(c.email) LIKE ?)
        ''', (full_name, domain, f"%@{domain}"))
        for r in results:
            if not any(d['id'] == r['id'] for d in duplicates):
                duplicates.append(r)
                
    # 4. Company + phone
    if company and phone:
        results = db_query('''
            SELECT c.id, c.full_name, c.email, c.phone, a.account_name as company, 'Company + Phone Match' as reason 
            FROM contacts c 
            JOIN accounts a ON c.account_id = a.id 
            WHERE LOWER(a.account_name) = ? AND (c.phone = ? OR c.alternate_phone = ?)
        ''', (company.lower(), phone, phone))
        for r in results:
            if not any(d['id'] == r['id'] for d in duplicates):
                duplicates.append(r)
                
    return duplicates

def evaluate_assignment_rules(lead_data):
    # Fetch active rules sorted by priority (higher number first)
    rules = db_query("SELECT * FROM website_lead_assignment_rules WHERE is_active = 1 ORDER BY priority DESC, id ASC")
    
    for rule in rules:
        match = True
        
        # Check source_form
        if rule.get('source_form'):
            if rule['source_form'].lower() != (lead_data.get('source_form') or '').lower():
                match = False
                
        # Check source_page_contains
        if rule.get('source_page_contains'):
            if rule['source_page_contains'].lower() not in (lead_data.get('source_page') or '').lower():
                match = False
                
        # Check geography
        if rule.get('geography'):
            if rule['geography'].lower() != (lead_data.get('geography') or '').lower():
                match = False
                
        # Check industry
        if rule.get('industry'):
            if rule['industry'].lower() != (lead_data.get('industry') or '').lower():
                match = False
                
        # Check product solution interest
        if rule.get('product_solution_id'):
            prod = db_query_one("SELECT name FROM product_solutions WHERE id = ?", (rule['product_solution_id'],))
            if prod:
                interest = (lead_data.get('product_solution_interest') or '').lower()
                if prod['name'].lower() not in interest:
                    match = False
            else:
                match = False
                
        # Check partner interest
        if rule.get('partner_id'):
            partner = db_query_one("SELECT name FROM partners WHERE id = ?", (rule['partner_id'],))
            if partner:
                interest = (lead_data.get('partner_interest') or '').lower()
                if partner['name'].lower() not in interest:
                    match = False
            else:
                match = False
                
        if match:
            # Match found! Process assignment type
            if rule['assignment_type'] == 'fixed_owner':
                return rule['assigned_owner_id']
                
            elif rule['assignment_type'] == 'round_robin':
                group_id = rule['assigned_group_id']
                if group_id:
                    # Get active users in group
                    users = db_query("SELECT id FROM crm_users WHERE group_id = ? AND is_active = 1 AND role != 'Telecaller'", (group_id,))
                    if users:
                        user_ids = [u['id'] for u in users]
                        user_counts = {u_id: 0 for u_id in user_ids}
                        
                        # Fetch count of staging leads assigned to these users in the last 30 days
                        placeholders = ",".join("?" * len(user_ids))
                        counts = db_query(f'''
                            SELECT assigned_owner_id, COUNT(*) as cnt 
                            FROM website_leads 
                            WHERE assigned_owner_id IN ({placeholders}) 
                              AND created_at >= datetime('now', '-30 days')
                            GROUP BY assigned_owner_id
                        ''', user_ids)
                        
                        for row in counts:
                            if row['assigned_owner_id'] in user_counts:
                                user_counts[row['assigned_owner_id']] = row['cnt']
                                
                        # Pick user with lowest count
                        selected_user_id = min(user_counts, key=user_counts.get)
                        return selected_user_id
                        
            elif rule['assignment_type'] == 'group_queue':
                return None  # Leave unassigned in staging inbox
                
    return None

def log_website_lead_review_log(website_lead_id, action_type, description, previous_status=None, new_status=None, previous_owner_id=None, new_owner_id=None, performed_by=None, metadata_dict=None):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    metadata_json = json.dumps(metadata_dict) if metadata_dict else None
    
    db_execute('''
        INSERT INTO website_lead_review_logs (
            website_lead_id, action_type, description, previous_status, new_status,
            previous_owner_id, new_owner_id, performed_by, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        website_lead_id, action_type, description, previous_status, new_status,
        previous_owner_id, new_owner_id, performed_by, metadata_json, now_str
    ))

def forward_lead_to_crm(email, first_name, last_name, company, phone, job_title, geography, country, industry, message, source_form, source_page, cta_clicked, lead_source, utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status=0, **kwargs):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    email = (email or "").strip().lower()
    if not email:
        return None
        
    is_career = 'career' in (source_form or '').lower() or 'job' in (source_form or '').lower()
    
    # Check if careers capture is enabled
    if is_career:
        settings = db_query_one("SELECT careers_capture_enabled FROM crm_settings LIMIT 1")
        if not settings or not settings.get('careers_capture_enabled'):
            return None
            
        # Fetch default settings
        settings = db_query_one("SELECT default_group_id, default_sql_owner_id FROM crm_settings LIMIT 1")
        default_group = settings['default_group_id'] if settings else 1
        default_owner = settings['default_sql_owner_id'] if settings else 1
        
        # Insert Lead to traditional Leads table
        domain = email.split('@')[1] if '@' in email else ''
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        if not full_name:
            full_name = email.split('@')[0]
            
        lead_id = db_execute('''
            INSERT INTO leads (
                first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
                website, lead_source, source_form, source_page, cta_clicked, lead_list_id, owner_id, group_id, status,
                utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'New', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
            domain, lead_source, source_form, source_page, cta_clicked, default_owner, default_group,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status, now_str, now_str
        ))
        
        db_execute("INSERT OR IGNORE INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('lead', ?, ?, ?)", (lead_id, now_str, now_str))
        log_timeline_activity('lead', lead_id, 'Website lead captured', f"Career Lead captured from form: {source_form}", f"Source page: {source_page}", default_owner)
        return lead_id
        
    else:
        # NON-CAREER SUBMISSION: Staging into website_leads table!
        domain = email.split('@')[1] if '@' in email else ''
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        if not full_name:
            full_name = email.split('@')[0]
            
        # Get details from kwargs if passed
        form_name = kwargs.get('form_name') or source_form
        product_solution_interest = kwargs.get('product_solution_interest') or kwargs.get('product_interest') or ''
        partner_interest = kwargs.get('partner_interest') or kwargs.get('partner') or ''
        case_study_downloaded = kwargs.get('case_study_downloaded') or ''
        resource_downloaded = kwargs.get('resource_downloaded') or ''
        assessment_type = kwargs.get('assessment_type') or ''
        
        lead_data = {
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name,
            'business_email': email,
            'phone': phone,
            'company': company,
            'job_title': job_title,
            'country': country,
            'geography': geography,
            'industry': industry,
            'source_form': source_form,
            'source_page': source_page,
            'product_solution_interest': product_solution_interest,
            'partner_interest': partner_interest
        }
        
        # 1. Run assignment rules
        assigned_owner_id = evaluate_assignment_rules(lead_data)
        
        # 2. Run duplicate check
        duplicates = detect_contact_duplicates(email, phone, company, first_name, last_name)
        duplicate_status = "No Duplicates Detected"
        possible_duplicate_contact_ids = "[]"
        
        if duplicates:
            duplicate_status = "Warning: Possible Duplicate(s)"
            possible_duplicate_contact_ids = json.dumps([d['id'] for d in duplicates])
            
        status = 'New'
        if assigned_owner_id:
            status = 'Assigned'
            
        # Insert Website Lead
        lead_id = db_execute('''
            INSERT INTO website_leads (
                first_name, last_name, full_name, business_email, phone, company, job_title, country, geography, industry,
                message, source_form, source_page, cta_clicked, form_name, product_solution_interest, partner_interest,
                case_study_downloaded, resource_downloaded, assessment_type, consent_status, utm_source, utm_medium,
                utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, duplicate_status,
                possible_duplicate_contact_ids, assigned_owner_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            first_name, last_name, full_name, email, phone, company, job_title, country, geography, industry,
            message, source_form, source_page, cta_clicked, form_name, product_solution_interest, partner_interest,
            case_study_downloaded, resource_downloaded, assessment_type, consent_status, utm_source, utm_medium,
            utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, duplicate_status,
            possible_duplicate_contact_ids, assigned_owner_id, status, now_str, now_str
        ))
        
        # Log Review Log
        log_website_lead_review_log(
            website_lead_id=lead_id,
            action_type='Website lead captured',
            description=f"Captured staging lead from form: {source_form}",
            new_status=status,
            new_owner_id=assigned_owner_id,
            metadata_dict={'duplicates_found': len(duplicates)}
        )
        
        return lead_id

