import sqlite3
import os
from datetime import datetime

# Monkey-patch sqlite3.connect to use URI connection with nolock=1 under OneDrive
_original_sqlite3_connect = sqlite3.connect
def _patched_sqlite3_connect(database, *args, **kwargs):
    if database == 'blog.db':
        database = 'file:blog.db?nolock=1'
        kwargs['uri'] = True
    return _original_sqlite3_connect(database, *args, **kwargs)
sqlite3.connect = _patched_sqlite3_connect

DB_PATH = 'blog.db'

def run_migration():
    print("Connecting to database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create website_leads table
    print("Creating website_leads table...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS website_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT NOT NULL,
        business_email TEXT NOT NULL,
        phone TEXT,
        company TEXT,
        job_title TEXT,
        country TEXT,
        geography TEXT,
        industry TEXT,
        message TEXT,
        source_form TEXT,
        source_page TEXT,
        cta_clicked TEXT,
        form_name TEXT,
        product_solution_interest TEXT,
        partner_interest TEXT,
        case_study_downloaded TEXT,
        resource_downloaded TEXT,
        assessment_type TEXT,
        consent_status INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        duplicate_status TEXT,
        possible_duplicate_contact_ids TEXT,
        assigned_owner_id INTEGER,
        status TEXT DEFAULT 'New',
        review_notes TEXT,
        crm_contact_id INTEGER,
        converted_at TEXT,
        converted_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (assigned_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (crm_contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (converted_by) REFERENCES crm_users(id) ON DELETE SET NULL
    )
    ''')

    # 2. Create website_lead_review_logs table
    print("Creating website_lead_review_logs table...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS website_lead_review_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        website_lead_id INTEGER NOT NULL,
        action_type TEXT,
        description TEXT,
        previous_status TEXT,
        new_status TEXT,
        previous_owner_id INTEGER,
        new_owner_id INTEGER,
        performed_by INTEGER,
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (website_lead_id) REFERENCES website_leads(id) ON DELETE CASCADE,
        FOREIGN KEY (previous_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (new_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (performed_by) REFERENCES crm_users(id) ON DELETE SET NULL
    )
    ''')

    # 3. Create website_lead_assignment_rules table
    print("Creating website_lead_assignment_rules table...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS website_lead_assignment_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        source_form TEXT,
        source_page_contains TEXT,
        geography TEXT,
        industry TEXT,
        product_solution_id INTEGER,
        partner_id INTEGER,
        assigned_owner_id INTEGER,
        assigned_group_id INTEGER,
        assignment_type TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (assigned_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_group_id) REFERENCES crm_groups(id) ON DELETE SET NULL
    )
    ''')

    # 4. Alter contacts table to add missing fields if they don't exist
    print("Checking and adding missing columns to contacts table...")
    # Helper to check if column exists
    cursor.execute("PRAGMA table_info(contacts)")
    columns = [col[1] for col in cursor.fetchall()]
    
    new_columns = [
        ("source_website_lead_id", "INTEGER"),
        ("source_form", "TEXT"),
        ("source_page", "TEXT"),
        ("cta_clicked", "TEXT"),
        ("utm_source", "TEXT"),
        ("utm_medium", "TEXT"),
        ("utm_campaign", "TEXT"),
        ("utm_term", "TEXT"),
        ("utm_content", "TEXT"),
        ("referrer", "TEXT"),
        ("owner_id", "INTEGER"),
        ("group_id", "INTEGER")
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"Adding column '{col_name}' ({col_type}) to contacts...")
            cursor.execute(f"ALTER TABLE contacts ADD COLUMN {col_name} {col_type};")
            
    # Add foreign key constraints implicitly where possible, or rely on manual mapping.
    
    # 5. Create index on website_leads
    print("Creating indices...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_website_leads_email ON website_leads(business_email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_website_leads_status ON website_leads(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_website_leads_owner ON website_leads(assigned_owner_id);")

    # 6. Seed sample assignment rules
    cursor.execute("SELECT COUNT(*) FROM website_lead_assignment_rules")
    if cursor.fetchone()[0] == 0:
        print("Seeding sample website lead assignment rules...")
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # We can find active admin/manager user ID
        cursor.execute("SELECT id FROM crm_users WHERE role = 'Platform Admin' LIMIT 1")
        admin_row = cursor.fetchone()
        admin_id = admin_row[0] if admin_row else 1
        
        cursor.execute("SELECT id FROM crm_groups LIMIT 1")
        group_row = cursor.fetchone()
        group_id = group_row[0] if group_row else 1
        
        # Geo Rule
        cursor.execute('''
            INSERT INTO website_lead_assignment_rules (
                rule_name, priority, source_form, source_page_contains, geography, industry, 
                product_solution_id, partner_id, assigned_owner_id, assigned_group_id, 
                assignment_type, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("US Geography Assignment", 10, None, None, "USA", None, None, None, admin_id, group_id, "fixed_owner", 1, now_str, now_str))
        
        # Product Rule
        cursor.execute('''
            INSERT INTO website_lead_assignment_rules (
                rule_name, priority, source_form, source_page_contains, geography, industry, 
                product_solution_id, partner_id, assigned_owner_id, assigned_group_id, 
                assignment_type, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("Healthcare Industry Round-Robin", 20, None, None, None, "Healthcare", None, None, None, group_id, "round_robin", 1, now_str, now_str))
        
        print("Sample rules seeded.")

    # 7. Commit changes and close
    conn.commit()
    conn.close()
    print("Migration finished successfully!")

if __name__ == '__main__':
    run_migration()
