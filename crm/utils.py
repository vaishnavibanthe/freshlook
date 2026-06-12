import sqlite3
import base64
import re
from datetime import datetime

# Simple base64-based XOR encryption for SMTP credentials
ENCRYPTION_KEY = b"thinkartha_secret_key_2026"

def encrypt_smtp_password(password):
    if not password:
        return ""
    # XOR encryption
    xor_bytes = bytearray(ord(c) ^ ENCRYPTION_KEY[i % len(ENCRYPTION_KEY)] for i, c in enumerate(password))
    return base64.b64encode(xor_bytes).decode('utf-8')

def decrypt_smtp_password(encrypted_password):
    if not encrypted_password:
        return ""
    try:
        data = base64.b64decode(encrypted_password)
        decrypted = "".join(chr(b ^ ENCRYPTION_KEY[i % len(ENCRYPTION_KEY)]) for i, b in enumerate(data))
        return decrypted
    except Exception:
        return ""

# Helper to extract domain from email or website URL
def extract_domain(text):
    if not text:
        return ""
    text = text.lower().strip()
    # Check if email
    if '@' in text:
        parts = text.split('@')
        if len(parts) == 2:
            return parts[1]
    # Check if website URL
    text = re.sub(r'^(https?://)?(www\.)?', '', text)
    parts = text.split('/')
    return parts[0]

# Calculate MEDDIC score and return (score, label)
def calculate_meddic_score(meddic):
    if not meddic:
        return 0, "Weak"
    
    score = 0
    # Weights: Metrics: 20, Economic Buyer: 15, Decision Criteria: 15, Decision Process: 15, Identify Pain: 20, Champion: 15
    if meddic.get('metrics_identified'):
        score += 20
    if meddic.get('economic_buyer_identified'):
        score += 15
    if meddic.get('decision_criteria') or meddic.get('technical_criteria') or meddic.get('business_criteria'):
        score += 15
    if meddic.get('decision_process_known'):
        score += 15
    if meddic.get('pain_validated'):
        score += 20
    if meddic.get('champion_identified'):
        score += 15
        
    if score >= 70:
        label = "Strong"
    elif score >= 40:
        label = "Developing"
    else:
        label = "Weak"
        
    return score, label

# DB connection helper
def get_db_connection():
    conn = sqlite3.connect('blog.db', timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

# Duplicate detection logic for import checks
def check_duplicates(conn, email, phone, company, first_name, last_name):
    duplicates = []
    
    email = (email or "").strip().lower()
    phone = (phone or "").strip()
    company = (company or "").strip()
    domain = extract_domain(email) if email else ""
    full_name = f"{first_name or ''} {last_name or ''}".strip()
    
    # 1. Email exact match
    if email:
        # Check leads
        lead = conn.execute("SELECT id, full_name, company, 'Lead' as match_type FROM leads WHERE LOWER(email) = ?", (email,)).fetchone()
        if lead:
            duplicates.append(dict(lead))
        # Check contacts
        contact = conn.execute("SELECT c.id, c.full_name, a.account_name as company, 'Contact' as match_type FROM contacts c LEFT JOIN accounts a ON c.account_id = a.id WHERE LOWER(c.email) = ?", (email,)).fetchone()
        if contact:
            duplicates.append(dict(contact))
        # Check telecrm_contacts
        t_contact = conn.execute("SELECT id, full_name, company, 'TeleCRM Contact' as match_type FROM telecrm_contacts WHERE LOWER(email) = ?", (email,)).fetchone()
        if t_contact:
            duplicates.append(dict(t_contact))
            
    # 2. Phone exact match
    if phone:
        # Check leads
        lead = conn.execute("SELECT id, full_name, company, 'Lead (Phone Match)' as match_type FROM leads WHERE phone = ?", (phone,)).fetchone()
        if lead and dict(lead) not in duplicates:
            duplicates.append(dict(lead))
        # Check contacts
        contact = conn.execute("SELECT c.id, c.full_name, a.account_name as company, 'Contact (Phone Match)' as match_type FROM contacts c LEFT JOIN accounts a ON c.account_id = a.id WHERE c.phone = ? OR c.alternate_phone = ?", (phone, phone)).fetchone()
        if contact and dict(contact) not in duplicates:
            duplicates.append(dict(contact))
        # Check telecrm_contacts
        t_contact = conn.execute("SELECT id, full_name, company, 'TeleCRM Contact (Phone Match)' as match_type FROM telecrm_contacts WHERE phone = ? OR alternate_phone = ?", (phone, phone)).fetchone()
        if t_contact and dict(t_contact) not in duplicates:
            duplicates.append(dict(t_contact))

    # 3. Company domain + contact name match
    if domain and full_name:
        contact = conn.execute('''
            SELECT c.id, c.full_name, a.account_name as company, 'Contact (Domain + Name Match)' as match_type 
            FROM contacts c 
            JOIN accounts a ON c.account_id = a.id 
            WHERE LOWER(c.full_name) = ? AND (LOWER(a.domain) = ? OR LOWER(a.website) LIKE ?)
        ''', (full_name.lower(), domain, f"%{domain}%")).fetchone()
        if contact and dict(contact) not in duplicates:
            duplicates.append(dict(contact))
            
    # 4. Company + phone match
    if company and phone:
        # Check telecrm_contacts
        t_contact = conn.execute("SELECT id, full_name, company, 'TeleCRM (Company + Phone Match)' as match_type FROM telecrm_contacts WHERE LOWER(company) = ? AND phone = ?", (company.lower(), phone)).fetchone()
        if t_contact and dict(t_contact) not in duplicates:
            duplicates.append(dict(t_contact))
            
    return duplicates

# Percent-based telecaller allocation algorithm
def allocate_contacts_to_telecallers(contact_ids, allocation_map):
    """
    contact_ids: list of integer IDs of telecrm_contacts to allocate
    allocation_map: dict of {telecaller_user_id: percentage_integer}
    e.g., {5: 40, 6: 30, 7: 30}
    Returns a dict mapping contact_id to telecaller_user_id
    """
    total_contacts = len(contact_ids)
    if total_contacts == 0:
        return {}
        
    # Filter active allocations (>0%)
    active_allocations = {tc_id: pct for tc_id, pct in allocation_map.items() if pct > 0}
    if not active_allocations:
        return {}
        
    # Validate sum of percentages
    total_pct = sum(active_allocations.values())
    if total_pct != 100:
        # Adjust allocation to sum to 100% proportionally or raise
        scale = 100.0 / total_pct
        active_allocations = {tc_id: round(pct * scale) for tc_id, pct in active_allocations.items()}
        # Correct rounding errors to hit exactly 100
        diff = 100 - sum(active_allocations.values())
        if diff != 0:
            first_key = list(active_allocations.keys())[0]
            active_allocations[first_key] += diff

    # Calculate counts per caller
    assigned_counts = {}
    remaining = total_contacts
    
    # Sort telecallers to distribute largest percentages first
    sorted_callers = sorted(active_allocations.items(), key=lambda x: x[1], reverse=True)
    
    for i, (tc_id, pct) in enumerate(sorted_callers):
        if i == len(sorted_callers) - 1:
            # Last caller takes all remaining due to rounding
            assigned_counts[tc_id] = remaining
        else:
            count = int(round(total_contacts * (pct / 100.0)))
            # Keep count bounded
            count = min(count, remaining)
            assigned_counts[tc_id] = count
            remaining -= count
            
    # Assign contact IDs sequentially based on calculated allocations
    assignments = {}
    current_idx = 0
    for tc_id, count in assigned_counts.items():
        for _ in range(count):
            if current_idx < total_contacts:
                assignments[contact_ids[current_idx]] = tc_id
                current_idx += 1
                
    return assignments
