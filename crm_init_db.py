import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

# Monkey-patch sqlite3.connect to use URI connection with nolock=1 under OneDrive
_original_sqlite3_connect = sqlite3.connect
def _patched_sqlite3_connect(database, *args, **kwargs):
    if database == 'blog.db':
        database = 'file:blog.db?nolock=1'
        kwargs['uri'] = True
    return _original_sqlite3_connect(database, *args, **kwargs)
sqlite3.connect = _patched_sqlite3_connect

def init_crm_db():
    conn = sqlite3.connect('blog.db')
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    print("Initializing CRM Tables...")
    
    # 1. CRM Groups
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crm_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        group_admin_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')

    # 2. CRM Users
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crm_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, 
        group_id INTEGER,
        manager_id INTEGER,
        sales_head_id INTEGER,
        geography TEXT,
        department TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (manager_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (sales_head_id) REFERENCES crm_users(id) ON DELETE SET NULL
    )
    ''')

    # 3. Product Solutions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS product_solutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        category TEXT,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')

    # 4. Partners
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        partner_type TEXT,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')

    # 5. Product Partner Mappings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS product_partner_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_solution_id INTEGER NOT NULL,
        partner_id INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (product_solution_id) REFERENCES product_solutions(id) ON DELETE CASCADE,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE CASCADE,
        UNIQUE(product_solution_id, partner_id)
    )
    ''')

    # 6. Accounts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_name TEXT NOT NULL,
        website TEXT,
        domain TEXT,
        industry TEXT,
        geography TEXT,
        country TEXT,
        owner_id INTEGER,
        group_id INTEGER,
        partner_id INTEGER,
        source TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL
    )
    ''')

    # 7. Contacts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        alternate_phone TEXT,
        job_title TEXT,
        geography TEXT,
        country TEXT,
        linkedin_profile TEXT,
        source TEXT,
        validation_status TEXT DEFAULT 'Not Validated',
        consent_status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
    )
    ''')

    # 8. Lead Lists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lead_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        group_id INTEGER,
        created_by INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (created_by) REFERENCES crm_users(id) ON DELETE SET NULL
    )
    ''')

    # 9. Leads
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT NOT NULL,
        company TEXT,
        email TEXT NOT NULL,
        phone TEXT,
        job_title TEXT,
        geography TEXT,
        country TEXT,
        industry TEXT,
        website TEXT,
        linkedin_profile TEXT,
        lead_source TEXT,
        source_form TEXT,
        source_page TEXT,
        cta_clicked TEXT,
        lead_list_id INTEGER,
        account_id INTEGER,
        contact_id INTEGER,
        owner_id INTEGER,
        group_id INTEGER,
        status TEXT DEFAULT 'New',
        primary_product_solution_id INTEGER,
        secondary_product_solution_ids TEXT,
        partner_id INTEGER,
        partner_influence_type TEXT,
        lead_score INTEGER DEFAULT 0,
        meddic_score INTEGER DEFAULT 0,
        consent_status INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        notes TEXT,
        converted_opportunity_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (lead_list_id) REFERENCES lead_lists(id) ON DELETE SET NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (primary_product_solution_id) REFERENCES product_solutions(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL
    )
    ''')

    # 10. Opportunities
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        account_id INTEGER,
        contact_id INTEGER,
        opportunity_name TEXT NOT NULL,
        company TEXT,
        primary_contact_name TEXT,
        primary_contact_email TEXT,
        owner_id INTEGER,
        sales_manager_id INTEGER,
        group_id INTEGER,
        industry TEXT,
        geography TEXT,
        primary_product_solution_id INTEGER,
        additional_product_solution_ids TEXT,
        partner_id INTEGER,
        partner_influence_type TEXT,
        partner_contact_name TEXT,
        partner_notes TEXT,
        estimated_value REAL DEFAULT 0.0,
        currency TEXT DEFAULT 'USD',
        expected_close_date TEXT,
        stage TEXT DEFAULT 'Prospecting',
        bucket TEXT DEFAULT 'Prospecting',
        probability INTEGER DEFAULT 10,
        meddic_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Open',
        sql_source TEXT,
        telecrm_contact_id INTEGER,
        meeting_date TEXT,
        mom TEXT,
        closed_reason TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (sales_manager_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (primary_product_solution_id) REFERENCES product_solutions(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL
    )
    ''')

    # 11. MEDDIC Qualifications
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS meddic_qualifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        metrics_identified INTEGER DEFAULT 0,
        metrics_note TEXT,
        estimated_impact TEXT,
        success_metric TEXT,
        economic_buyer_identified INTEGER DEFAULT 0,
        economic_buyer_name TEXT,
        economic_buyer_title TEXT,
        economic_buyer_access_level TEXT,
        decision_criteria TEXT,
        technical_criteria TEXT,
        business_criteria TEXT,
        compliance_criteria TEXT,
        decision_process_known INTEGER DEFAULT 0,
        decision_timeline TEXT,
        approval_process TEXT,
        procurement_involved INTEGER DEFAULT 0,
        target_decision_date TEXT,
        primary_pain TEXT,
        business_challenge TEXT,
        pain_severity TEXT,
        pain_validated INTEGER DEFAULT 0,
        champion_identified INTEGER DEFAULT 0,
        champion_name TEXT,
        champion_role TEXT,
        champion_strength TEXT,
        competitor_or_alternative TEXT,
        current_solution TEXT,
        differentiation_note TEXT,
        score INTEGER DEFAULT 0,
        updated_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (updated_by) REFERENCES crm_users(id) ON DELETE SET NULL,
        UNIQUE(entity_type, entity_id)
    )
    ''')

    # 12. TeleCRM Lists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        campaign_name TEXT,
        description TEXT,
        geography TEXT,
        industry TEXT,
        lead_source TEXT,
        product_solution_id INTEGER,
        partner_id INTEGER,
        uploaded_by INTEGER,
        group_id INTEGER,
        status TEXT DEFAULT 'Active',
        total_contacts INTEGER DEFAULT 0,
        duplicate_count INTEGER DEFAULT 0,
        assigned_count INTEGER DEFAULT 0,
        completed_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (product_solution_id) REFERENCES product_solutions(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL,
        FOREIGN KEY (uploaded_by) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL
    )
    ''')

    # 13. TeleCRM Contacts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telecrm_list_id INTEGER NOT NULL,
        account_id INTEGER,
        contact_id INTEGER,
        lead_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT NOT NULL,
        company TEXT,
        email TEXT NOT NULL,
        phone TEXT,
        alternate_phone TEXT,
        job_title TEXT,
        geography TEXT,
        country TEXT,
        industry TEXT,
        website TEXT,
        linkedin_profile TEXT,
        assigned_telecaller_id INTEGER,
        assigned_manager_id INTEGER,
        group_id INTEGER,
        product_solution_id INTEGER,
        partner_id INTEGER,
        dialing_status TEXT DEFAULT 'Not Dialed',
        last_disposition TEXT,
        contact_validation_status TEXT DEFAULT 'Not Validated',
        interest_level TEXT,
        meeting_status TEXT DEFAULT 'Not Required',
        meeting_scheduled_at TEXT,
        meeting_completed_at TEXT,
        sql_status TEXT DEFAULT 'Not SQL',
        converted_opportunity_id INTEGER,
        mom TEXT,
        notes TEXT,
        source TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (telecrm_list_id) REFERENCES telecrm_lists(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_telecaller_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_manager_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (product_solution_id) REFERENCES product_solutions(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL,
        FOREIGN KEY (converted_opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    )
    ''')

    # 14. TeleCRM Call Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telecrm_contact_id INTEGER NOT NULL,
        telecaller_id INTEGER NOT NULL,
        call_datetime TEXT NOT NULL,
        disposition TEXT NOT NULL,
        outcome_note TEXT,
        next_followup_date TEXT,
        contact_validated INTEGER DEFAULT 0,
        interest_level TEXT,
        product_solution_id INTEGER,
        partner_id INTEGER,
        meeting_required INTEGER DEFAULT 0,
        meeting_scheduled_at TEXT,
        mom TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (telecrm_contact_id) REFERENCES telecrm_contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (telecaller_id) REFERENCES crm_users(id) ON DELETE CASCADE,
        FOREIGN KEY (product_solution_id) REFERENCES product_solutions(id) ON DELETE SET NULL,
        FOREIGN KEY (partner_id) REFERENCES partners(id) ON DELETE SET NULL
    )
    ''')

    # 15. TeleCRM Email Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telecrm_contact_id INTEGER NOT NULL,
        sender_user_id INTEGER NOT NULL,
        to_email TEXT NOT NULL,
        cc TEXT,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT DEFAULT 'Sent',
        sent_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (telecrm_contact_id) REFERENCES telecrm_contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (sender_user_id) REFERENCES crm_users(id) ON DELETE CASCADE
    )
    ''')

    # 16. TeleCRM Allocation Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_allocation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telecrm_list_id INTEGER NOT NULL,
        allocated_by INTEGER NOT NULL,
        telecaller_id INTEGER NOT NULL,
        allocation_percentage REAL NOT NULL,
        assigned_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (telecrm_list_id) REFERENCES telecrm_lists(id) ON DELETE CASCADE,
        FOREIGN KEY (allocated_by) REFERENCES crm_users(id) ON DELETE CASCADE,
        FOREIGN KEY (telecaller_id) REFERENCES crm_users(id) ON DELETE CASCADE
    )
    ''')

    # 17. TeleCRM Import Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telecrm_import_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telecrm_list_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        uploaded_by INTEGER NOT NULL,
        duplicate_action TEXT NOT NULL,
        total_rows INTEGER DEFAULT 0,
        imported_rows INTEGER DEFAULT 0,
        duplicate_rows INTEGER DEFAULT 0,
        skipped_rows INTEGER DEFAULT 0,
        failed_rows INTEGER DEFAULT 0,
        error_report_path TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (telecrm_list_id) REFERENCES telecrm_lists(id) ON DELETE CASCADE,
        FOREIGN KEY (uploaded_by) REFERENCES crm_users(id) ON DELETE CASCADE
    )
    ''')

    # 18. CRM Tasks
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crm_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        task_type TEXT NOT NULL,
        related_entity_type TEXT,
        related_entity_id INTEGER,
        lead_id INTEGER,
        opportunity_id INTEGER,
        telecrm_contact_id INTEGER,
        assigned_to INTEGER NOT NULL,
        created_by INTEGER NOT NULL,
        due_date TEXT NOT NULL,
        due_time TEXT,
        priority TEXT DEFAULT 'Medium',
        status TEXT DEFAULT 'Open',
        completed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (assigned_to) REFERENCES crm_users(id) ON DELETE CASCADE,
        FOREIGN KEY (created_by) REFERENCES crm_users(id) ON DELETE CASCADE,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
        FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE CASCADE,
        FOREIGN KEY (telecrm_contact_id) REFERENCES telecrm_contacts(id) ON DELETE CASCADE
    )
    ''')

    # 19. Timeline Activities
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS timeline_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        account_id INTEGER,
        contact_id INTEGER,
        lead_id INTEGER,
        opportunity_id INTEGER,
        telecrm_contact_id INTEGER,
        activity_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        created_by INTEGER,
        related_task_id INTEGER,
        visibility TEXT DEFAULT 'All',
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (created_by) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (related_task_id) REFERENCES crm_tasks(id) ON DELETE SET NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
        FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL,
        FOREIGN KEY (telecrm_contact_id) REFERENCES telecrm_contacts(id) ON DELETE SET NULL
    )
    ''')

    # 20. CRM Email Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crm_email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        lead_id INTEGER,
        opportunity_id INTEGER,
        sender_user_id INTEGER NOT NULL,
        to_email TEXT NOT NULL,
        cc TEXT,
        bcc TEXT,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        attachment_paths TEXT,
        status TEXT DEFAULT 'Sent',
        sent_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (sender_user_id) REFERENCES crm_users(id) ON DELETE CASCADE,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
        FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    )
    ''')

    # 21. Lead Assignment History
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lead_assignment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        opportunity_id INTEGER,
        telecrm_contact_id INTEGER,
        previous_owner_id INTEGER,
        new_owner_id INTEGER,
        changed_by INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
        FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL,
        FOREIGN KEY (telecrm_contact_id) REFERENCES telecrm_contacts(id) ON DELETE SET NULL,
        FOREIGN KEY (previous_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (new_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL,
        FOREIGN KEY (changed_by) REFERENCES crm_users(id) ON DELETE CASCADE
    )
    ''')

    # 22. CRM Settings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crm_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        smtp_host TEXT,
        smtp_port INTEGER,
        smtp_username TEXT,
        smtp_password_encrypted TEXT,
        from_email TEXT,
        default_group_id INTEGER,
        duplicate_detection_enabled INTEGER DEFAULT 1,
        task_reminder_enabled INTEGER DEFAULT 1,
        default_sql_owner_id INTEGER,
        careers_capture_enabled INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (default_group_id) REFERENCES crm_groups(id) ON DELETE SET NULL,
        FOREIGN KEY (default_sql_owner_id) REFERENCES crm_users(id) ON DELETE SET NULL
    )
    ''')

    print("Creating Indices for CRM query optimizations...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telecrm_contacts_email ON telecrm_contacts(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_owner ON leads(owner_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_owner ON opportunities(owner_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telecrm_contacts_caller ON telecrm_contacts(assigned_telecaller_id);")

    # Commit the schema
    conn.commit()
    print("Schema created successfully!")

    # ----------------------------------------------------
    # Seed Initial Data
    # ----------------------------------------------------
    print("Seeding default lists and configurations...")
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    # Seed Default Settings
    cursor.execute("SELECT COUNT(*) FROM crm_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
        INSERT INTO crm_settings (smtp_host, smtp_port, smtp_username, smtp_password_encrypted, from_email, duplicate_detection_enabled, careers_capture_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('smtp.gmail.com', 587, 'sales@thinkartha.com', '', 'sales@thinkartha.com', 1, 0, now_str, now_str))
        print("Seeded default CRM Settings.")

    # Seed Default Product Solutions
    products = [
        ('AI Data Readiness', 'Artificial Intelligence'),
        ('Data Governance', 'Governance'),
        ('Data Quality', 'Governance'),
        ('Master Data Management', 'Governance'),
        ('Customer 360', '360 Views'),
        ('Product 360', '360 Views'),
        ('Supplier 360', '360 Views'),
        ('Data Insights Platform', 'Analytics'),
        ('Data Integration', 'Integration'),
        ('Analytics Modernization', 'Analytics'),
        ('Cloud Data Platform', 'Cloud'),
        ('SAP / ERP Data Modernization', 'SAP Services'),
        ('ETL Modernization', 'Integration'),
        ('Qlik + Talend Services', 'Partners Services'),
        ('Managed Services', 'Operations'),
        ('Healthcare Data Solutions', 'Industry Solutions'),
        ('Manufacturing Data Solutions', 'Industry Solutions'),
        ('BFSI Data Solutions', 'Industry Solutions'),
        ('Retail Data Solutions', 'Industry Solutions')
    ]
    for p_name, category in products:
        cursor.execute("SELECT id FROM product_solutions WHERE name = ?", (p_name,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO product_solutions (name, category, description, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ''', (p_name, category, f"ThinkArtha solution for {p_name}", now_str, now_str))
            print(f"Seeded Product/Solution: {p_name}")

    # Seed Default Partners
    partners = [
        ('Qlik', 'Technology Partner'),
        ('Talend', 'Technology Partner'),
        ('AWS', 'Cloud Provider'),
        ('Azure', 'Cloud Provider'),
        ('Google Cloud', 'Cloud Provider'),
        ('Snowflake', 'Data Platform'),
        ('SAP', 'Enterprise Application'),
        ('Salesforce', 'CRM & Sales'),
        ('Other', 'Various'),
        ('No Partner', 'Direct')
    ]
    for p_name, p_type in partners:
        cursor.execute("SELECT id FROM partners WHERE name = ?", (p_name,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO partners (name, partner_type, description, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ''', (p_name, p_type, f"Technology partnership with {p_name}", now_str, now_str))
            print(f"Seeded Partner: {p_name}")

    # Map products to partners
    mapping_data = [
        ('Qlik + Talend Services', 'Qlik'),
        ('Qlik + Talend Services', 'Talend'),
        ('SAP / ERP Data Modernization', 'SAP'),
        ('Cloud Data Platform', 'Snowflake'),
        ('Cloud Data Platform', 'AWS'),
        ('Cloud Data Platform', 'Azure'),
        ('Cloud Data Platform', 'Google Cloud')
    ]
    for prod_name, part_name in mapping_data:
        cursor.execute("SELECT id FROM product_solutions WHERE name = ?", (prod_name,))
        prod_row = cursor.fetchone()
        cursor.execute("SELECT id FROM partners WHERE name = ?", (part_name,))
        part_row = cursor.fetchone()
        if prod_row and part_row:
            p_id = prod_row[0]
            part_id = part_row[0]
            cursor.execute("SELECT id FROM product_partner_mappings WHERE product_solution_id = ? AND partner_id = ?", (p_id, part_id))
            if not cursor.fetchone():
                cursor.execute('''
                INSERT INTO product_partner_mappings (product_solution_id, partner_id, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ''', (p_id, part_id, now_str, now_str))
                print(f"Mapped {prod_name} to partner {part_name}")

    # Seed Default CRM Group
    cursor.execute("SELECT id FROM crm_groups WHERE name = 'ThinkArtha Enterprise Sales'")
    group_row = cursor.fetchone()
    if not group_row:
        cursor.execute('''
        INSERT INTO crm_groups (name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ''', ('ThinkArtha Enterprise Sales', 'Default business group for ThinkArtha core services', now_str, now_str))
        cursor.execute("SELECT id FROM crm_groups WHERE name = 'ThinkArtha Enterprise Sales'")
        group_row = cursor.fetchone()
        print("Seeded default CRM Group: ThinkArtha Enterprise Sales")
    
    group_id = group_row[0]
    # Update settings to point to this group
    cursor.execute("UPDATE crm_settings SET default_group_id = ?", (group_id,))

    # Seed Default Admin User
    cursor.execute("SELECT id FROM crm_users WHERE email = 'admin@thinkartha.com'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('artha2026')
        cursor.execute('''
        INSERT INTO crm_users (name, email, password_hash, role, group_id, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ''', ('Platform Admin', 'admin@thinkartha.com', hashed_password, 'Platform Admin', group_id, now_str, now_str))
        print("Seeded default Platform Admin user: admin@thinkartha.com / artha2026")

    # Seed Default Telecaller User (for testing calling workbench)
    cursor.execute("SELECT id FROM crm_users WHERE email = 'caller@thinkartha.com'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('caller2026')
        cursor.execute('''
        INSERT INTO crm_users (name, email, password_hash, role, group_id, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ''', ('Telecaller John', 'caller@thinkartha.com', hashed_password, 'Telecaller', group_id, now_str, now_str))
        print("Seeded default Telecaller user: caller@thinkartha.com / caller2026")

    # Seed Default Sales Manager User (for SQL assignment)
    cursor.execute("SELECT id FROM crm_users WHERE email = 'manager@thinkartha.com'")
    manager_row = cursor.fetchone()
    if not manager_row:
        hashed_password = generate_password_hash('manager2026')
        cursor.execute('''
        INSERT INTO crm_users (name, email, password_hash, role, group_id, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ''', ('Sales Manager Sarah', 'manager@thinkartha.com', hashed_password, 'Manager / Sales Manager', group_id, now_str, now_str))
        cursor.execute("SELECT id FROM crm_users WHERE email = 'manager@thinkartha.com'")
        manager_row = cursor.fetchone()
        print("Seeded default Sales Manager user: manager@thinkartha.com / manager2026")
    
    manager_user_id = manager_row[0]
    cursor.execute("UPDATE crm_settings SET default_sql_owner_id = ?", (manager_user_id,))

    # Seed Default Lead Lists (matching list categories in spec)
    list_names = [
        'Healthcare Microsite Leads',
        'Manufacturing Microsite Leads',
        'BFSI Microsite Leads',
        'Retail Microsite Leads',
        'Case Study Downloads',
        'Data Readiness Assessment Leads',
        'Website Contact Leads',
        'Resource Leads',
        'Manually Added Leads',
        'Imported Leads',
        'TeleCRM Dialing Lists'
    ]
    for lst_name in list_names:
        cursor.execute("SELECT id FROM lead_lists WHERE name = ?", (lst_name,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO lead_lists (name, description, group_id, created_by, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, 1, ?, ?)
            ''', (lst_name, f"List for capturing {lst_name}", group_id, now_str, now_str))
            print(f"Seeded Lead List: {lst_name}")

    conn.commit()
    conn.close()
    print("Database initial CRM seeding complete.")

if __name__ == '__main__':
    init_crm_db()
