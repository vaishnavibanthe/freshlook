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

def forward_lead_to_crm(email, first_name, last_name, company, phone, job_title, geography, country, industry, message, source_form, source_page, cta_clicked, lead_source, utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status=0):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    email = (email or "").strip().lower()
    if not email:
        return None
        
    # Check if careers capture is enabled
    if 'career' in source_form.lower() or 'job' in source_form.lower():
        settings = db_query_one("SELECT careers_capture_enabled FROM crm_settings LIMIT 1")
        if not settings or not settings.get('careers_capture_enabled'):
            return None
            
    # Fetch default settings
    settings = db_query_one("SELECT default_group_id, default_sql_owner_id FROM crm_settings LIMIT 1")
    default_group = settings['default_group_id'] if settings else 1
    default_owner = settings['default_sql_owner_id'] if settings else 1
    
    # Map form name to appropriate list
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
        
    list_row = db_query_one("SELECT id FROM lead_lists WHERE name = ?", (list_name,))
    list_id = list_row['id'] if list_row else 1
    
    # Extract domain from email
    domain = email.split('@')[1] if '@' in email else ''
    is_career = 'career' in (source_form or '').lower() or 'job' in (source_form or '').lower()
    if not is_career and domain in PERSONAL_DOMAINS:
        return None  # Restrict personal domains
        
    full_name = f"{first_name or ''} {last_name or ''}".strip()
    if not full_name:
        full_name = email.split('@')[0]
        
    # Insert Lead
    lead_id = db_execute('''
        INSERT INTO leads (
            first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
            website, lead_source, source_form, source_page, cta_clicked, lead_list_id, owner_id, group_id, status,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
        domain, lead_source, source_form, source_page, cta_clicked, list_id, default_owner, default_group,
        utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status, now_str, now_str
    ))
    
    # Initialize MEDDIC
    db_execute("INSERT OR IGNORE INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('lead', ?, ?, ?)", (lead_id, now_str, now_str))
    
    # Log timeline
    log_timeline_activity('lead', lead_id, 'Website lead captured', f"Lead captured from form: {source_form}", f"Source page: {source_page}", default_owner)
    
    return lead_id

