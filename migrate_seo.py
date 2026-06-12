"""
Migration script: Create SEO, AEO, and GEO Tables in blog.db
Run once: python3 migrate_seo.py
"""
import sqlite3
import os
import uuid
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'blog.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # -- seo_pages table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS seo_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_slug TEXT UNIQUE NOT NULL,
            seo_title TEXT,
            meta_description TEXT,
            canonical_url TEXT,
            h1 TEXT,
            breadcrumb_title TEXT,
            og_title TEXT,
            og_description TEXT,
            og_image TEXT,
            robots_directive TEXT DEFAULT 'index, follow',
            sitemap_inclusion INTEGER DEFAULT 1,
            sitemap_priority REAL DEFAULT 0.5,
            last_updated TEXT,
            schema_json TEXT,
            aeo_quick_answer TEXT,
            aeo_key_facts TEXT, -- JSON array of key facts
            aeo_questions TEXT, -- JSON array of questions and answers
            author_name TEXT,
            author_role TEXT,
            author_expertise TEXT,
            reviewer_name TEXT,
            reviewer_role TEXT,
            reviewer_expertise TEXT,
            last_reviewed_date TEXT,
            content_status TEXT DEFAULT 'Draft', -- Draft, SEO Review, Subject-Matter Review, Legal/Compliance Review, Approved, Published
            seo_score INTEGER DEFAULT 0,
            aeo_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # -- seo_redirects table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS seo_redirects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT UNIQUE NOT NULL,
            target_path TEXT NOT NULL,
            redirect_type INTEGER DEFAULT 301,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # -- seo_audits table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS seo_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            health_score INTEGER DEFAULT 0,
            technical_score INTEGER DEFAULT 0,
            content_score INTEGER DEFAULT 0,
            schema_score INTEGER DEFAULT 0,
            page_exp_score INTEGER DEFAULT 0,
            aeo_score INTEGER DEFAULT 0,
            ai_citation_score INTEGER DEFAULT 0,
            crawl_score INTEGER DEFAULT 0,
            index_score INTEGER DEFAULT 0,
            link_score INTEGER DEFAULT 0,
            pages_audited INTEGER DEFAULT 0,
            critical_errors INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            opportunities INTEGER DEFAULT 0,
            fixed_issues INTEGER DEFAULT 0,
            remaining_issues INTEGER DEFAULT 0,
            audit_results_json TEXT
        )
    """)

    # -- seo_settings table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS seo_settings (
            key TEXT UNIQUE NOT NULL,
            value TEXT
        )
    """)

    # -- seo_indexnow_logs table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS seo_indexnow_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            response_code INTEGER,
            error_message TEXT,
            submitted_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Pre-seed settings if not existing
    default_settings = {
        'robots_policy': json.dumps({
            'Googlebot': {'allowed': True, 'crawl_delay': None},
            'Bingbot': {'allowed': True, 'crawl_delay': None},
            'OAI-SearchBot': {'allowed': True, 'crawl_delay': None},
            'GPTBot': {'allowed': False, 'crawl_delay': None},
            'Applebot': {'allowed': True, 'crawl_delay': None},
            '*': {'allowed': True, 'crawl_delay': None}
        }),
        'google_verification': '',
        'bing_verification': '',
        'indexnow_key': uuid.uuid4().hex,
        'indexnow_enabled': '1',
        'performance_budget': json.dumps({
            'max_page_weight_kb': 2000,
            'max_js_weight_kb': 500,
            'max_img_weight_kb': 1000,
            'max_fonts': 3,
            'max_response_time_ms': 500
        })
    }

    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO seo_settings (key, value) VALUES (?, ?)", (k, v))

    # Pre-populate seo_pages with existing main paths if empty
    c.execute("SELECT COUNT(*) FROM seo_pages")
    if c.fetchone()[0] == 0:
        main_paths = [
            '/', '/artha-advantage', '/artificial-intelligence', '/about-us', '/careers',
            '/solutions', '/partners', '/data-solutions', '/sap', '/enterprise-application',
            '/industries', '/resources', '/resources/blogs', '/resources/case-studies',
            '/resources/events', '/resources/webinars', '/resources/whitepapers',
            '/cloud', '/managed-services', '/artha-advantage-for-sap', '/data-readiness',
            '/solutions/big-data', '/industries/data-quality', '/privacy-policy'
        ]
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for path in main_paths:
            title_part = path.replace('/', ' ').replace('-', ' ').title().strip() or 'Home'
            c.execute("""
                INSERT INTO seo_pages 
                (route_slug, seo_title, meta_description, canonical_url, h1, robots_directive, sitemap_inclusion, sitemap_priority, content_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                path,
                f"{title_part} | Artha Solutions",
                f"Empower your business with ThinkArtha's {title_part.lower()} services. Learn more about our data strategy and solutions.",
                f"https://www.thinkartha.com{path}",
                title_part,
                'index, follow',
                1,
                1.0 if path == '/' else 0.8,
                'Published',
                now_str,
                now_str
            ))
        print(f"Pre-populated {len(main_paths)} routes in seo_pages.")

    conn.commit()
    conn.close()
    print("SEO tables created and initialized successfully.")

if __name__ == '__main__':
    migrate()
