"""
Backfill and audit unified Events/Webinars admin content.

The legacy public detail route used render-time enrichment for speakers,
takeaways, agenda, and highlight cards. The unified admin needs those values
stored in event_webinars and its child tables so admins can edit the real page
content.

Usage:
    python3 sync_event_admin_content.py
    python3 sync_event_admin_content.py --check
    python3 sync_event_admin_content.py --overwrite
"""

import argparse
import re
import sqlite3
from datetime import datetime, UTC

DB = "blog.db"

OPTIONAL_COLUMNS = {
    "event_label": "TEXT",
    "tags": "TEXT",
    "who_should_attend": "TEXT",
    "why_attend": "TEXT",
    "highlight_title": "TEXT",
    "highlight_text": "TEXT",
    "highlight_link": "TEXT",
    "custom_cta_text": "TEXT",
    "custom_cta_url": "TEXT",
    "resource_download_url": "TEXT",
    "calendar_details": "TEXT",
    "business_email_only": "INTEGER DEFAULT 1",
    "crm_integration_enabled": "INTEGER DEFAULT 1",
    "product_solution_id": "INTEGER",
    "partner_id": "INTEGER",
}

EVENT_CARD_IMAGES = [
    "/static/img/event_1.png",
    "/static/img/event_2.png",
    "/static/img/event_3.png",
    "/static/img/event_4.png",
    "/static/img/event_5.png",
    "/static/img/event_6.png",
]

SPEAKER_IMAGES = [
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&h=400&q=80",
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&h=400&q=80",
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&h=400&q=80",
    "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=400&h=400&q=80",
]


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def now_utc():
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def ensure_schema(conn):
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(event_webinars)").fetchall()}
    for name, definition in OPTIONAL_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE event_webinars ADD COLUMN {name} {definition}")


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def legacy_record(conn, event):
    if event["content_type"] == "Webinar":
        return one(conn, "SELECT * FROM webinars WHERE slug = ?", (event["slug"],))
    return one(conn, "SELECT * FROM events WHERE slug = ?", (event["slug"],))


def lower_blob(event, legacy):
    return " ".join([
        event.get("slug") or "",
        event.get("title") or "",
        (legacy or {}).get("title") or "",
        (legacy or {}).get("summary") or "",
        (legacy or {}).get("description") or "",
        (legacy or {}).get("location") or "",
    ]).lower()


def infer_theme(event, legacy):
    blob = lower_blob(event, legacy)
    tokens = set(re.findall(r"[a-z0-9]+", blob))
    if "sap" in blob or "s/4hana" in blob:
        return "SAP Data Modernization"
    if "retail" in blob or "customer 360" in blob or "customer-centricity" in blob:
        return "Retail Real-Time Insights"
    if "bfsi" in blob or "banking" in blob or "financial" in blob:
        return "BFSI Data Governance"
    if "governance" in blob or "metadata" in blob or "dpdp" in blob or "compliance" in blob:
        return "Active Data Governance"
    if "ai" in tokens or "future-ready" in blob:
        return "Data Ready for AI"
    if "qlik" in blob or "talend" in blob:
        return "Qlik + Talend Services"
    return "Enterprise Data Modernization"


def infer_topic(event, legacy):
    if event["content_type"] == "Webinar":
        if "SAP" in infer_theme(event, legacy):
            return "SAP Data Governance Webinar"
        if "AI" in infer_theme(event, legacy):
            return "AI Data Readiness Webinar"
        return "Data Governance Webinar"
    event_format = event.get("event_format") or "Event"
    return event_format


def speaker_set(title):
    title_lower = (title or "").lower()
    if "future-ready" in title_lower or "modernization" in title_lower or "spotlight" in title_lower:
        rows = [
            ("Stewart Bond", "Research VP, Data Intelligence", "IDC"),
            ("Srinivas Poddutoori", "COO & Co-Founder", "Artha Solutions"),
            ("Madhav", "Enterprise Intelligence Architect", "Artha Solutions"),
            ("Sidney Drill", "Product Marketer", "Qlik"),
        ]
    elif "sap" in title_lower:
        rows = [
            ("Graham Bailey", "SAP Modernization Lead", "Artha Solutions"),
            ("Holly A. Ray", "Director of Data Conversion", "SAP practice at Artha"),
            ("Clark Frogley", "Chief Enterprise Architect", "SAP North America"),
            ("Sara Crowe", "Database Conversion Consultant", "Artha Enterprise Solutions"),
        ]
    elif "governance" in title_lower or "agile" in title_lower:
        rows = [
            ("Graham Bailey", "Talend Practice Director", "Artha Solutions"),
            ("Holly A. Ray", "Lead Governance Architect", "Artha Solutions"),
            ("Clark Frogley", "Director of Data Quality", "Talend Inc."),
            ("Sara Crowe", "Global Compliance Director", "Data Sentinel"),
        ]
    elif "retail" in title_lower or "customer" in title_lower:
        rows = [
            ("Graham Bailey", "Retail Practice Lead", "Artha Solutions"),
            ("Holly A. Ray", "Director of Analytics", "Artha Retail Practice"),
            ("Clark Frogley", "VP of Solutions Consulting", "Qlik Retail Solutions"),
            ("Sara Crowe", "Customer Journey Analyst", "Artha Solutions"),
        ]
    else:
        rows = [
            ("Graham Bailey", "Chief Operating Officer", "Artha Solutions"),
            ("Holly A. Ray", "Head of Data and AI Solutions", "Artha Solutions"),
            ("Clark Frogley", "Financial Crime Advisory Director", "Artha Solutions"),
            ("Sara Crowe", "Director of Data Analysis & Intelligence", "Artha Solutions"),
        ]
    return [
        {
            "name": name,
            "designation": designation,
            "company": company,
            "image_path": SPEAKER_IMAGES[idx],
            "image_alt_text": f"{name} headshot",
            "short_bio": f"{name} brings practical enterprise experience as {designation} at {company}.",
            "full_bio": f"{name} helps enterprise teams connect governance, modernization, and analytics programs to measurable business outcomes.",
        }
        for idx, (name, designation, company) in enumerate(rows)
    ]


def content_blocks(title):
    title_lower = (title or "").lower()
    if "future-ready" in title_lower or "modernization" in title_lower or "spotlight" in title_lower:
        return {
            "takeaways": [
                "Why trusted data, ownership, lineage, timeliness, and access matter for enterprise AI adoption.",
                "How fragmented systems, inconsistent data, and weak governance slow down AI pilot scaling.",
                "What a strong AI-ready data foundation includes: quality, integration, governance, real-time access, and accountability.",
                "A practical roadmap to assess AI readiness, prioritize use cases, and scale value responsibly.",
            ],
            "highlight_title": "Building a Future-Ready Data Foundation: From AI Pilot to Production Value",
            "highlight_text": "Every organization is investing in AI, but most initiatives stall before production because data is not ready. Learn how to build a trusted, scalable, and AI-ready data foundation that unlocks enterprise value.",
            "highlight_link": "/resources/webinars",
        }
    if "sap" in title_lower:
        return {
            "takeaways": [
                "Why SAP S/4HANA migrations fail due to poor source data quality and how to prevent it.",
                "Best practices for real-time data validation workflows directly inside SAP creation portals.",
                "How to structure post-migration data governance policies to prevent database degradation over time.",
            ],
            "highlight_title": "Modernize your SAP data landscape with automated conversion frameworks",
            "highlight_text": "Moving to S/4HANA is not just an infrastructure project; it is a data quality project. Artha's data governance framework automates data auditing and conversion mapping to support a zero-loss transition.",
            "highlight_link": "/solutions/sap",
        }
    if "governance" in title_lower or "agile" in title_lower:
        return {
            "takeaways": [
                "How to stand up a compliant metadata catalog and data lineage map in under 100 days.",
                "Methods to automate data harvesting and schema tagging to reduce manual compliance search time.",
                "How to assign data stewardship responsibilities and enforce active data policies across teams.",
            ],
            "highlight_title": "Accelerate corporate compliance and catalog search speeds",
            "highlight_text": "Traditional data governance initiatives fail because they take years to show value. Artha accelerator frameworks with Talend metadata harvesting APIs help teams connect critical databases, tag sensitive fields, and map lineage faster.",
            "highlight_link": "/solutions/data-governance",
        }
    if "retail" in title_lower or "customer" in title_lower:
        return {
            "takeaways": [
                "How to unify point-of-sale logs, shipping systems, and payment gateway checkouts in real time.",
                "Techniques to de-duplicate customer files and resolve identities using machine-learning match rules.",
                "How to build high-performance data pipelines for real-time marketing personalization engines.",
            ],
            "highlight_title": "Establish a unified customer single source of truth",
            "highlight_text": "Siloed customer datasets prevent cohesive omnichannel experiences. Artha's Customer 360 reference architecture ingests, cleans, and consolidates payment events, web checkouts, and mobile activity into unified customer profiles.",
            "highlight_link": "/industries/retail",
        }
    return {
        "takeaways": [
            "How enterprise teams can identify the data capabilities needed for modern analytics programs.",
            "What operating model changes help keep data quality, access, and governance aligned.",
            "How Artha helps connect strategy, implementation, and measurable business outcomes.",
        ],
        "highlight_title": "Build a modern enterprise data foundation",
        "highlight_text": "Artha helps enterprise teams modernize data platforms, improve governance, and prepare trusted data for analytics, automation, and AI programs.",
        "highlight_link": "/solutions",
    }


def parse_date_for_display(value):
    if not value:
        return ""
    value = value.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%dT09:00:00")
        except ValueError:
            pass
    return ""


def webinar_datetime(slug):
    dates = {
        "100-days": "2026-06-15T10:00:00",
        "sap-data-governance": "2026-06-28T11:00:00",
        "sap-data-modernization": "2026-07-12T10:00:00",
        "customer-360": "2026-08-05T11:00:00",
        "balancing-modernization": "2026-08-24T11:00:00",
    }
    for key, value in dates.items():
        if key in slug:
            return value
    return ""


def display_time_text(event, legacy):
    slug = event["slug"]
    if event["content_type"] == "Webinar":
        if "100-days" in slug or "sap-data-modernization" in slug:
            return "10:00 AM EST - 3:00 PM BST - 7:30 PM IST"
        if "sap-data-governance" in slug or "balancing-modernization" in slug:
            return "11:00 AM EST - 4:00 PM BST - 8:30 PM IST"
        if "customer-360" in slug:
            return "11:00 AM SGT - 8:30 AM IST - 10:00 PM EST (-1d)"
        return "Available anytime" if event.get("webinar_format") == "On-Demand Webinar" else ""
    location = ((legacy or {}).get("location") or event.get("location") or "").lower()
    if "india" in slug or "delhi" in slug or "mumbai" in location or "bengaluru" in location:
        return "2:30 PM IST - 9:00 AM BST - 4:00 AM EST"
    if "indonesia" in slug or "jakarta" in location:
        return "1:00 PM WIB - 2:00 PM SGT - 11:30 AM IST"
    if "london" in slug or "uk" in location:
        return "10:00 AM BST - 5:00 AM EST - 2:30 PM IST"
    return "8:00 AM PST - 11:00 AM EST - 4:00 PM BST"


def location_type_and_format(event, legacy):
    if event["content_type"] == "Webinar":
        return "Online", "", "Webinar"
    location = ((legacy or {}).get("location") or event.get("location") or "").lower()
    if "hybrid" in location:
        return "Hybrid", "Hybrid Event", "Hybrid Event"
    if "virtual" in location or "online" in location:
        return "Online", "Virtual Event", "Virtual Event"
    if "summit" in (event.get("title") or "").lower():
        return "Hybrid" if "hybrid" in location else "In-Person", "Summit", "Summit"
    if "conference" in (event.get("title") or "").lower():
        return "In-Person", "Conference", "Conference"
    if "sponsored" in location or "qlik" in (event.get("title") or "").lower():
        return "In-Person", "Partner Event", "Partner Event"
    return "In-Person", "In-Person Event", "Event"


def agenda_for(event, takeaways):
    title_lower = (event.get("title") or "").lower()
    if event["content_type"] == "Webinar":
        return [
            (1, "00:00", "10 min", "Welcome and business context", "", "Why this topic matters now and what teams should prepare before starting."),
            (1, "10 min", "35 min", "Framework walkthrough", "", takeaways[0] if takeaways else "A practical walkthrough of the main framework."),
            (1, "35 min", "45 min", "Implementation roadmap and Q&A", "", "Recommended next steps, operating model considerations, and audience questions."),
        ]
    if "barc" in title_lower:
        return [
            (1, "08:00 AM", "10:00 AM", "Registration & Welcome Coffee", "Main Stage", "Pick up badges, conference guidebooks, and enjoy a warm welcome breakfast with peer attendees."),
            (1, "10:00 AM", "11:00 AM", "Keynote: Cloud Data Warehousing Trends", "Main Stage", "An executive overview of petabyte-scale data ingestion, multi-cloud clusters, and pricing optimization strategies."),
            (1, "11:00 AM", "12:00 PM", "Talend Integration Checkpoints", "Data Engineering", "Best practices to eliminate legacy ETL tool bottlenecks and accelerate conversion routines with Talend APIs."),
            (1, "12:00 PM", "01:00 PM", "Networking Lunch & Partner Exhibition", "Networking", "Explore interactive partner booths and network with fellow data engineering directors."),
            (1, "01:00 PM", "02:30 PM", "Panel: Master Data Governance Loops", "Governance", "Discussion on roles, consent frameworks, and automatic tags under regional compliance guidelines."),
            (2, "09:00 AM", "10:30 AM", "Deep-Dive: Modernizing Data Quality", "Workshop", "Interactive session showcasing machine-learning data de-duplication rules and real-time validation methods."),
            (2, "10:30 AM", "12:00 PM", "Case Study: BFSI Risk Mitigation", "Case Study", "Reviewing a compliance migration that cut SAP S/4HANA in-memory database costs."),
            (2, "01:00 PM", "02:30 PM", "Hands-on Lab: GenAI Readiness Pipelines", "Lab", "Learn to ingest records, structure schemas, and tag data indexes for AI programs."),
            (3, "09:30 AM", "11:00 AM", "Roundtable: Aligning Tech with Corporate Growth", "Roundtable", "Auditing database bottlenecks, purging redundant structures, and setting metadata catalog parameters."),
            (3, "11:00 AM", "12:30 PM", "Closing Panel: The Next Decade of Analytics", "Main Stage", "Predictive visual analytics, lakehouse architecture, and deployment guardrails."),
        ]
    if "retail" in title_lower or "compliance" in title_lower:
        return [
            (1, "08:00 AM", "10:00 AM", "Check-in & Registration", "Welcome", "Receive badges, welcome packages, and join the pre-event networking hub."),
            (1, "10:00 AM", "11:30 AM", "Omnichannel Checkout Pipelines", "Retail Data", "How retail networks integrate POS logs, shipping databases, and gateways in real time."),
            (1, "11:30 AM", "12:30 PM", "Talend Ingestion & Identity Deduplication", "Data Quality", "Automated conversions and match rules to establish a unified customer view."),
            (2, "09:00 AM", "10:30 AM", "Privacy Compliance and Customer Data", "Governance", "Mitigating security risks, role-based access management, and audit structures."),
            (2, "10:30 AM", "12:00 PM", "Customer 360 Personalization", "Analytics", "Feeding cleaned buyer profiles into real-time marketing and recommendation engines."),
        ]
    return [
        (1, "09:00 AM", "10:00 AM", "Welcome and opening keynote", "Main Stage", "Executive overview of the event theme and current enterprise data priorities."),
        (1, "10:00 AM", "11:30 AM", "Modern data foundation session", "Strategy", takeaways[0] if takeaways else "Frameworks for data quality, governance, and platform modernization."),
        (1, "11:30 AM", "12:30 PM", "Implementation patterns and case examples", "Delivery", takeaways[1] if len(takeaways) > 1 else "Practical examples from enterprise data transformation programs."),
        (1, "01:30 PM", "02:30 PM", "Expert panel and Q&A", "Panel", "Discussion with Artha specialists on risks, roadmap decisions, and next steps."),
    ]


def update_if_empty(conn, event_id, updates, overwrite):
    current = one(conn, "SELECT * FROM event_webinars WHERE id = ?", (event_id,))
    applied = {}
    for key, value in updates.items():
        if overwrite or not current.get(key):
            applied[key] = value
    if not applied:
        return 0
    applied["updated_at"] = now_utc()
    set_clause = ", ".join([f"{key} = ?" for key in applied])
    conn.execute(
        f"UPDATE event_webinars SET {set_clause} WHERE id = ?",
        list(applied.values()) + [event_id],
    )
    return len(applied)


def insert_children(conn, event, speakers, takeaways, agenda, overwrite):
    now = now_utc()
    event_id = event["id"]
    counts = {
        "speakers": conn.execute("SELECT COUNT(*) FROM event_speakers WHERE event_id = ?", (event_id,)).fetchone()[0],
        "takeaways": conn.execute("SELECT COUNT(*) FROM event_key_takeaways WHERE event_id = ?", (event_id,)).fetchone()[0],
        "agenda": conn.execute("SELECT COUNT(*) FROM event_agenda_items WHERE event_id = ?", (event_id,)).fetchone()[0],
    }
    if overwrite:
        conn.execute("DELETE FROM event_speakers WHERE event_id = ?", (event_id,))
        conn.execute("DELETE FROM event_key_takeaways WHERE event_id = ?", (event_id,))
        conn.execute("DELETE FROM event_agenda_items WHERE event_id = ?", (event_id,))
        counts = {"speakers": 0, "takeaways": 0, "agenda": 0}

    if counts["speakers"] == 0:
        for idx, speaker in enumerate(speakers):
            conn.execute(
                """
                INSERT INTO event_speakers (
                    event_id, name, designation, company, image_path, image_alt_text,
                    short_bio, full_bio, linkedin_url, profile_url, display_order,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, 1, ?, ?)
                """,
                (
                    event_id,
                    speaker["name"],
                    speaker["designation"],
                    speaker["company"],
                    speaker["image_path"],
                    speaker["image_alt_text"],
                    speaker["short_bio"],
                    speaker["full_bio"],
                    idx,
                    now,
                    now,
                ),
            )

    if counts["takeaways"] == 0:
        for idx, takeaway in enumerate(takeaways):
            conn.execute(
                """
                INSERT INTO event_key_takeaways (event_id, takeaway_text, display_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, takeaway, idx, now, now),
            )

    if counts["agenda"] == 0:
        for idx, item in enumerate(agenda):
            day, start, end, title, track, description = item
            conn.execute(
                """
                INSERT INTO event_agenda_items (
                    event_id, day_number, session_title, start_time, end_time,
                    speaker_id, track, description, display_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (event_id, day, title, start, end, track, description, idx, now, now),
            )


def sync(overwrite=False):
    conn = connect()
    ensure_schema(conn)
    events = [dict(row) for row in conn.execute("SELECT * FROM event_webinars ORDER BY id").fetchall()]
    touched = []
    for event in events:
        legacy = legacy_record(conn, event) or {}
        title = event.get("title") or legacy.get("title") or ""
        blocks = content_blocks(title)
        speakers = speaker_set(title)
        takeaways = blocks["takeaways"]
        agenda = agenda_for(event, takeaways)
        location_type, event_format, event_label = location_type_and_format(event, legacy)
        legacy_start = parse_date_for_display(legacy.get("date", ""))
        start_datetime = event.get("start_datetime") or legacy_start or webinar_datetime(event["slug"])
        card_image = legacy.get("card_image") or EVENT_CARD_IMAGES[(event["id"] - 1) % len(EVENT_CARD_IMAGES)]
        theme = infer_theme(event, legacy)
        updates = {
            "short_description": legacy.get("summary") or event.get("short_description") or "",
            "full_description": legacy.get("description") or event.get("full_description") or "",
            "theme": theme,
            "topic_category": infer_topic(event, legacy),
            "display_time_text": display_time_text(event, legacy),
            "start_datetime": start_datetime,
            "end_datetime": event.get("end_datetime") or start_datetime,
            "location": legacy.get("location") or event.get("location") or ("Online" if event["content_type"] == "Webinar" else ""),
            "location_type": location_type,
            "event_format": event_format,
            "event_label": event_label if event["content_type"] == "Event" else (event.get("webinar_format") or "Webinar"),
            "recording_duration": legacy.get("duration") or event.get("recording_duration") or "",
            "registration_form_title": "Access On-Demand Webinar" if event.get("webinar_format") == "On-Demand Webinar" else f"Register for {event['content_type']}",
            "registration_cta_text": "Watch On-Demand" if event.get("webinar_format") == "On-Demand Webinar" else "Register Now",
            "thank_you_message": event.get("thank_you_message") or "Thank you. Your registration has been received.",
            "featured_image": card_image,
            "hero_image": card_image,
            "highlight_title": blocks["highlight_title"],
            "highlight_text": blocks["highlight_text"],
            "highlight_link": blocks["highlight_link"],
            "related_solution_url": blocks["highlight_link"] if blocks["highlight_link"].startswith("/solutions") else "",
            "related_industry_url": blocks["highlight_link"] if blocks["highlight_link"].startswith("/industries") else "",
            "seo_title": event.get("seo_title") or f"{title} | Artha Solutions",
            "seo_description": legacy.get("summary") or event.get("seo_description") or "",
            "og_title": event.get("og_title") or title,
            "og_description": legacy.get("summary") or event.get("og_description") or "",
            "og_image": event.get("og_image") or card_image,
            "ai_summary": event.get("ai_summary") or f"This {event['content_type'].lower()} is designed for enterprise data leaders and covers {theme}. Attendees will learn practical next steps for modernization, governance, and AI-ready data programs.",
            "business_email_only": 1,
            "crm_integration_enabled": 1,
        }
        updated = update_if_empty(conn, event["id"], updates, overwrite)
        insert_children(conn, event, speakers, takeaways, agenda, overwrite)
        touched.append((event["id"], event["slug"], updated))
    conn.commit()
    conn.close()
    return touched


def audit():
    conn = connect()
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT ew.id, ew.slug, ew.content_type, ew.title,
               COALESCE(ew.theme, '') as theme,
               COALESCE(ew.highlight_title, '') as highlight_title,
               COALESCE(ew.highlight_text, '') as highlight_text,
               COALESCE(ew.highlight_link, '') as highlight_link,
               COALESCE(ew.featured_image, '') as featured_image,
               COALESCE(ew.hero_image, '') as hero_image,
               (SELECT COUNT(*) FROM event_speakers s WHERE s.event_id = ew.id AND s.is_active = 1) as speakers,
               (SELECT COUNT(*) FROM event_key_takeaways t WHERE t.event_id = ew.id) as takeaways,
               (SELECT COUNT(*) FROM event_agenda_items a WHERE a.event_id = ew.id) as agenda
        FROM event_webinars ew
        ORDER BY ew.id
        """
    ).fetchall()
    missing = []
    print("id | type | speakers | agenda | takeaways | mapped | slug")
    print("---|------|----------|--------|-----------|--------|-----")
    for row in rows:
        checks = [
            row["theme"],
            row["highlight_title"],
            row["highlight_text"],
            row["highlight_link"],
            row["featured_image"],
            row["hero_image"],
            row["speakers"] > 0,
            row["takeaways"] > 0,
            row["agenda"] > 0,
        ]
        ok = all(checks)
        if not ok:
            missing.append(row["slug"])
        print(f"{row['id']} | {row['content_type']} | {row['speakers']} | {row['agenda']} | {row['takeaways']} | {'yes' if ok else 'NO'} | {row['slug']}")
    conn.close()
    return missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Only audit mapping completeness.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite stored fields and child rows.")
    args = parser.parse_args()
    if not args.check:
        touched = sync(overwrite=args.overwrite)
        print(f"Synced {len(touched)} event/webinar records.")
    missing = audit()
    if missing:
        print("\nMissing mapped content:")
        for slug in missing:
            print(f"- {slug}")
        raise SystemExit(1)
    print("\nAll event/webinar records have admin-mapped content.")


if __name__ == "__main__":
    main()
