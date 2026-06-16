import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    # Create posts table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        content TEXT NOT NULL,
        summary TEXT NOT NULL,
        meta_title TEXT,
        meta_desc TEXT,
        keywords TEXT,
        seo_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Published',
        views INTEGER DEFAULT 0
    )
    ''')
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    ''')
    
    # Create case_studies table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS case_studies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'Draft',
        featured INTEGER DEFAULT 0,
        client_name TEXT,
        client_display_name TEXT,
        is_client_anonymized INTEGER DEFAULT 1,
        industry TEXT,
        region TEXT,
        solution_area TEXT,
        technologies TEXT,
        business_challenge TEXT,
        solution_summary TEXT,
        implementation_approach TEXT,
        business_outcomes TEXT,
        key_metrics TEXT,
        quote TEXT,
        executive_summary TEXT,
        ai_summary TEXT,
        card_summary TEXT,
        detail_content TEXT,
        faq_json TEXT,
        tags TEXT,
        related_case_studies TEXT,
        related_services TEXT,
        seo_title TEXT,
        seo_description TEXT,
        seo_keywords TEXT,
        canonical_url TEXT,
        og_title TEXT,
        og_description TEXT,
        og_image TEXT,
        schema_json TEXT,
        pdf_file_path TEXT,
        pdf_file_hash TEXT,
        thumbnail_path TEXT,
        extraction_confidence_score REAL DEFAULT 0.0,
        seo_score INTEGER DEFAULT 0,
        genai_seo_score INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT
    )
    ''')

    # Create case_study_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS case_study_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_study_id INTEGER,
        business_email TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        consent INTEGER DEFAULT 0,
        source_url TEXT,
        referrer TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        ip_address TEXT,
        user_agent TEXT,
        lead_score INTEGER DEFAULT 0,
        downloaded_at TEXT,
        FOREIGN KEY (case_study_id) REFERENCES case_studies (id) ON DELETE CASCADE
    )
    ''')

    # Create case_study_import_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS case_study_import_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pdf_file_name TEXT NOT NULL,
        pdf_file_path TEXT NOT NULL,
        pdf_file_hash TEXT NOT NULL,
        status TEXT,
        extraction_summary TEXT,
        errors TEXT,
        created_case_study_id INTEGER,
        processed_at TEXT
    )
    ''')

    # Create case_study_version_history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS case_study_version_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_study_id INTEGER,
        changed_by TEXT,
        previous_data TEXT,
        new_data TEXT,
        change_summary TEXT,
        created_at TEXT,
        FOREIGN KEY (case_study_id) REFERENCES case_studies (id) ON DELETE CASCADE
    )
    ''')

    # Create industry_microsite_pages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS industry_microsite_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        industry TEXT NOT NULL,
        page_key TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        url TEXT NOT NULL,
        hero_title TEXT,
        hero_subtitle TEXT,
        body_sections_json TEXT,
        cta_json TEXT,
        faq_json TEXT,
        related_services_json TEXT,
        related_case_studies_json TEXT,
        seo_title TEXT,
        seo_description TEXT,
        seo_keywords TEXT,
        canonical_url TEXT,
        og_title TEXT,
        og_description TEXT,
        og_image TEXT,
        schema_json TEXT,
        ai_summary TEXT,
        genai_entities_json TEXT,
        status TEXT DEFAULT 'Published',
        noindex INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT
    )
    ''')

    # Create healthcare_use_cases table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS healthcare_use_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        audience_type TEXT,
        problem TEXT,
        data_domains TEXT,
        artha_solution TEXT,
        technologies TEXT,
        business_outcomes TEXT,
        related_services TEXT,
        related_case_studies TEXT,
        tags TEXT,
        seo_title TEXT,
        seo_description TEXT,
        ai_summary TEXT,
        status TEXT DEFAULT 'Published',
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # Create healthcare_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS healthcare_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_page TEXT,
        cta_clicked TEXT,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        message TEXT,
        consent INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    ''')

    # Create ai_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_page TEXT,
        cta_clicked TEXT,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        message TEXT,
        consent INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    ''')

    # Create resource_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS resource_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        business_email TEXT NOT NULL,
        company TEXT,
        source_info TEXT,
        resource_type TEXT NOT NULL,
        resource_slug TEXT NOT NULL,
        resource_title TEXT NOT NULL,
        ip_address TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # Create manufacturing_use_cases table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS manufacturing_use_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        category TEXT,
        problem TEXT,
        data_domains TEXT,
        artha_solution TEXT,
        technologies TEXT,
        business_outcomes TEXT,
        related_services TEXT,
        related_case_studies TEXT,
        tags TEXT,
        seo_title TEXT,
        seo_description TEXT,
        ai_summary TEXT,
        status TEXT DEFAULT 'Published',
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # Create manufacturing_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS manufacturing_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_page TEXT,
        cta_clicked TEXT,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        area_of_interest TEXT,
        message TEXT,
        consent INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    ''')

    # Create bfsi_use_cases table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bfsi_use_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        category TEXT,
        audience_type TEXT,
        problem TEXT,
        data_domains TEXT,
        artha_solution TEXT,
        technologies TEXT,
        business_outcomes TEXT,
        related_services TEXT,
        related_case_studies TEXT,
        tags TEXT,
        seo_title TEXT,
        seo_description TEXT,
        ai_summary TEXT,
        status TEXT DEFAULT 'Published',
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # Create bfsi_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bfsi_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_page TEXT,
        cta_clicked TEXT,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        area_of_interest TEXT,
        message TEXT,
        consent INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    ''')

    # Create retail_use_cases table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS retail_use_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        category TEXT,
        audience_type TEXT,
        problem TEXT,
        data_domains TEXT,
        artha_solution TEXT,
        technologies TEXT,
        business_outcomes TEXT,
        related_services TEXT,
        related_case_studies TEXT,
        tags TEXT,
        seo_title TEXT,
        seo_description TEXT,
        ai_summary TEXT,
        status TEXT DEFAULT 'Published',
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # Create retail_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS retail_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_page TEXT,
        cta_clicked TEXT,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        area_of_interest TEXT,
        message TEXT,
        consent INTEGER DEFAULT 0,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        referrer TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    ''')

    # Create navigation_menus table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS navigation_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT NOT NULL,
        status TEXT DEFAULT 'Published',
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT
    )
    ''')

    # Create navigation_items table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS navigation_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER,
        parent_id INTEGER,
        label TEXT NOT NULL,
        url TEXT,
        description TEXT,
        icon TEXT,
        badge TEXT,
        group_label TEXT,
        sort_order INTEGER DEFAULT 0,
        is_top_level INTEGER DEFAULT 0,
        is_featured INTEGER DEFAULT 0,
        is_visible INTEGER DEFAULT 1,
        opens_in_new_tab INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (menu_id) REFERENCES navigation_menus (id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES navigation_items (id) ON DELETE SET NULL
    )
    ''')

    # Create navigation_featured_cards table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS navigation_featured_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER,
        parent_nav_item_id INTEGER,
        title TEXT,
        description TEXT,
        image_path TEXT,
        label TEXT,
        cta_text TEXT,
        cta_url TEXT,
        sort_order INTEGER DEFAULT 0,
        is_visible INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (menu_id) REFERENCES navigation_menus (id) ON DELETE CASCADE,
        FOREIGN KEY (parent_nav_item_id) REFERENCES navigation_items (id) ON DELETE CASCADE
    )
    ''')

    # Create navigation_ctas table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS navigation_ctas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        url TEXT NOT NULL,
        style TEXT,
        location TEXT,
        is_visible INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # Create whitepapers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS whitepapers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        summary TEXT,
        content_type TEXT,
        category TEXT,
        industry TEXT,
        solution_area TEXT,
        file_path TEXT,
        file_size INTEGER,
        file_hash TEXT,
        thumbnail_path TEXT,
        preview_image_path TEXT,
        seo_title TEXT,
        seo_description TEXT,
        seo_keywords TEXT,
        canonical_url TEXT,
        og_title TEXT,
        og_description TEXT,
        og_image TEXT,
        ai_summary TEXT,
        schema_json TEXT,
        author TEXT,
        publish_date TEXT,
        status TEXT DEFAULT 'Published',
        featured INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        downloads INTEGER DEFAULT 0,
        tags TEXT,
        related_resources TEXT,
        created_by TEXT,
        updated_by TEXT,
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT
    )
    ''')

    # Create whitepaper_leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS whitepaper_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        whitepaper_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        industry TEXT,
        consent INTEGER DEFAULT 0,
        source_url TEXT,
        referrer TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        ip_address TEXT,
        user_agent TEXT,
        lead_score INTEGER DEFAULT 0,
        downloaded_at TEXT,
        created_at TEXT,
        FOREIGN KEY (whitepaper_id) REFERENCES whitepapers (id) ON DELETE CASCADE
    )
    ''')

    # Create blogs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS blogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        author TEXT,
        content TEXT,
        excerpt TEXT,
        featured_image_path TEXT,
        featured_image_alt TEXT,
        category TEXT,
        tags TEXT,
        status TEXT DEFAULT 'Published',
        featured INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        seo_title TEXT,
        seo_description TEXT,
        seo_keywords TEXT,
        canonical_url TEXT,
        og_title TEXT,
        og_description TEXT,
        og_image TEXT,
        ai_summary TEXT,
        schema_json TEXT,
        reading_time_minutes INTEGER,
        published_date TEXT,
        created_by TEXT,
        updated_by TEXT,
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT
    )
    ''')

    # Create blog_comments table (for future comments functionality)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS blog_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blog_id INTEGER,
        name TEXT,
        email TEXT,
        comment TEXT,
        is_approved INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (blog_id) REFERENCES blogs (id) ON DELETE CASCADE
    )
    ''')

    # Check if admin user exists, if not, create default
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('artha2026')
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ('admin', hashed_password))
        print("Created default admin user: username=admin, password=artha2026")
    
    # Create events table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        date TEXT NOT NULL,
        location TEXT NOT NULL,
        summary TEXT,
        description TEXT,
        card_image TEXT
    )
    ''')

    # Create webinars table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS webinars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        host TEXT NOT NULL,
        duration TEXT NOT NULL,
        summary TEXT,
        description TEXT,
        card_image TEXT
    )
    ''')

    # Create token_usage table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS token_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step_index INTEGER UNIQUE,
        timestamp TEXT,
        category TEXT,
        user_tokens REAL,
        system_tokens REAL,
        completion_tokens REAL,
        thinking_tokens REAL
    )
    ''')

    # ═══════════════════════════════════════════════════════════════
    # UNIFIED EVENTS + WEBINARS MODULE (v2)
    # ═══════════════════════════════════════════════════════════════

    # Main unified content table (replaces separate events + webinars)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_webinars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content_type TEXT NOT NULL DEFAULT 'Event',
        webinar_format TEXT,
        event_format TEXT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        short_description TEXT,
        full_description TEXT,
        theme TEXT,
        topic_category TEXT,
        start_datetime TEXT,
        end_datetime TEXT,
        timezone TEXT DEFAULT 'America/New_York',
        display_time_text TEXT,
        location_type TEXT DEFAULT 'Online',
        location TEXT,
        event_link TEXT,
        live_join_link TEXT,
        recording_link TEXT,
        recording_duration TEXT,
        recording_embed_code TEXT,
        recording_access_type TEXT DEFAULT 'redirect',
        registration_required INTEGER DEFAULT 1,
        registration_form_title TEXT,
        registration_cta_text TEXT DEFAULT 'Register Now',
        thank_you_message TEXT,
        countdown_enabled INTEGER DEFAULT 1,
        capacity INTEGER,
        registration_close_datetime TEXT,
        lifecycle_status TEXT DEFAULT 'Upcoming',
        publishing_status TEXT DEFAULT 'Draft',
        auto_convert_to_ondemand INTEGER DEFAULT 0,
        converted_to_ondemand_at TEXT,
        converted_by TEXT,
        hero_image TEXT,
        featured_image TEXT,
        partner_logo TEXT,
        sponsor_logo TEXT,
        product_solution_id INTEGER,
        partner_id INTEGER,
        related_solution_url TEXT,
        related_industry_url TEXT,
        related_case_study_id INTEGER,
        event_label TEXT,
        tags TEXT,
        who_should_attend TEXT,
        why_attend TEXT,
        highlight_title TEXT,
        highlight_text TEXT,
        highlight_link TEXT,
        custom_cta_text TEXT,
        custom_cta_url TEXT,
        resource_download_url TEXT,
        calendar_details TEXT,
        business_email_only INTEGER DEFAULT 1,
        crm_integration_enabled INTEGER DEFAULT 1,
        seo_title TEXT,
        seo_description TEXT,
        canonical_url TEXT,
        og_title TEXT,
        og_description TEXT,
        og_image TEXT,
        ai_summary TEXT,
        schema_json TEXT,
        created_by TEXT DEFAULT 'admin',
        updated_by TEXT,
        created_at TEXT,
        updated_at TEXT,
        published_at TEXT,
        archived_at TEXT
    )
    ''')

    # Speakers per event/webinar
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_speakers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        designation TEXT,
        company TEXT,
        image_path TEXT,
        image_alt_text TEXT,
        short_bio TEXT,
        full_bio TEXT,
        linkedin_url TEXT,
        profile_url TEXT,
        display_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE
    )
    ''')

    # Agenda items per event/webinar
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_agenda_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        day_number INTEGER DEFAULT 1,
        session_title TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        speaker_id INTEGER,
        track TEXT,
        description TEXT,
        display_order INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE,
        FOREIGN KEY (speaker_id) REFERENCES event_speakers (id) ON DELETE SET NULL
    )
    ''')

    # Key takeaways per event/webinar
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_key_takeaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        takeaway_text TEXT NOT NULL,
        display_order INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE
    )
    ''')

    # Registration records
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        first_name TEXT,
        last_name TEXT,
        business_email TEXT NOT NULL,
        company TEXT,
        job_title TEXT,
        phone TEXT,
        country TEXT,
        how_did_you_hear TEXT,
        consent_status INTEGER DEFAULT 0,
        attendee_status TEXT DEFAULT 'Registered',
        source_page TEXT,
        referrer TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        crm_website_lead_id TEXT,
        registered_at TEXT,
        accessed_recording_at TEXT,
        ip_address TEXT,
        user_agent TEXT,
        notes TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE
    )
    ''')

    # Activity / audit log
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        description TEXT,
        previous_status TEXT,
        new_status TEXT,
        performed_by TEXT,
        metadata_json TEXT,
        created_at TEXT,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE
    )
    ''')

    # Secure access tokens for gated on-demand recording pages
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_registration_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        registration_id INTEGER NOT NULL,
        event_id INTEGER NOT NULL,
        token_hash TEXT UNIQUE NOT NULL,
        expires_at TEXT,
        used_at TEXT,
        created_at TEXT,
        FOREIGN KEY (registration_id) REFERENCES event_registrations (id) ON DELETE CASCADE,
        FOREIGN KEY (event_id) REFERENCES event_webinars (id) ON DELETE CASCADE
    )
    ''')

    # Seed events if empty
    cursor.execute("SELECT COUNT(*) FROM events")
    if cursor.fetchone()[0] == 0:
        try:
            from content_store import EVENTS_DATA
            for slug, item in EVENTS_DATA.items():
                cursor.execute('''
                INSERT INTO events (slug, title, date, location, summary, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (slug, item.get('title'), item.get('date'), item.get('location'), item.get('summary'), item.get('description')))
            print(f"Seeded {len(EVENTS_DATA)} events.")
        except Exception as e:
            print(f"Error seeding events: {e}")

    # Seed webinars if empty
    cursor.execute("SELECT COUNT(*) FROM webinars")
    if cursor.fetchone()[0] == 0:
        try:
            from content_store import WEBINARS_DATA
            for slug, item in WEBINARS_DATA.items():
                cursor.execute('''
                INSERT INTO webinars (slug, title, host, duration, summary, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (slug, item.get('title'), item.get('host'), item.get('duration'), item.get('summary'), item.get('description')))
            print(f"Seeded {len(WEBINARS_DATA)} webinars.")
        except Exception as e:
            print(f"Error seeding webinars: {e}")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
