"""
migrate_events_unified.py
─────────────────────────
One-time migration: copies records from the legacy `events` and `webinars`
tables into the new unified `event_webinars` table, then backfills the
admin-editable detail content used by public event/webinar pages.

Old tables are NOT dropped — they stay for backward compat.

Run once after applying the new init_db.py schema:
    python3 migrate_events_unified.py
"""

import sqlite3
from datetime import UTC, datetime

DB = 'blog.db'

def get_conn():
    conn = sqlite3.connect(f'file:{DB}?nolock=1', uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def migrate():
    conn = get_conn()
    now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    migrated = 0

    # ── Migrate old `events` → event_webinars ──────────────────────
    try:
        old_events = conn.execute("SELECT * FROM events").fetchall()
        for ev in old_events:
            slug = ev['slug']
            # Skip if already migrated
            exists = conn.execute(
                "SELECT id FROM event_webinars WHERE slug = ?", (slug,)
            ).fetchone()
            if exists:
                print(f"  [SKIP] Event already migrated: {slug}")
                continue

            # Parse date for start_datetime
            date_str = ev['date'] if ev['date'] else ''
            start_dt = None
            for fmt in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d'):
                try:
                    start_dt = datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%dT09:00:00')
                    break
                except ValueError:
                    pass
            if not start_dt:
                start_dt = date_str

            conn.execute('''
            INSERT INTO event_webinars (
                content_type, event_format, title, slug, short_description,
                full_description, location_type, location, start_datetime,
                lifecycle_status, publishing_status, registration_required,
                registration_cta_text, countdown_enabled,
                created_by, created_at, updated_at, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'Event',
                'In-Person Event',
                ev['title'],
                slug,
                ev['summary'] or '',
                ev['description'] or '',
                'In-Person',
                ev['location'] or '',
                start_dt,
                'Upcoming',
                'Published',
                0,
                'Register Now',
                1,
                'admin',
                now, now, now
            ))
            migrated += 1
            print(f"  [OK] Migrated event: {slug}")
    except Exception as e:
        print(f"  [ERROR] Events migration failed: {e}")

    # ── Migrate old `webinars` → event_webinars ────────────────────
    try:
        old_webinars = conn.execute("SELECT * FROM webinars").fetchall()
        for wb in old_webinars:
            slug = wb['slug']
            # Map to webinar slug pattern for deconfliction
            ew_slug = slug if not slug.startswith('wb-') else slug
            exists = conn.execute(
                "SELECT id FROM event_webinars WHERE slug = ?", (ew_slug,)
            ).fetchone()
            if exists:
                print(f"  [SKIP] Webinar already migrated: {ew_slug}")
                continue

            conn.execute('''
            INSERT INTO event_webinars (
                content_type, webinar_format, title, slug, short_description,
                full_description, location_type, recording_duration,
                lifecycle_status, publishing_status, registration_required,
                registration_cta_text, countdown_enabled,
                created_by, created_at, updated_at, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'Webinar',
                'On-Demand Webinar',
                wb['title'],
                ew_slug,
                wb['summary'] or '',
                wb['description'] or '',
                'Online',
                wb['duration'] or '',
                'On-Demand',
                'Published',
                1,
                'Watch On-Demand',
                0,
                'admin',
                now, now, now
            ))
            migrated += 1
            print(f"  [OK] Migrated webinar: {ew_slug}")
    except Exception as e:
        print(f"  [ERROR] Webinars migration failed: {e}")

    conn.commit()

    # ── Seed sample records for testing if table is still empty ────
    count = conn.execute("SELECT COUNT(*) FROM event_webinars").fetchone()[0]
    if count == 0:
        print("  [INFO] No legacy records found — seeding sample data...")
        _seed_samples(conn, now)

    conn.close()
    print(f"\nMigration complete. {migrated} records migrated.")

    try:
        from sync_event_admin_content import audit, sync

        print("\nSyncing admin-mapped speakers, agenda, takeaways, and highlight content...")
        sync(overwrite=False)
        missing = audit()
        if missing:
            raise RuntimeError(f"Event/Webinar admin mapping incomplete: {missing}")
    except Exception as exc:
        print(f"  [ERROR] Events/Webinars content sync failed: {exc}")
        raise

def _seed_samples(conn, now):
    """Seed a few sample records to populate the admin and test the UI."""
    samples = [
        {
            'content_type': 'Webinar',
            'webinar_format': 'Live Webinar',
            'title': 'Future Ready Data Foundation: From AI Pilot to Production Value',
            'slug': 'future-ready-data-foundation-2026',
            'short_description': 'Explores how organizations can build a future-ready data foundation that enables trusted, scalable, and AI-ready data pipelines.',
            'full_description': '''<p>Every organization is investing in AI. But most initiatives stall before production — not because models fail, but because data isn't ready.</p>
<p>In this webinar, our experts walk through the critical requirements for a production-ready AI data foundation: data quality, integration, governance, real-time access, and accountability.</p>''',
            'theme': 'Data Ready for AI',
            'topic_category': 'AI Data Foundation',
            'start_datetime': '2026-07-15T10:00:00',
            'end_datetime': '2026-07-15T11:30:00',
            'timezone': 'America/New_York',
            'display_time_text': '10:00 AM EST | 3:00 PM BST | 7:30 PM IST',
            'location_type': 'Online',
            'lifecycle_status': 'Upcoming',
            'publishing_status': 'Published',
            'registration_required': 1,
            'registration_form_title': 'Register for This Webinar',
            'registration_cta_text': 'Register Now',
            'thank_you_message': 'Thank you for registering! You will receive a confirmation email with your join link shortly.',
            'countdown_enabled': 1,
            'seo_title': 'Future Ready Data Foundation Webinar 2026 | Artha Solutions',
            'seo_description': 'Join our live webinar to learn how to build a trusted, scalable, AI-ready data foundation. Register now.',
            'ai_summary': 'This live webinar is designed for data leaders and analytics teams, covering the critical requirements for production-ready AI data foundations including data quality, governance, and real-time pipeline architecture.',
        },
        {
            'content_type': 'Webinar',
            'webinar_format': 'On-Demand Webinar',
            'title': 'Active Data Governance: 100 Days to a Compliant Metadata Catalog',
            'slug': 'active-data-governance-100-days',
            'short_description': 'Learn how to stand up a fully compliant metadata catalog in under 100 days using Talend and Artha\'s accelerator frameworks.',
            'full_description': '<p>Traditional data governance initiatives fail because they take years to show value. This webinar shows how organizations can connect critical databases, tag sensitive PII fields, and map lineages in a fraction of the time.</p>',
            'theme': 'Active Data Governance',
            'topic_category': 'Data Governance',
            'start_datetime': '2025-11-20T11:00:00',
            'end_datetime': '2025-11-20T12:30:00',
            'timezone': 'America/New_York',
            'location_type': 'Online',
            'recording_link': 'https://player.vimeo.com/video/1180502062',
            'recording_duration': '75 minutes',
            'recording_access_type': 'redirect',
            'lifecycle_status': 'On-Demand',
            'publishing_status': 'Published',
            'registration_required': 1,
            'registration_cta_text': 'Watch On-Demand',
            'thank_you_message': 'Thank you! You now have access to the on-demand recording.',
            'countdown_enabled': 0,
            'seo_title': 'On-Demand: Active Data Governance in 100 Days | Artha Solutions',
            'seo_description': 'Watch our on-demand webinar on building a compliant metadata catalog in 100 days with Talend and Artha.',
            'ai_summary': 'This on-demand webinar is for data governance leads and compliance teams, covering metadata cataloging, PII tagging, and lineage mapping using Talend accelerator frameworks.',
        },
        {
            'content_type': 'Event',
            'event_format': 'Conference',
            'title': 'Artha Solutions at Qlik Connect 2026',
            'slug': 'qlik-connect-2026',
            'short_description': 'Meet the Artha Solutions team at Qlik Connect 2026 — the premier data and analytics conference in North America.',
            'full_description': '<p>Join us at Booth #SS15 at the Gaylord Palms Resort & Convention Center, Kissimmee, Florida. Our team will showcase AI-ready data foundations, ETL modernization, MDM solutions, and live demos of the Artha DIP Platform.</p>',
            'theme': 'Qlik + Talend Services',
            'topic_category': 'Data Analytics Conference',
            'start_datetime': '2026-04-13T09:00:00',
            'end_datetime': '2026-04-15T17:00:00',
            'timezone': 'America/New_York',
            'location_type': 'In-Person',
            'location': 'Gaylord Palms Resort & Convention Center, Kissimmee, Florida, USA',
            'lifecycle_status': 'Completed',
            'publishing_status': 'Published',
            'registration_required': 0,
            'registration_cta_text': 'Learn More',
            'countdown_enabled': 0,
            'seo_title': 'Artha at Qlik Connect 2026 | Booth #SS15 | Florida',
            'seo_description': 'Artha Solutions at Qlik Connect 2026. Visit us at Booth #SS15 for live demos of our AI data platforms.',
            'ai_summary': 'This event is for data and analytics professionals attending Qlik Connect 2026, where Artha Solutions showcases AI-ready data foundations, MDM, and ETL modernization at Booth #SS15.',
        },
        {
            'content_type': 'Event',
            'event_format': 'In-Person Event',
            'title': 'Qlik AI Reality Tour 2025 — Bengaluru',
            'slug': 'qlik-ai-reality-tour-bengaluru-2025',
            'short_description': 'An exclusive event in Bengaluru to help organizations turn data, analytics, and AI initiatives into real business impact.',
            'full_description': '<p>Hosted by Artha Solutions, the Qlik AI Reality Tour 2025 brings together data leaders across India to explore practical AI strategies, real-world use cases, and embedding intelligence into enterprise workflows.</p>',
            'theme': 'Data Ready for AI',
            'topic_category': 'AI & Analytics',
            'start_datetime': '2025-11-27T09:00:00',
            'end_datetime': '2025-11-27T18:00:00',
            'timezone': 'Asia/Kolkata',
            'location_type': 'In-Person',
            'location': 'Bengaluru, Karnataka, India',
            'lifecycle_status': 'Completed',
            'publishing_status': 'Published',
            'registration_required': 0,
            'registration_cta_text': 'Learn More',
            'countdown_enabled': 0,
            'seo_title': 'Qlik AI Reality Tour 2025 Bengaluru | Artha Solutions',
            'seo_description': 'Artha Solutions hosts the Qlik AI Reality Tour 2025 in Bengaluru. Discover practical AI strategies and real-world use cases.',
            'ai_summary': 'This in-person event is designed for data and AI leaders in India, covering practical AI strategies, real-world use cases, and enterprise intelligence embedding, hosted by Artha Solutions.',
        },
    ]

    for s in samples:
        try:
            conn.execute('''
            INSERT INTO event_webinars (
                content_type, webinar_format, event_format, title, slug,
                short_description, full_description, theme, topic_category,
                start_datetime, end_datetime, timezone, display_time_text,
                location_type, location, recording_link, recording_duration,
                recording_access_type, lifecycle_status, publishing_status,
                registration_required, registration_form_title, registration_cta_text,
                thank_you_message, countdown_enabled,
                seo_title, seo_description, ai_summary,
                created_by, created_at, updated_at, published_at
            ) VALUES (
                :content_type, :webinar_format, :event_format, :title, :slug,
                :short_description, :full_description, :theme, :topic_category,
                :start_datetime, :end_datetime, :timezone, :display_time_text,
                :location_type, :location, :recording_link, :recording_duration,
                :recording_access_type, :lifecycle_status, :publishing_status,
                :registration_required, :registration_form_title, :registration_cta_text,
                :thank_you_message, :countdown_enabled,
                :seo_title, :seo_description, :ai_summary,
                'admin', :now, :now, :now
            )
            ''', {
                'webinar_format': s.get('webinar_format'),
                'event_format': s.get('event_format'),
                'display_time_text': s.get('display_time_text'),
                'location': s.get('location', ''),
                'recording_link': s.get('recording_link'),
                'recording_duration': s.get('recording_duration'),
                'recording_access_type': s.get('recording_access_type', 'redirect'),
                'registration_form_title': s.get('registration_form_title', 'Register to Attend'),
                'thank_you_message': s.get('thank_you_message', 'Thank you for registering!'),
                'countdown_enabled': s.get('countdown_enabled', 1),
                'now': now,
                **{k: s[k] for k in ['content_type','title','slug','short_description','full_description',
                                      'theme','topic_category','start_datetime','end_datetime','timezone',
                                      'location_type','lifecycle_status','publishing_status',
                                      'registration_required','registration_cta_text',
                                      'seo_title','seo_description','ai_summary']}
            })
            print(f"  [OK] Seeded sample: {s['slug']}")
        except sqlite3.IntegrityError:
            print(f"  [SKIP] Sample already exists: {s['slug']}")

    conn.commit()

if __name__ == '__main__':
    print("Running Events + Webinars unified migration...")
    migrate()
