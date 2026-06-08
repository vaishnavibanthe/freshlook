from flask import Flask, render_template, request, jsonify, abort, redirect, session, send_file, make_response
import sqlite3

# Monkey-patch sqlite3.connect to use URI connection with nolock=1 under OneDrive
_original_sqlite3_connect = sqlite3.connect
def _patched_sqlite3_connect(database, *args, **kwargs):
    if database == 'blog.db':
        database = 'file:blog.db?nolock=1'
        kwargs['uri'] = True
    return _original_sqlite3_connect(database, *args, **kwargs)
sqlite3.connect = _patched_sqlite3_connect

from werkzeug.security import check_password_hash
from content_store import SOLUTIONS_DATA, INDUSTRIES_DATA, PARTNERS_DATA, ADVANTAGE_DATA, SAP_PAGES_DATA, ENTERPRISE_APP_DATA, AI_PAGES_DATA, EVENTS_DATA, WEBINARS_DATA, WHITEPAPERS_DATA, JOBS_DATA
import os
import re
import csv
import io
import json
import time
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from werkzeug.utils import secure_filename
import pdf_extractor

app = Flask(__name__)
app.secret_key = 'artha-solutions-super-secret-key-2026'

# Configure Jinja2 to cache templates and disable auto-reloading to prevent OneDrive sync lock timeouts
app.config['TEMPLATES_AUTO_RELOAD'] = False
app.jinja_env.auto_reload = False

serializer = URLSafeTimedSerializer(app.secret_key)

# Global rate limiting cache for downloads: {ip: [timestamps]}
DOWNLOAD_RATE_LIMIT = {}

def get_db_connection():
    conn = sqlite3.connect('blog.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_db_events():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM events").fetchall()
        if rows:
            return {r['slug']: dict(r) for r in rows}
    except Exception as e:
        print(f"Error reading events: {e}")
    finally:
        conn.close()
    return EVENTS_DATA

def get_db_webinars():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM webinars").fetchall()
        if rows:
            return {r['slug']: dict(r) for r in rows}
    except Exception as e:
        print(f"Error reading webinars: {e}")
    finally:
        conn.close()
    return WEBINARS_DATA

# Inject data registries into template contexts globally
def get_navigation_fallback():
    return {
        'items': [
            {
                'id': 991,
                'label': 'Artha Advantage',
                'url': '/artha-advantage',
                'icon': None,
                'is_featured': 0,
                'groups': [
                    {
                        'label': 'Accelerators',
                        'items': [
                            {'id': 9911, 'label': 'Data Insights Platform (DIP)', 'url': '/artha-advantage/data-insights-platform', 'description': 'Comprehensive, AI-driven solution to streamline Data Governance', 'icon': None},
                            {'id': 9912, 'label': 'MDM Lite', 'url': '/artha-advantage/mdm-lite', 'description': 'Cost-effective, easy-to-use platform to manage and centralize master data', 'icon': None},
                            {'id': 9913, 'label': 'Customer 360', 'url': '/artha-advantage/customer-360', 'description': 'A complete customer picture with unified data for actionable insights', 'icon': None},
                            {'id': 9914, 'label': 'Dynamic Ingestion Framework', 'url': '/artha-advantage/dynamic-ingestion-framework', 'description': 'Revolutionize Data Ingestion with Metadata-driven ETL', 'icon': None},
                            {'id': 9915, 'label': 'ETL Tool Migration', 'url': '/artha-advantage/technology-and-data-migration', 'description': 'Accelerate your ETL Tool Migration to Talend', 'icon': None},
                            {'id': 99110, 'label': 'AI SniffGuard', 'url': '/artha-advantage/ai-sniffguard', 'description': 'Real-time security, cost optimization & guardrails for LLM APIs', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Digital Transformation',
                        'items': [
                            {'id': 9916, 'label': 'Digital Strategy', 'url': '/artha-advantage/digital-transformation/digital-strategy', 'description': 'Differentiate digitally, optimize, engage, and succeed', 'icon': None},
                            {'id': 9917, 'label': 'Transformation Solutions & Services', 'url': '/artha-advantage/digital-transformation/digital-transformation-services', 'description': 'Unlock digital potential with innovative solutions and ongoing support', 'icon': None}
                        ]
                    },
                    {
                        'label': 'SAP Modernization',
                        'items': [
                            {'id': 9918, 'label': 'Artha Advantage for SAP', 'url': '/artha-advantage-for-sap', 'description': 'Comprehensive SAP migration for data quality and accelerated transition', 'icon': None},
                            {'id': 9919, 'label': 'B’etl™ – The ETL Migrator', 'url': '/artha-advantage/technology-and-data-migration', 'description': "Modernization doesn't have to be hard. With B’etl™, it isn't.", 'icon': None}
                        ]
                    }
                ],
                'featured_card': None
            },
            {
                'id': 992,
                'label': 'Solutions',
                'url': '#',
                'icon': None,
                'is_featured': 0,
                'groups': [
                    {
                        'label': 'Data Solutions',
                        'items': [
                            {'id': 9921, 'label': 'Data Strategy', 'url': '/solutions/data-strategy', 'description': 'Align business goals with data potential', 'icon': None},
                            {'id': 9922, 'label': 'Master Data Management', 'url': '/solutions/master-data-management', 'description': 'Single source of truth for critical entity data', 'icon': None},
                            {'id': 9923, 'label': 'Enterprise Data Management', 'url': '/solutions/enterprise-data-management', 'description': 'Build scalable pipelines and data lakes', 'icon': None},
                            {'id': 9924, 'label': 'Data Governance', 'url': '/solutions/data-governance', 'description': 'Security, quality, and compliance for confidence', 'icon': None},
                            {'id': 9925, 'label': 'Big Data', 'url': '/solutions/big-data', 'description': 'Real-time processing and massive scalability', 'icon': None},
                            {'id': 9926, 'label': 'Data Quality', 'url': '/industries/data-quality', 'description': 'Clean, consistent, and reliable datasets', 'icon': None},
                            {'id': 9927, 'label': 'Data Science & Analytics', 'url': '/solutions/data-science-analytics', 'description': 'AI/ML predictive analytics and visual intelligence', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Artificial Intelligence',
                        'items': [
                            {'id': 9928, 'label': 'AI Solutions Hub', 'url': '/artificial-intelligence', 'description': "Overview of Artha's Generative AI consulting & engineering", 'icon': None},
                            {'id': 9929, 'label': 'AI Data Readiness', 'url': '/artificial-intelligence/data-readiness', 'description': 'Prepare data foundations for model ingestion & RAG', 'icon': None},
                            {'id': 99210, 'label': 'Intelligent Decisions', 'url': '/artificial-intelligence/intelligent-solutions', 'description': 'AutoML forecasting, pricing engines, and scenario simulations', 'icon': None},
                            {'id': 99211, 'label': 'Workflow Automation', 'url': '/artificial-intelligence/ai-workflow-automation-process-optimization', 'description': 'Orchestrate tasks and automate document processing loops', 'icon': None},
                            {'id': 99212, 'label': 'Human Engagement', 'url': '/artificial-intelligence/ai-human-engagement-experience', 'description': 'Conversational agents, copilots, and CCaaS QA scoring', 'icon': None},
                            {'id': 99213, 'label': 'Platform Engineering', 'url': '/artificial-intelligence/ai-platform-engineering-services', 'description': 'Set up MLOps/LLMOps pipelines, lakehouses, & guardrails', 'icon': None},
                            {'id': 99214, 'label': 'AI ROI Solutions', 'url': '/artificial-intelligence/ai-roi-solutions', 'description': 'Outcome-driven frameworks like MAAC & SniffGuard', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Enterprise Applications',
                        'items': [
                            {'id': 99215, 'label': 'SAP Modernization', 'url': '/solutions/sap', 'description': 'SAP migration, integration, and platform upgrades', 'icon': None},
                            {'id': 99216, 'label': 'ServiceNow Services', 'url': '/enterprise-application/service-now', 'description': 'Optimize IT workflows and enterprise operations', 'icon': None},
                            {'id': 99217, 'label': 'Oracle Consulting', 'url': '/enterprise-application/oracle', 'description': 'Upgrade ERP, databases, and financial systems', 'icon': None},
                            {'id': 99218, 'label': 'Cloud Services', 'url': '/cloud', 'description': 'Multi-cloud migration, strategy, and architecture', 'icon': None},
                            {'id': 99219, 'label': 'Managed Services', 'url': '/managed-services', 'description': '24/7 proactive data platform administration', 'icon': None}
                        ]
                    }
                ],
                'featured_card': {
                    'title': 'Future-Ready Data Foundation',
                    'description': 'Learn how to move from AI pilots to full scale enterprise production value in this IDC Spotlight report.',
                    'label': 'Featured Spotlight',
                    'cta_text': 'Download Report',
                    'cta_url': '/events/future-ready-data-foundation-from-ai-pilot-to-production-value'
                }
            },
            {
                'id': 993,
                'label': 'Industries',
                'url': '#',
                'icon': None,
                'is_featured': 0,
                'groups': [
                    {
                        'label': 'Selected Success Stories',
                        'items': [
                            {'id': 9931, 'label': 'Enhanced Data Governance', 'url': '/case-studies', 'description': 'Reduced metadata search time by 40% and improved data accuracy by 65% for financial operations.', 'icon': None},
                            {'id': 9932, 'label': 'Analytics Modernization', 'url': '/case-studies', 'description': 'Improved data visibility, safeguard data security, and scale data infrastructure for acquisition analytics.', 'icon': None},
                            {'id': 9933, 'label': 'Master Data Management', 'url': '/case-studies', 'description': 'Strengthened customer experience, compliance, and decision logic via unified MDM.', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Target Industries',
                        'items': [
                            {'id': 9934, 'label': 'Manufacturing', 'url': '/industries/manufacturing', 'description': '', 'icon': 'fas fa-industry'},
                            {'id': 9935, 'label': 'BFSI (Banking & Financial Services)', 'url': '/industries/bfsi', 'description': '', 'icon': 'fas fa-landmark'},
                            {'id': 9936, 'label': 'Retail & E-Commerce', 'url': '/industries/retail', 'description': '', 'icon': 'fas fa-shopping-cart'},
                            {'id': 9937, 'label': 'Healthcare & Life Sciences', 'url': '/industries/healthcare', 'description': '', 'icon': 'fas fa-hospital'},
                            {'id': 9938, 'label': 'Utilities & Energy', 'url': '/industries/utilities', 'description': '', 'icon': 'fas fa-tint'},
                            {'id': 9939, 'label': 'Hospitality & Travel', 'url': '/industries/hospitality', 'description': '', 'icon': 'fas fa-hotel'},
                            {'id': 99310, 'label': 'Telecommunications', 'url': '/industries/telecom', 'description': '', 'icon': 'fas fa-broadcast-tower'}
                        ]
                    }
                ],
                'featured_card': None
            },
            {
                'id': 994,
                'label': 'Resources',
                'url': '#',
                'icon': None,
                'is_featured': 0,
                'groups': [
                    {
                        'label': 'Featured Resources',
                        'items': [
                            {'id': 9941, 'label': 'Data Quality Guide', 'url': '/industries/data-quality', 'description': 'Clean, consistent, and well-governed data to drive your business success.', 'icon': None},
                            {'id': 9942, 'label': 'Master Data Management Frameworks', 'url': '/solutions/master-data-management', 'description': 'Improve data visibility, safeguard data security, and scale data infrastructure.', 'icon': None},
                            {'id': 9943, 'label': 'Data Governance Playbook', 'url': '/solutions/data-governance', 'description': 'Establish data quality, security, and compliance for better decision logic.', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Resource Center',
                        'items': [
                            {'id': 9944, 'label': 'Events & Summits', 'url': '/resources/events', 'description': '', 'icon': 'fas fa-calendar-alt'},
                            {'id': 9945, 'label': 'On-Demand Webinars', 'url': '/resources/webinars', 'description': '', 'icon': 'fas fa-video'},
                            {'id': 9946, 'label': 'Blogs & Insights', 'url': '/blogs', 'description': '', 'icon': 'fas fa-book-open'},
                            {'id': 9947, 'label': 'Whitepapers & Reports', 'url': '/resources/whitepapers', 'description': '', 'icon': 'fas fa-file-alt'},
                            {'id': 9948, 'label': 'Case Studies', 'url': '/case-studies', 'description': '', 'icon': 'fas fa-clipboard-list'},
                            {'id': 9949, 'label': 'On-Demand Workshop', 'url': '/resources/on-demand-workshop', 'description': '', 'icon': 'fas fa-tools'}
                        ]
                    }
                ],
                'featured_card': None
            },
            {
                'id': 995,
                'label': 'About Us',
                'url': '#',
                'icon': None,
                'is_featured': 0,
                'groups': [
                    {
                        'label': 'Technology Partners',
                        'items': [
                            {'id': 9951, 'label': 'Talend', 'url': '/partners/talend', 'description': 'Platinum Partner', 'icon': None},
                            {'id': 9952, 'label': 'Qlik', 'url': '/partners/qlik', 'description': 'Active Intelligence', 'icon': None},
                            {'id': 9953, 'label': 'Snowflake', 'url': '/partners/snowflake', 'description': 'Cloud Warehouse', 'icon': None},
                            {'id': 9954, 'label': 'AWS Cloud', 'url': '/partners/aws-cloud-services', 'description': 'Infrastructure', 'icon': None},
                            {'id': 9955, 'label': 'Azure Cloud', 'url': '/partners/azure-cloud-services', 'description': 'Solutions', 'icon': None},
                            {'id': 9956, 'label': 'Amurta DIP', 'url': '/partners/amurta-data-insights-platform', 'description': 'Governance', 'icon': None},
                            {'id': 9957, 'label': 'Data Sentinel', 'url': '/data-sentinel', 'description': 'Privacy & Compliance', 'icon': None},
                            {'id': 9958, 'label': 'Alation', 'url': '/alation-2', 'description': 'Data Catalog', 'icon': None}
                        ]
                    },
                    {
                        'label': 'Company',
                        'items': [
                            {'id': 9959, 'label': 'About Our Team', 'url': '/about-us', 'description': 'Empower businesses with insightful innovations', 'icon': None},
                            {'id': 99510, 'label': 'Partners Ecosystem', 'url': '/partners', 'description': 'Strategic alliances catering to all data requirements', 'icon': None},
                            {'id': 99512, 'label': 'Careers', 'url': '/careers', 'description': 'Be part of our dynamic enterprise consulting team', 'icon': None},
                            {'id': 99513, 'label': 'Request a Demo', 'url': '/contact-us', 'description': 'See our assessment framework in action', 'icon': None}
                        ]
                    }
                ],
                'featured_card': None
            }
        ],
        'ctas': [
            {'label': 'Talk to an Expert', 'url': '/contact-us', 'style': 'secondary'},
            {'label': 'Get Data Readiness Assessment', 'url': '/data-readiness-assessment', 'style': 'primary'}
        ]
    }

def load_navigation_menu():
    try:
        conn = sqlite3.connect('blog.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='navigation_menus'")
        if not cursor.fetchone():
            conn.close()
            return get_navigation_fallback()
            
        cursor.execute("SELECT id FROM navigation_menus WHERE location = 'header' AND status = 'Published' LIMIT 1")
        menu = cursor.fetchone()
        if not menu:
            conn.close()
            return get_navigation_fallback()
            
        menu_id = menu['id']
        
        cursor.execute("""
            SELECT * FROM navigation_items 
            WHERE menu_id = ? AND is_visible = 1 
            ORDER BY sort_order ASC
        """, (menu_id,))
        rows = cursor.fetchall()
        
        cursor.execute("""
            SELECT * FROM navigation_featured_cards
            WHERE menu_id = ? AND is_visible = 1
            ORDER BY sort_order ASC
        """, (menu_id,))
        card_rows = cursor.fetchall()
        
        featured_cards = {}
        for card in card_rows:
            featured_cards[card['parent_nav_item_id']] = dict(card)
            
        cursor.execute("""
            SELECT * FROM navigation_ctas
            WHERE is_visible = 1
            ORDER BY sort_order ASC
        """)
        cta_rows = cursor.fetchall()
        ctas = [dict(cta) for cta in cta_rows]
        
        conn.close()
        
        top_items = []
        child_items = []
        for r in rows:
            item = dict(r)
            if item['is_top_level']:
                top_items.append(item)
            else:
                child_items.append(item)
                
        children_by_parent = {}
        for c in child_items:
            pid = c['parent_id']
            if pid not in children_by_parent:
                children_by_parent[pid] = []
            children_by_parent[pid].append(c)
            
        menu_structure = []
        for parent in top_items:
            pid = parent['id']
            parent_id_children = children_by_parent.get(pid, [])
            
            groups = {}
            for child in parent_id_children:
                g_label = child['group_label'] or 'General'
                if g_label not in groups:
                    groups[g_label] = []
                groups[g_label].append(child)
                
            group_list = []
            for g_label, items in groups.items():
                group_list.append({
                    'label': g_label,
                    'items': items
                })
                
            parent['groups'] = group_list
            parent['featured_card'] = featured_cards.get(pid, None)
            menu_structure.append(parent)
            
        return {
            'items': menu_structure,
            'ctas': ctas
        }
    except Exception as e:
        print(f"Error loading navigation menu: {e}")
        return get_navigation_fallback()

@app.context_processor
def inject_global_data():
    def load_json_helper(val):
        if not val:
            return []
        try:
            return json.loads(val)
        except Exception:
            return []

    def get_case_study(slug):
        try:
            conn = sqlite3.connect('blog.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM case_studies WHERE slug=?", (slug,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception as e:
            print(f"Error fetching case study {slug}: {e}")
        return None

    return {
        'nav_solutions': SOLUTIONS_DATA,
        'nav_industries': INDUSTRIES_DATA,
        'nav_partners': PARTNERS_DATA,
        'nav_advantage': ADVANTAGE_DATA,
        'nav_sap_pages': SAP_PAGES_DATA,
        'nav_enterprise_apps': ENTERPRISE_APP_DATA,
        'nav_ai_pages': AI_PAGES_DATA,
        'nav_events': get_db_events(),
        'nav_webinars': get_db_webinars(),
        'nav_whitepapers': WHITEPAPERS_DATA,
        'nav_jobs': JOBS_DATA,
        'load_json_helper': load_json_helper,
        'get_case_study': get_case_study,
        'navigation_menu': load_navigation_menu()
    }

@app.template_filter('load_json')
def load_json_filter(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except Exception:
        return []

# 1. Main Static Routes
@app.route('/')
def home():
    # Fetch 3 latest published blog posts
    conn = get_db_connection()
    latest_posts = conn.execute("SELECT * FROM posts WHERE status = 'Published' ORDER BY date DESC LIMIT 3").fetchall()
    conn.close()
    
    # Compile events and webinars into a unified list
    combined_events = []
    
    for slug, item in get_db_events().items():
        loc_lower = item.get('location', '').lower()
        if 'virtual' in loc_lower or 'online' in loc_lower:
            del_type = 'Online'
        elif 'hybrid' in loc_lower:
            del_type = 'Hybrid'
        else:
            del_type = 'In-Person'
            
        combined_events.append({
            'type': 'Event',
            'slug': slug,
            'title': item.get('title'),
            'summary': item.get('summary'),
            'description': item.get('description'),
            'date_str': item.get('date'),
            'time': '10:00 AM EST' if 'north america' in item.get('title', '').lower() else '2:30 PM IST',
            'delivery_type': del_type,
            'location': item.get('location'),
            'url': f'/event-view/{slug}'
        })
        
    for slug, item in get_db_webinars().items():
        combined_events.append({
            'type': 'Webinar',
            'slug': slug,
            'title': item.get('title'),
            'summary': item.get('summary'),
            'description': item.get('description'),
            'date_str': 'On-Demand',
            'time': item.get('duration', '45 min'),
            'delivery_type': 'Online',
            'location': item.get('host', 'Artha Solutions'),
            'url': f'/webinar-view/{slug}'
        })
        
    # Sort chronologically: upcoming events first, then webinars alphabetically
    from datetime import datetime
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    def get_sort_key(ev):
        if ev['type'] == 'Webinar':
            return (1, ev['title'])
            
        dt_str = ev['date_str']
        try:
            parts = dt_str.replace(',', '').split()
            if len(parts) == 3:
                m = months.get(parts[0].lower(), 1)
                d = int(parts[1])
                y = int(parts[2])
                return (0, datetime(y, m, d))
        except Exception:
            pass
        return (0, datetime.max)
        
    combined_events.sort(key=get_sort_key)
    
    return render_template('home.html', 
                           active_page='home', 
                           latest_posts=latest_posts, 
                           events_list=combined_events)

@app.route('/artha-advantage')
def artha_advantage():
    return render_template('artha_advantage.html', active_page='artha_advantage')

@app.route('/artificial-intelligence')
def artificial_intelligence():
    return render_ai_page('ai-overview')

@app.route('/about-us')
def about_us():
    return render_template('about_us.html', active_page='about_us')

# ============================================================
#  CAREERS MODULE – Public Routes
# ============================================================

CAREERS_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'resumes')
ALLOWED_RESUME_EXTENSIONS = {'pdf', 'doc', 'docx'}
MAX_RESUME_SIZE_MB = 5

def _allowed_resume(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_RESUME_EXTENSIONS

def _get_career_jobs(status='published', department=None, location=None, job_type=None, search=None):
    conn = get_db_connection()
    query = "SELECT * FROM career_jobs WHERE status = ?"
    params = [status]
    if department:
        query += " AND department = ?"
        params.append(department)
    if location:
        query += " AND location LIKE ?"
        params.append(f'%{location}%')
    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)
    if search:
        query += " AND (title LIKE ? OR summary LIKE ? OR department LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    query += " ORDER BY posted_date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.route('/careers')
def careers():
    import json as _json
    jobs = _get_career_jobs()
    departments = sorted(set(j['department'] for j in jobs))
    locations_raw = [j['location'] for j in jobs]
    geographies = sorted(set(
        loc.split(',')[-1].strip() for loc in locations_raw
    ))
    job_types = sorted(set(j['job_type'] for j in jobs))
    return render_template(
        'careers.html',
        active_page='careers',
        jobs=jobs,
        departments=departments,
        geographies=geographies,
        job_types=job_types,
        json=_json
    )

@app.route('/careers/<slug>')
def career_job_detail(slug):
    import json as _json
    conn = get_db_connection()
    job = conn.execute("SELECT * FROM career_jobs WHERE slug = ? AND status = 'published'", (slug,)).fetchone()
    conn.close()
    if not job:
        abort(404)
    job = dict(job)
    # Parse JSON arrays
    for field in ['responsibilities', 'requirements']:
        if job.get(field):
            try:
                job[field] = _json.loads(job[field])
            except Exception:
                job[field] = [job[field]]
    # Related jobs (same department, excluding current)
    related = _get_career_jobs()
    related = [j for j in related if j['slug'] != slug][:3]
    return render_template('career_job_detail.html', job=job, related_jobs=related, active_page='careers')

@app.route('/careers/<slug>/apply', methods=['POST'])
def career_apply(slug):
    import json as _json
    conn = get_db_connection()
    job = conn.execute("SELECT * FROM career_jobs WHERE slug = ? AND status = 'published'", (slug,)).fetchone()
    conn.close()
    if not job:
        abort(404)
    job = dict(job)

    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    linkedin_url = request.form.get('linkedin_url', '').strip()
    cover_letter = request.form.get('cover_letter', '').strip()
    consent = request.form.get('consent', '')

    errors = []
    if not full_name:
        errors.append('Full name is required.')
    if not email or '@' not in email:
        errors.append('Valid email address is required.')
    if not consent:
        errors.append('You must consent to data processing.')

    resume_file = request.files.get('resume')
    resume_filename = None
    resume_path = None
    if not resume_file or resume_file.filename == '':
        errors.append('Resume/CV upload is mandatory.')
    elif not _allowed_resume(resume_file.filename):
        errors.append('Resume must be a PDF, DOC, or DOCX file.')
    else:
        content = resume_file.read()
        if len(content) > MAX_RESUME_SIZE_MB * 1024 * 1024:
            errors.append(f'Resume file must be under {MAX_RESUME_SIZE_MB} MB.')
        else:
            resume_file.seek(0)
            safe_name = secure_filename(resume_file.filename)
            timestamp = int(time.time())
            resume_filename = f"{timestamp}_{slug}_{safe_name}"
            resume_path = os.path.join(CAREERS_UPLOAD_FOLDER, resume_filename)
            os.makedirs(CAREERS_UPLOAD_FOLDER, exist_ok=True)
            resume_file.save(resume_path)

    if errors:
        job_copy = dict(job)
        for field in ['responsibilities', 'requirements']:
            if job_copy.get(field):
                try:
                    job_copy[field] = _json.loads(job_copy[field])
                except Exception:
                    pass
        related = _get_career_jobs()
        related = [j for j in related if j['slug'] != slug][:3]
        return render_template('career_job_detail.html', job=job_copy, related_jobs=related,
                               active_page='careers', form_errors=errors,
                               form_data={'full_name': full_name, 'email': email,
                                          'phone': phone, 'linkedin_url': linkedin_url,
                                          'cover_letter': cover_letter})

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO career_applications
        (job_id, job_title, full_name, email, phone, linkedin_url, cover_letter,
         resume_filename, resume_path, consent_given, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'new')
    """, (job['id'], job['title'], full_name, email, phone, linkedin_url, cover_letter,
          resume_filename, resume_path))
    conn.commit()
    conn.close()

    return render_template('career_apply_success.html', job=job, applicant_name=full_name,
                           active_page='careers')


# ============================================================
#  CAREERS MODULE – Admin Routes
# ============================================================

def _careers_admin_required():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    return None

@app.route('/admin/careers')
def admin_careers_dashboard():
    guard = _careers_admin_required()
    if guard: return guard
    conn = get_db_connection()
    jobs = conn.execute("SELECT * FROM career_jobs ORDER BY id DESC").fetchall()
    total_apps = conn.execute("SELECT COUNT(*) FROM career_applications").fetchone()[0]
    new_apps = conn.execute("SELECT COUNT(*) FROM career_applications WHERE status='new'").fetchone()[0]
    conn.close()
    return render_template('admin_careers_jobs.html', jobs=jobs, total_apps=total_apps,
                           new_apps=new_apps, active_admin='careers')

@app.route('/admin/careers/jobs/new', methods=['GET', 'POST'])
def admin_career_job_new():
    guard = _careers_admin_required()
    if guard: return guard
    import json as _json
    if request.method == 'POST':
        slug = re.sub(r'[^a-z0-9-]', '-', request.form.get('title', '').lower().strip()).strip('-')
        slug = re.sub(r'-+', '-', slug)
        responsibilities = request.form.get('responsibilities', '').strip()
        requirements = request.form.get('requirements', '').strip()
        # Try to convert newline-separated text to JSON array
        try:
            resp_list = [r.strip() for r in responsibilities.splitlines() if r.strip()]
            req_list = [r.strip() for r in requirements.splitlines() if r.strip()]
            responsibilities = _json.dumps(resp_list)
            requirements = _json.dumps(req_list)
        except Exception:
            pass
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO career_jobs (slug, title, department, location, job_type, summary,
                    description, responsibilities, requirements, additional_info, status, posted_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slug, request.form.get('title'), request.form.get('department'),
                request.form.get('location'), request.form.get('job_type', 'Full-Time'),
                request.form.get('summary'), request.form.get('description'),
                responsibilities, requirements, request.form.get('additional_info'),
                request.form.get('status', 'published'),
                request.form.get('posted_date', datetime.now().strftime('%Y-%m-%d'))
            ))
            conn.commit()
        except Exception as e:
            conn.close()
            return render_template('admin_career_job_edit.html', job=None,
                                   error=str(e), active_admin='careers')
        conn.close()
        return redirect('/admin/careers')
    return render_template('admin_career_job_edit.html', job=None, active_admin='careers')

@app.route('/admin/careers/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
def admin_career_job_edit(job_id):
    guard = _careers_admin_required()
    if guard: return guard
    import json as _json
    conn = get_db_connection()
    job = conn.execute("SELECT * FROM career_jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        abort(404)
    job = dict(job)
    if request.method == 'POST':
        responsibilities = request.form.get('responsibilities', '').strip()
        requirements = request.form.get('requirements', '').strip()
        try:
            resp_list = [r.strip() for r in responsibilities.splitlines() if r.strip()]
            req_list = [r.strip() for r in requirements.splitlines() if r.strip()]
            responsibilities = _json.dumps(resp_list)
            requirements = _json.dumps(req_list)
        except Exception:
            pass
        conn2 = get_db_connection()
        conn2.execute("""
            UPDATE career_jobs SET title=?, department=?, location=?, job_type=?, summary=?,
            description=?, responsibilities=?, requirements=?, additional_info=?, status=?,
            posted_date=?, updated_at=datetime('now') WHERE id=?
        """, (
            request.form.get('title'), request.form.get('department'),
            request.form.get('location'), request.form.get('job_type', 'Full-Time'),
            request.form.get('summary'), request.form.get('description'),
            responsibilities, requirements, request.form.get('additional_info'),
            request.form.get('status', 'published'),
            request.form.get('posted_date'), job_id
        ))
        conn2.commit()
        conn2.close()
        return redirect('/admin/careers')
    # Format JSON arrays as newline-separated text for editing
    for field in ['responsibilities', 'requirements']:
        if job.get(field):
            try:
                items = _json.loads(job[field])
                job[field] = '\n'.join(items)
            except Exception:
                pass
    conn.close()
    return render_template('admin_career_job_edit.html', job=job, active_admin='careers')

@app.route('/admin/careers/jobs/<int:job_id>/delete', methods=['POST', 'GET'])
def admin_career_job_delete(job_id):
    guard = _careers_admin_required()
    if guard: return guard
    conn = get_db_connection()
    conn.execute("DELETE FROM career_jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/careers')

@app.route('/admin/careers/applications')
def admin_career_applications():
    guard = _careers_admin_required()
    if guard: return guard
    job_filter = request.args.get('job_id', '')
    status_filter = request.args.get('status', '')
    conn = get_db_connection()
    query = """
        SELECT a.*, j.title as job_title_ref, j.slug as job_slug
        FROM career_applications a
        LEFT JOIN career_jobs j ON a.job_id = j.id
        WHERE 1=1
    """
    params = []
    if job_filter:
        query += " AND a.job_id = ?"
        params.append(job_filter)
    if status_filter:
        query += " AND a.status = ?"
        params.append(status_filter)
    query += " ORDER BY a.submitted_at DESC"
    applications = conn.execute(query, params).fetchall()
    jobs = conn.execute("SELECT id, title FROM career_jobs ORDER BY title").fetchall()
    conn.close()
    return render_template('admin_career_applications.html', applications=applications,
                           jobs=jobs, job_filter=job_filter, status_filter=status_filter,
                           active_admin='careers')

@app.route('/admin/careers/applications/<int:app_id>/status', methods=['POST'])
def admin_career_app_status(app_id):
    guard = _careers_admin_required()
    if guard: return guard
    new_status = request.form.get('status', 'new')
    notes = request.form.get('notes', '')
    conn = get_db_connection()
    conn.execute("""
        UPDATE career_applications SET status=?, notes=?, updated_at=datetime('now')
        WHERE id=?
    """, (new_status, notes, app_id))
    conn.commit()
    conn.close()
    return redirect('/admin/careers/applications')

@app.route('/admin/careers/applications/<int:app_id>/download-resume')
def admin_career_download_resume(app_id):
    guard = _careers_admin_required()
    if guard: return guard
    conn = get_db_connection()
    app_row = conn.execute("SELECT * FROM career_applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    if not app_row or not app_row['resume_path']:
        abort(404)
    return send_file(app_row['resume_path'], as_attachment=True,
                     download_name=app_row['resume_filename'])

@app.route('/admin/careers/applications/export')
def admin_career_export_applications():
    guard = _careers_admin_required()
    if guard: return guard
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT a.id, a.full_name, a.email, a.phone, a.linkedin_url,
               j.title as job, a.status, a.submitted_at, a.resume_filename
        FROM career_applications a
        LEFT JOIN career_jobs j ON a.job_id = j.id
        ORDER BY a.submitted_at DESC
    """).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Email', 'Phone', 'LinkedIn', 'Job Applied', 'Status', 'Submitted', 'Resume'])
    for row in rows:
        writer.writerow([row['id'], row['full_name'], row['email'], row['phone'],
                         row['linkedin_url'], row['job'], row['status'],
                         row['submitted_at'], row['resume_filename']])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = 'attachment; filename=career_applications.csv'
    return resp

@app.route('/solutions')
def solutions_index():
    return render_template('solutions.html', active_page='solutions')

@app.route('/partners')
def partners_index():
    return render_template('partners.html', active_page='partners')

# 2. Dynamic Details Engines
@app.route('/solutions/<slug>')
def solution_detail(slug):
    if slug not in SOLUTIONS_DATA:
        abort(404)
    data = SOLUTIONS_DATA[slug]
    
    # Dedicated templates for specific solutions pages
    if slug == 'data-strategy':
        return render_template('data_strategy_detail.html', data=data, slug=slug, active_page='solutions')
    if slug == 'master-data-management':
        return render_template('master_data_management_detail.html', data=data, slug=slug, active_page='solutions')
    if slug == 'enterprise-data-management':
        return render_template('enterprise_data_management_detail.html', data=data, slug=slug, active_page='solutions')
    if slug == 'data-governance':
        return render_template('data_governance_detail.html', data=data, slug=slug, active_page='solutions')
    if slug in ('bigdata', 'big-data'):
        return render_template('bigdata_detail.html', data=data, slug='bigdata', active_page='solutions')
    if slug == 'data-quality':
        return render_template('data_quality_detail.html', data=data, slug=slug, active_page='solutions')
    if slug == 'data-science-analytics':
        return render_template('data_science_analytics_detail.html', data=data, slug=slug, active_page='solutions')
    if slug == 'sap':
        return render_template('sap.html', data=data, slug=slug, active_page='solutions')
        
    return render_template('solution_detail.html', data=data, slug=slug, active_page='solutions')

@app.route('/industries/<slug>')
def industry_detail(slug):
    if slug not in INDUSTRIES_DATA:
        abort(404)
    data = INDUSTRIES_DATA[slug]
    
    # Dedicated template for utilities
    if slug == 'utilities':
        return render_template('industry_utilities.html', data=data, slug=slug, active_page='industries')
    # Dedicated template for hospitality
    if slug == 'hospitality':
        return render_template('industry_hospitality.html', data=data, slug=slug, active_page='industries')
    # Dedicated template for telecom
    if slug == 'telecom':
        return render_template('industry_telecom.html', data=data, slug=slug, active_page='industries')
        
    return render_template('industry_detail.html', data=data, slug=slug, active_page='industries')

@app.route('/partners/<slug>')
def partner_detail(slug):
    if slug not in PARTNERS_DATA:
        abort(404)
    data = PARTNERS_DATA[slug]
    
    # Dedicated templates for specific partner pages
    if slug == 'talend':
        return render_template('partner_talend.html', data=data, slug=slug, active_page='partners')
    if slug == 'qlik':
        return render_template('partner_qlik.html', data=data, slug=slug, active_page='partners')
    if slug == 'snowflake':
        return render_template('partner_snowflake.html', data=data, slug=slug, active_page='partners')
    if slug == 'aws-cloud-services':
        return render_template('partner_aws.html', data=data, slug=slug, active_page='partners')
    if slug == 'azure-cloud-services':
        return render_template('partner_azure.html', data=data, slug=slug, active_page='partners')
    if slug == 'amurta-data-insights-platform':
        return render_template('partner_amurta.html', data=data, slug=slug, active_page='partners')
    if slug == 'data-sentinel':
        return render_template('partner_data_sentinel.html', data=data, slug=slug, active_page='partners')
    if slug == 'alation':
        return render_template('partner_alation.html', data=data, slug=slug, active_page='partners')
        
    return render_template('partner_detail.html', data=data, slug=slug, active_page='partners')

# 2.5 Sitemap-specific Overviews and Redirects
@app.route('/data-solutions')
def data_solutions():
    return render_template('data_solutions.html', active_page='solutions')

@app.route('/sap')
def sap_overview():
    return redirect('/solutions/sap', code=301)

@app.route('/enterprise-application')
def enterprise_application_overview():
    return render_template('enterprise_application.html', active_page='solutions')

@app.route('/industries')
def industries_overview():
    return render_template('industries.html', active_page='industries')

@app.route('/resources')
def resources_overview():
    return render_template('resources.html', active_page='resources')

@app.route('/resources/blogs')
def resources_blogs_redirect():
    return redirect('/blogs')

@app.route('/resources/case-studies')
def resources_case_studies_redirect():
    return redirect('/case-studies')

@app.route('/resources/events')
def resources_events():
    return render_template('resources_list.html', items=get_db_events(), type='Event', title='Upcoming Events & Summits', active_page='resources')

@app.route('/resources/webinars')
def resources_webinars():
    return render_template('resources_list.html', items=get_db_webinars(), type='Webinar', title='On-Demand Webinars', active_page='resources')

@app.route('/resources/whitepapers')
def resources_whitepapers():
    return render_template('resources_list.html', items=WHITEPAPERS_DATA, type='Whitepaper', title='Resource Whitepapers', active_page='resources')

@app.route('/resources/on-demand-workshop')
def resources_workshop():
    workshop_data = {
        'title': 'On-Demand Data Modernization Workshop',
        'tagline': 'Evaluate legacy platforms and build custom data roadmaps with our engineers.',
        'description': 'A tailored 2-hour session with our senior cloud database and integration architects. We will discuss cloud migrations, data quality validation checks, active governance practices, and LLM implementation guidelines.',
        'features': [
            {'title': 'Platform Assessment', 'desc': 'Understand database sizing, query performance, and indexing bottlenecks.'},
            {'title': 'Architecture Design', 'desc': 'Draft high-level diagrams connecting database inputs to cloud warehouses.'},
            {'title': 'AI Readiness Check', 'desc': 'Evaluate schema quality and profiling strategies to support production AI.'}
        ]
    }
    return render_template('advantage_detail.html', data=workshop_data, slug='on-demand-workshop', active_page='resources')

# 2.6 Sitemap Specific Detail Pages & Aliases
@app.route('/cloud')
def cloud_solution_alias():
    return redirect('/solutions/cloud')

@app.route('/managed-services')
def managed_services_alias():
    return redirect('/solutions/managed-services')

@app.route('/artha-advantage-for-sap')
def artha_advantage_sap():
    return redirect('/solutions/sap')

@app.route('/data-readiness')
def data_readiness_alias():
    data = AI_PAGES_DATA['data-readiness']
    return render_template('solution_detail.html', data=data, slug='data-readiness', active_page='solutions')

@app.route('/data-sentinel')
def data_sentinel_alias():
    return redirect('/partners/data-sentinel')

@app.route('/alation-2')
def alation_alias():
    return redirect('/partners/alation')

@app.route('/solutions/big-data')
def big_data_alias():
    return redirect('/solutions/bigdata')

@app.route('/industries/data-quality')
def industries_data_quality():
    return redirect('/solutions/data-quality')

@app.route('/industries-manufacturing')
def industries_manufacturing():
    return redirect('/industries/manufacturing')

@app.route('/industries/banking')
def industries_banking():
    return redirect('/industries/bfsi')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html', active_page='home')

@app.route('/careers/clients')
def careers_clients():
    return redirect('/careers', 301)

@app.route('/artha-advantage/ai-sniffguard')
def ai_sniffguard_landing():
    page = {
        'seo_title': 'AI SniffGuard: Active Middleware Cost & Security Guardrails',
        'seo_description': 'SniffGuard sits as an active layer between your endpoints and LLM APIs, handling prompt caching, rate limits, model fallbacks, and PII masking.',
        'seo_keywords': 'AI cost, LLM security, prompt caching, PII masking, guardrails, API audit',
        'title': 'AI SniffGuard'
    }
    return render_template('ai_sniffguard.html', page=page, active_subpage='roi-solutions', active_page='solutions')

@app.route('/artificial-intelligence/ai-roi-framework')
def ai_roi_framework_landing():
    page = {
        'seo_title': 'AI ROI Solutions Framework: Governed Production AI at Scale',
        'seo_description': 'A robust framework that connects your data pipelines to customized neural models, custom RAG indexes, and automated action loops.',
        'seo_keywords': 'AI ROI framework, RAG indexing, fine-tuning, data lineage, MAAC orchestration',
        'title': 'AI ROI Solutions Framework'
    }
    return render_template('ai_roi_framework.html', page=page, active_subpage='roi-solutions', active_page='solutions')

@app.route('/data-readiness-assessment')
def data_readiness_assessment_landing():
    page = {
        'seo_title': 'Intelligent Data Assessment Platform | Artha Solutions',
        'seo_description': 'Assess your current data, governance, and control maturity before AI risk becomes business risk. Get an evidence-gated readiness assessment for just $1.',
        'seo_keywords': 'AI data readiness, data governance assessment, DCAM, NIST AI RMF, ISO 42001, data quality audit',
        'title': 'Intelligent Data Assessment Platform'
    }
    return render_template('data_readiness_assessment.html', page=page, active_subpage='data-readiness', active_page='solutions')


@app.route('/artificial-intelligence/<slug>')
def ai_detail(slug):
    clean_slug = slug.strip('/')
    page_key = f"ai-{clean_slug}"
    
    conn = get_db_connection()
    db_slug = f"artificial-intelligence/{clean_slug}"
    row = conn.execute("SELECT page_key FROM industry_microsite_pages WHERE slug = ? OR page_key = ?", (db_slug, page_key)).fetchone()
    conn.close()
    
    if row:
        return render_ai_page(row['page_key'])
        
    if clean_slug not in AI_PAGES_DATA:
        abort(404)
    data = AI_PAGES_DATA[clean_slug]
    return render_template('solution_detail.html', data=data, slug=clean_slug, active_page='solutions')

@app.route('/artha-advantage/<path:slug>')
def advantage_detail(slug):
    # Strip trailing slash if present
    clean_slug = slug.strip('/')
    # If nested digital-transformations/digital-strategy, grab digital-strategy
    if '/' in clean_slug:
        clean_slug = clean_slug.split('/')[-1]
    if clean_slug not in ADVANTAGE_DATA:
        abort(404)
    data = ADVANTAGE_DATA[clean_slug]
    # Dedicated templates for specific advantage pages
    if clean_slug == 'digital-transformations':
        return render_template('digital_transformations_landing.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'digital-strategy':
        return render_template('digital_strategy.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'digital-transformation-services':
        return render_template('digital_transformation_services.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'technology-and-data-migration':
        return render_template('betl_migration.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'data-insights-platform':
        return render_template('dip_platform.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'mdm-lite':
        return render_template('mdm_lite.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'customer-360':
        return render_template('customer_360.html', data=data, slug=clean_slug, active_page='artha_advantage')
    if clean_slug == 'dynamic-ingestion-framework':
        return render_template('dynamic_ingestion_framework.html', data=data, slug=clean_slug, active_page='artha_advantage')
    return render_template('advantage_detail.html', data=data, slug=clean_slug, active_page='solutions')

@app.route('/solutions/sap/<slug>')
def sap_microsite_detail(slug):
    clean_slug = slug.strip('/')
    if clean_slug not in SAP_PAGES_DATA:
        abort(404)
    data = SAP_PAGES_DATA[clean_slug]
    return render_template('sap_detail.html', data=data, slug=clean_slug, active_page='solutions')

@app.route('/sap/<slug>')
def sap_detail(slug):
    clean_slug = slug.strip('/')
    return redirect(f'/solutions/sap/{clean_slug}', code=301)

@app.route('/enterprise-application/<slug>')
def enterprise_app_detail(slug):
    clean_slug = slug.strip('/')
    if clean_slug not in ENTERPRISE_APP_DATA:
        abort(404)
    data = ENTERPRISE_APP_DATA[clean_slug]
    return render_template('solution_detail.html', data=data, slug=clean_slug, active_page='solutions')

def enrich_resource_data(data, slug, type_name):
    # Create a copy so we don't mutate the global state in content_store.py
    enriched = dict(data)
    
    # Resolve Date & Timezones
    if type_name == 'Event':
        original_date = data.get('date', 'Upcoming')
        try:
            parts = original_date.replace(',', '').split()
            if len(parts) == 3:
                enriched['timezone_date'] = f"{parts[1]} {parts[0][:3]}"
            else:
                enriched['timezone_date'] = original_date
        except Exception:
            enriched['timezone_date'] = original_date
        
        if 'india' in slug or 'delhi' in slug:
            enriched['timezone_times'] = '2:30 PM IST • 9:00 AM BST • 4:00 AM EST'
        elif 'indonesia' in slug or 'asean' in slug:
            enriched['timezone_times'] = '1:00 PM WIB • 2:00 PM SGT • 11:30 AM IST'
        elif 'london' in slug or 'uk' in slug:
            enriched['timezone_times'] = '10:00 AM BST • 5:00 AM EST • 2:30 PM IST'
        else:
            enriched['timezone_times'] = '8:00 AM PST • 11:00 AM EST • 4:00 PM BST'
            
        loc_lower = data.get('location', '').lower()
        enriched['is_in_person'] = not ('virtual' in loc_lower or 'online' in loc_lower or 'hybrid' in loc_lower)
    elif type_name == 'Webinar':
        # Webinar / Whitepaper
        enriched['is_in_person'] = False
        if '100-days' in slug:
            enriched['timezone_date'] = '15 June'
            enriched['timezone_times'] = '10:00 AM EST • 3:00 PM BST • 7:30 PM IST'
        elif 'sap-data-governance' in slug:
            enriched['timezone_date'] = '28 June'
            enriched['timezone_times'] = '11:00 AM EST • 4:00 PM BST • 8:30 PM IST'
        elif 'sap-data-modernization' in slug:
            enriched['timezone_date'] = '12 July'
            enriched['timezone_times'] = '10:00 AM EST • 3:00 PM BST • 7:30 PM IST'
        elif 'customer-360' in slug:
            enriched['timezone_date'] = '05 Aug'
            enriched['timezone_times'] = '11:00 AM SGT • 8:30 AM IST • 10:00 PM EST (-1d)'
        elif 'balancing-modernization' in slug:
            enriched['timezone_date'] = '24 Aug'
            enriched['timezone_times'] = '11:00 AM EST • 4:00 PM BST • 8:30 PM IST'
        elif 'future-ready' in slug:
            enriched['timezone_date'] = 'On Demand'
            enriched['timezone_times'] = 'Available Anytime'
            enriched['video_url'] = 'https://player.vimeo.com/video/1180502062'
        else:
            enriched['timezone_date'] = '27 July'
            enriched['timezone_times'] = '8:00 AM PST • 11:00 AM EST • 4:00 PM BST'
    elif type_name == 'Whitepaper':
        enriched['timezone_date'] = data.get('pages', 'PDF Report')
        enriched['timezone_times'] = f"Published by: {data.get('author', 'Artha Research')}"
        enriched['speakers'] = []
        enriched['takeaways'] = [
            "In-depth analysis of legacy data modernization strategies for enterprise networks.",
            "Detailed architectural review of data quality, metadata cataloging, and integration checkpoints.",
            "Step-by-step implementation guide to achieve regulatory compliance and audit readiness."
        ]
        enriched['highlight_title'] = data.get('title', 'Executive Technical Whitepaper')
        enriched['highlight_text'] = data.get('description', '') or data.get('summary', '')
        enriched['highlight_link'] = "www.thinkartha.com/resources"

    # Build Speakers
    title_lower = data.get('title', '').lower()
    if 'future-ready' in title_lower or 'modernization' in title_lower or 'spotlight' in title_lower:
        enriched['speakers'] = [
            {
                'name': 'Stewart Bond',
                'role': 'Research VP, Data Intelligence',
                'company': 'IDC',
                'image_url': 'https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'cyan'
            },
            {
                'name': 'Srinivas Poddutoori',
                'role': 'COO & Co-Founder',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'violet'
            },
            {
                'name': 'Madhav',
                'role': 'Enterprise Intelligence Architect',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'orange'
            },
            {
                'name': 'Sidney Drill',
                'role': 'Product Marketer',
                'company': 'Qlik',
                'image_url': 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'yellow'
            }
        ]
    elif 'sap' in title_lower:
        enriched['speakers'] = [
            {
                'name': 'Graham Bailey',
                'role': 'SAP Modernization Lead',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'cyan'
            },
            {
                'name': 'Holly A. Ray',
                'role': 'Director of Data Conversion',
                'company': 'SAP practice at Artha',
                'image_url': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'yellow'
            },
            {
                'name': 'Clark Frogley',
                'role': 'Chief Enterprise Architect',
                'company': 'SAP North America',
                'image_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'orange'
            },
            {
                'name': 'Sara Crowe',
                'role': 'Database Conversion Consultant',
                'company': 'Artha Enterprise Solutions',
                'image_url': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'violet'
            }
        ]
    elif 'governance' in title_lower or 'agile' in title_lower:
        enriched['speakers'] = [
            {
                'name': 'Graham Bailey',
                'role': 'Talend Practice Director',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'cyan'
            },
            {
                'name': 'Holly A. Ray',
                'role': 'Lead Governance Architect',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'yellow'
            },
            {
                'name': 'Clark Frogley',
                'role': 'Director of Data Quality',
                'company': 'Talend Inc.',
                'image_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'orange'
            },
            {
                'name': 'Sara Crowe',
                'role': 'Global Compliance Director',
                'company': 'Data Sentinel',
                'image_url': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'violet'
            }
        ]
    elif 'retail' in title_lower or 'customer' in title_lower:
        enriched['speakers'] = [
            {
                'name': 'Graham Bailey',
                'role': 'Retail Practice Lead',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'cyan'
            },
            {
                'name': 'Holly A. Ray',
                'role': 'Director of Analytics',
                'company': 'Artha Retail Practice',
                'image_url': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'yellow'
            },
            {
                'name': 'Clark Frogley',
                'role': 'VP of Solutions Consulting',
                'company': 'Qlik Retail Solutions',
                'image_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'orange'
            },
            {
                'name': 'Sara Crowe',
                'role': 'Customer Journey Analyst',
                'company': 'Artha Solutions',
                'image_url': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'violet'
            }
        ]
    else:
        # Default/Fallback matches the Polaris design style
        enriched['speakers'] = [
            {
                'name': 'Graham Bailey',
                'role': 'Chief Operating Officer',
                'company': 'Quantifind',
                'image_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'cyan'
            },
            {
                'name': 'Holly A. Ray',
                'role': 'Head of AML/AFC Solutions America',
                'company': 'Quantexa',
                'image_url': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'yellow'
            },
            {
                'name': 'Clark Frogley',
                'role': 'Financial Crime Advisory Director',
                'company': 'Quantexa',
                'image_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'orange'
            },
            {
                'name': 'Sara Crowe',
                'role': 'Director of Data Analysis & Intelligence',
                'company': 'Polaris Project',
                'image_url': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=400&h=400&q=80',
                'accent_class': 'violet'
            }
        ]

    # Build takeaways and highlight details based on context
    if 'future-ready' in title_lower or 'modernization' in title_lower or 'spotlight' in title_lower:
        enriched['takeaways'] = [
            "Why trusted data, ownership, lineage, timeliness, and access now matter more than ever for enterprise AI adoption.",
            "How fragmented systems, inconsistent data, and weak governance slow down AI pilot scaling.",
            "What a strong AI-ready data foundation includes: quality, integration, governance, real-time access, and accountability.",
            "A practical roadmap for enterprises to assess AI readiness, prioritize use cases, and scale value responsibly."
        ]
        enriched['highlight_title'] = "Building a Future-Ready Data Foundation: From AI Pilot to Production Value"
        enriched['highlight_text'] = "Every organization is investing in AI. But most initiatives stall before production. Not because models fail, but because data isn’t ready. Data sits across systems, defined differently, owned by different teams, and stitched together to power AI. Learn how you can build a trusted, scalable, and AI-ready data foundation to unlock true enterprise value."
        enriched['highlight_link'] = "/resources/webinars"
    elif 'sap' in title_lower:
        enriched['takeaways'] = [
            "Why SAP S/4HANA migrations fail due to poor source data quality and how to prevent it.",
            "Best practices for establishing real-time data validation workflows directly inside SAP creation portals.",
            "How to structure post-migration data governance policies to prevent database degradation over time."
        ]
        enriched['highlight_title'] = "Modernize your SAP data landscape with automated conversion frameworks"
        enriched['highlight_text'] = "Moving to S/4HANA is not just an infrastructure project; it's a data quality project. Legacy data inconsistencies, duplicate vendor accounts, and obsolete material categories can trigger severe ERP transaction failures. Our proven data governance framework automates data auditing and conversion mapping to ensure a zero-loss transition."
        enriched['highlight_link'] = "/solutions/sap"
    elif 'governance' in title_lower or 'agile' in title_lower:
        enriched['takeaways'] = [
            "How to stand up a fully compliant metadata catalog and data lineage map in under 100 days.",
            "Methods to automate data harvesting and schema tagging to reduce manual compliance search time.",
            "How to assign data stewardship responsibilities and enforce active data policies across teams."
        ]
        enriched['highlight_title'] = "Accelerate corporate compliance and catalog search speeds"
        enriched['highlight_text'] = "Traditional data governance initiatives fail because they take years to show value. By combining Artha's accelerator frameworks with Talend's metadata harvesting APIs, organizations can connect critical databases, tag sensitive PII fields, and map lineages in a fraction of the time."
        enriched['highlight_link'] = "/solutions/data-governance"
    elif 'retail' in title_lower or 'customer' in title_lower:
        enriched['takeaways'] = [
            "How to unify point-of-sale logs, shipping systems, and payment gateway checkouts in real-time.",
            "Techniques to de-duplicate customer files and resolve identities using ML-based match rules.",
            "How to build high-performance data pipelines to feed real-time marketing personalization engines."
        ]
        enriched['highlight_title'] = "Establish a unified customer single source of truth"
        enriched['highlight_text'] = "Siloed customer datasets prevent retailers from delivering cohesive omnichannel experiences. Our Customer 360 reference architecture shows how to ingestion, clean, and consolidate payment events, web checkouts, and mobile activity into unified customer profiles that drive direct marketing ROI."
        enriched['highlight_link'] = "/industries/retail"
    else:
        # Default / Polaris themed
        enriched['takeaways'] = [
            "Why you need to look more closely at the businesses surrounding human trafficking. Polaris's groundbreaking typology report breaks down the broad categories of labor trafficking and sex trafficking into 25 distinct business models, each with their own specific way of operating.",
            "What red flags frequently appear in investigations and what companies and financial institutions should look for in the future.",
            "How contextual monitoring leverages open-source intelligence and network graphs to link one bad indicator to a networked criminal organization driving sex or labor trafficking."
        ]
        enriched['highlight_title'] = "Unraveling human trafficking by leveraging open source contextual intelligence"
        enriched['highlight_text'] = "Human trafficking is a multi-billion dollar criminal industry that denies freedom to 24.9 million people around the world. In some cases, traffickers trick, defraud or physically force victims into selling sex or working in inhumane conditions. By tracking financial signals and corporate shell records, investigators can dismantle these rings."
        enriched['highlight_link'] = "www.polarisproject.org"

    # Build schedule/agenda for in-person events
    if enriched.get('is_in_person'):
        original_date = data.get('date', 'Oct 14, 2026')
        day1_date = original_date
        day2_date = "Next Day"
        day3_date = "Following Day"
        try:
            parts = original_date.replace(',', '').split()
            if len(parts) == 3:
                m = parts[0][:3]
                d = int(parts[1])
                y = parts[2]
                day1_date = f"{m} {d}, {y}"
                day2_date = f"{m} {d+1}, {y}"
                day3_date = f"{m} {d+2}, {y}"
        except Exception:
            pass

        title_lower = data.get('title', '').lower()
        if 'barc' in title_lower:
            enriched['agenda_days'] = [
                {
                    'label': 'Day 01',
                    'date_str': day1_date,
                    'sessions': [
                        {'time_range': '08:00 AM - 10:00 AM', 'title': 'Registration & Welcome Coffee', 'description': 'Pick up badges, conference guidebooks, and enjoy a warm welcome breakfast with peer attendees.'},
                        {'time_range': '10:00 AM - 11:00 AM', 'title': 'Keynote: Cloud Data Warehousing Trends', 'description': 'An executive overview of petabyte-scale data ingestion, multi-cloud clusters, and pricing optimization strategies.'},
                        {'time_range': '11:00 AM - 12:00 PM', 'title': 'Talend Integration Checkpoints', 'description': 'Best practices to eliminate legacy ETL tool bottlenecks and accelerate conversion routines with Talend APIs.'},
                        {'time_range': '12:00 PM - 01:00 PM', 'title': 'Networking Lunch & Partner Exhibition', 'description': 'Explore interactive partner booths and network with fellow data engineering directors.'},
                        {'time_range': '01:00 PM - 02:30 PM', 'title': 'Panel: Master Data Governance loops', 'description': 'Discussion on roles, consent frameworks, and automatic tags under regional compliance guidelines.'}
                    ]
                },
                {
                    'label': 'Day 02',
                    'date_str': day2_date,
                    'sessions': [
                        {'time_range': '09:00 AM - 10:30 AM', 'title': 'Deep-Dive: Modernizing Data Quality', 'description': 'Interactive session showcasing ML-based data de-duplication rules and real-time validation methods.'},
                        {'time_range': '10:30 AM - 12:00 PM', 'title': 'Case Study: BFSI Risk Mitigation', 'description': 'Reviewing a live compliance migration that cut S/4HANA in-memory database costs by 45%.'},
                        {'time_range': '12:00 PM - 01:00 PM', 'title': 'Lunch Break', 'description': 'Catered lunch and peer networking in the main exhibition hall.'},
                        {'time_range': '01:00 PM - 02:30 PM', 'title': 'Hands-on Lab: GenAI Readiness Pipelines', 'description': 'Bring your laptop. Learn to ingest database records, structure schemas, and tag LLM data indices.'},
                        {'time_range': '02:30 PM - 04:00 PM', 'title': 'Partner Showcase & Cocktails', 'description': 'Join the Qlik and Artha Solutions teams for drinks, project showcases, and giveaways.'}
                    ]
                },
                {
                    'label': 'Day 03',
                    'date_str': day3_date,
                    'sessions': [
                        {'time_range': '09:30 AM - 11:00 AM', 'title': 'Roundtable: Aligning Tech with Corporate Growth', 'description': 'Auditing database bottlenecks, purging redundant data structures, and establishing metadata catalog parameters.'},
                        {'time_range': '11:00 AM - 12:30 PM', 'title': 'Closing Panel: The Next Decade of Analytics', 'description': 'Predictive visual analytics, Lakehouse architecture, and MLOps deployment guardrails.'},
                        {'time_range': '12:30 PM - 01:30 PM', 'title': 'Closing Remarks & Farewell Lunch', 'description': 'Summary of key conference learnings, resource packages distribution, and final lunch.'}
                    ]
                }
            ]
        elif 'retail' in title_lower or 'compliance' in title_lower:
            enriched['agenda_days'] = [
                {
                    'label': 'Day 01',
                    'date_str': day1_date,
                    'sessions': [
                        {'time_range': '08:00 AM - 10:00 AM', 'title': 'Check-in & Registration', 'description': 'Receive badges, corporate welcome packages, and join the pre-summit networking hub.'},
                        {'time_range': '10:00 AM - 11:30 AM', 'title': 'Omnichannel Checkout Pipelines', 'description': 'How leading retail networks integrate POS checkout logs, shipping databases, and gateways in real-time.'},
                        {'time_range': '11:30 AM - 12:30 PM', 'title': 'Talend Ingestion & Identity Duplication', 'description': 'Automated conversions and ML match rules to establish a unified customer single source of truth.'},
                        {'time_range': '12:00 PM - 01:00 PM', 'title': 'Lunch Break', 'description': 'Networking lunch in the central atrium.'}
                    ]
                },
                {
                    'label': 'Day 02',
                    'date_str': day2_date,
                    'sessions': [
                        {'time_range': '09:00 AM - 10:30 AM', 'title': 'GDPR & Privacy Compliance', 'description': 'Mitigating security risks, role-based access management, and CCPA auditing structures.'},
                        {'time_range': '10:30 AM - 12:00 PM', 'title': 'Analytics: Customer 360 Personalization', 'description': 'Feeding cleaned buyer profiles into real-time marketing and recommendation engines.'},
                        {'time_range': '12:00 PM - 01:00 PM', 'title': 'Lunch Break', 'description': 'Catered peer dining in the main ballroom.'},
                        {'time_range': '01:00 PM - 03:00 PM', 'title': 'Panel: Future of Retail IT Architecture', 'description': 'Discussion on cloud database scaling, inventory synchronization, and IoT shop floor systems.'}
                    ]
                },
                {
                    'label': 'Day 03',
                    'date_str': day3_date,
                    'sessions': [
                        {'time_range': '10:00 AM - 12:00 PM', 'title': 'Interactive Q&A Session', 'description': 'Open roundtable with retail practice directors, case study reviews, and closing lunch.'}
                    ]
                }
            ]
        else:
            # Fallback general tech agenda
            enriched['agenda_days'] = [
                {
                    'label': 'Day 01',
                    'date_str': day1_date,
                    'sessions': [
                        {'time_range': '08:00 AM - 10:00 AM', 'title': 'Registration & Welcome Breakfast', 'description': 'Pick up badges, conference brochures, and enjoy a warm welcome breakfast with peer attendees.'},
                        {'time_range': '10:00 AM - 11:30 AM', 'title': 'Introduction & Keynote Presentation', 'description': 'Executive overview of industry digital transformation trends, modern platforms, and active catalogs.'},
                        {'time_range': '11:30 AM - 12:30 PM', 'title': 'Emerging Technologies Architecture', 'description': 'A session covering cloud warehouses, real-time pipelines, and scalable enterprise platforms.'},
                        {'time_range': '12:30 PM - 01:30 PM', 'title': 'Networking Lunch', 'description': 'Catered networking lunch and partner display exhibition.'}
                    ]
                },
                {
                    'label': 'Day 02',
                    'date_str': day2_date,
                    'sessions': [
                        {'time_range': '09:00 AM - 10:30 AM', 'title': 'Deep-Dive: Ingestion & Data Quality', 'description': 'Addressing database bottlenecks, data de-duplication rules, and schema validation frameworks.'},
                        {'time_range': '10:30 AM - 12:00 PM', 'title': 'Compliance & Security Audits', 'description': 'GDPR, consent managers, and role-based access to keep systems secure and compliant.'},
                        {'time_range': '12:00 PM - 01:00 PM', 'title': 'Lunch Break', 'description': 'Buffet lunch and roundtable networking.'},
                        {'time_range': '01:00 PM - 02:30 PM', 'title': 'Panel Discussion: GenAI Readiness', 'description': 'Deploying LLM indexing, RAG architectures, and metadata catalogs in enterprise systems.'}
                    ]
                },
                {
                    'label': 'Day 03',
                    'date_str': day3_date,
                    'sessions': [
                        {'time_range': '10:00 AM - 12:00 PM', 'title': 'Expert Roundtable & Closing remarks', 'description': 'Key takeaways summary, download package distribution, and final networking lunch.'}
                    ]
                }
            ]

    return enriched

@app.route('/event-view/<slug>')
def event_view(slug):
    clean_slug = slug.strip('/')
    events = get_db_events()
    if clean_slug not in events:
        abort(404)
    data = enrich_resource_data(events[clean_slug], clean_slug, 'Event')
    return render_template('resource_detail.html', data=data, type='Event', slug=clean_slug, active_page='resources')

@app.route('/webinar-view/<slug>')
def webinar_view(slug):
    clean_slug = slug.strip('/')
    webinars = get_db_webinars()
    if clean_slug not in webinars:
        abort(404)
    data = enrich_resource_data(webinars[clean_slug], clean_slug, 'Webinar')
    return render_template('resource_detail.html', data=data, type='Webinar', slug=clean_slug, active_page='resources')

@app.route('/submit-resource-lead', methods=['POST'])
def submit_resource_lead():
    if request.form.get('website_url_honeypot'):
        return jsonify({'status': 'success', 'message': 'Registration received (spam filter active)'})
        
    now = time.time()
    ip = request.remote_addr or '127.0.0.1'
    ips_timestamps = DOWNLOAD_RATE_LIMIT.get(ip, [])
    ips_timestamps = [t for t in ips_timestamps if now - t < 60]
    if len(ips_timestamps) >= 5:
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded. Maximum 5 registrations per minute allowed.'}), 429
    ips_timestamps.append(now)
    DOWNLOAD_RATE_LIMIT[ip] = ips_timestamps
    
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('business_email', '').strip()
    company = request.form.get('company', '').strip()
    source_info = request.form.get('source_info', '').strip()
    resource_type = request.form.get('resource_type', '').strip()
    resource_slug = request.form.get('resource_slug', '').strip()
    resource_title = request.form.get('resource_title', '').strip()
    
    if not first_name or not last_name:
        return jsonify({'status': 'error', 'message': 'First name and last name are required.'}), 400
        
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    PERSONAL_DOMAINS = {
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    }
    
    email_parts = email.split('@')
    if len(email_parts) != 2:
        return jsonify({'status': 'error', 'message': 'Invalid email format.'}), 400
        
    domain = email_parts[1].lower().strip()
    if domain in PERSONAL_DOMAINS:
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    conn = get_db_connection()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO resource_leads (
            first_name, last_name, business_email, company, source_info,
            resource_type, resource_slug, resource_title, ip_address, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        first_name, last_name, email, company, source_info,
        resource_type, resource_slug, resource_title, ip, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'success',
        'message': f'Thank you, {first_name}! You have successfully registered for the {resource_type.lower()}. We have sent confirmation details to your email.'
    })

@app.route('/white-papers/<slug>')
def whitepaper_view(slug):
    clean_slug = slug.strip('/')
    if clean_slug not in WHITEPAPERS_DATA:
        abort(404)
    data = enrich_resource_data(WHITEPAPERS_DATA[clean_slug], clean_slug, 'Whitepaper')
    return render_template('resource_detail.html', data=data, type='Whitepaper', slug=clean_slug, active_page='resources')

@app.route('/blog/jobs/<slug>')
def job_view(slug):
    clean_slug = slug.strip('/')
    if clean_slug not in JOBS_DATA:
        abort(404)
    data = JOBS_DATA[clean_slug]
    return render_template('job_detail.html', data=data, slug=clean_slug, active_page='careers')

# 3. Blog Module Frontend Routes
def get_post_image(slug, category):
    category_images = {
        'AI & ML': 'https://images.unsplash.com/photo-1677442136019-21780efad99a?auto=format&fit=crop&w=800&q=85',
        'Data Solutions': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=85',
        'SAP Modernization': 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=800&q=85',
        'Cloud Services': 'https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=800&q=85',
        'Oracle Services': 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=800&q=85',
        'ServiceNow': 'https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=800&q=85',
        'Healthcare': 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=800&q=85',
        'Manufacturing': 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=85',
        'Retail': 'https://images.unsplash.com/photo-1534452286114-14ecb656f4cd?auto=format&fit=crop&w=800&q=85'
    }

    post_images = {
        'enhancing-recruitment-with-unified-talent-analytics': 'https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=800&q=85',
        'machine-learning-in-insurance-risk-management-a-strategic-guide-for-cios': 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=800&q=85',
        'master-data-management-in-manufacturing-powering-ai-sap-and-plm-integration': 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=85',
        'data-modernization-strategies-for-sap-in-manufacturing': 'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=800&q=85',
        'ai-data-readiness-services-for-enterprises': 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=800&q=85',
        'generative-ai-consulting-ai-implementation-services': 'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=800&q=85',
        'oracle-data-integration-solution': 'https://images.unsplash.com/photo-1544383835-bda2bc66a55d?auto=format&fit=crop&w=800&q=85',
        'cloud-based-data-pipelines-architecting-the-next-decade-of-retail-it': 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=800&q=85',
        'servicenow-data-integration-services': 'https://images.unsplash.com/photo-1531403009284-440f080d1e12?auto=format&fit=crop&w=800&q=85',
        'ai-powered-production-optimization-the-future-of-manufacturing': 'https://images.unsplash.com/photo-1563784462386-044fd95e9852?auto=format&fit=crop&w=800&q=85',
        'cloud-based-data-pipelines-architecting-the-next-decade-of-retail-it-20252030': 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=800&q=85',
        'cross-system-patient-data-sharing-breaking-down-the-real-data-barriers': 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=800&q=85',
        'customer-data-portal-for-retail-data-processes-architecture-and-operating-model': 'https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=800&q=85',
        'etl-migration-in-1-2-3-from-legacy-gridlock-to-automated-acceleration': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=85',
        'financial-data-quality-management-ensuring-accuracy-and-compliance': 'https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=800&q=85',
        'its-much-easier-to-migrate-from-informatica-to-qlik-than-you-think': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=85',
        'reinventing-customer-identity-how-ml-based-deduplication-is-transforming-banking-data-integrity': 'https://images.unsplash.com/photo-1601597111158-2fceff292cdc?auto=format&fit=crop&w=800&q=85',
        'streaming-data-processing-real-time-insights-for-retail': 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=800&q=85',
        'transforming-healthcare-with-data-artha-solutions-awarded-qlik-specialist-badge': 'https://images.unsplash.com/photo-1505751172876-fa1923c5c528?auto=format&fit=crop&w=800&q=85',
        'why-enterprises-are-moving-from-informatica-to-talend': 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=800&q=85'
    }

    # Match slug, fallback to category, fallback to global default
    img = post_images.get(slug)
    if not img:
        img = category_images.get(category)
    if not img:
        img = 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=85'
    return img

@app.route('/blogs')
def blogs_index():
    category = request.args.get('category')
    q = request.args.get('q')
    
    conn = get_db_connection()
    query = "SELECT * FROM posts WHERE status = 'Published'"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if q:
        query += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%'])
        
    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    
    # Convert SQLite row objects to dicts and attach resolved image_url
    posts = [dict(row) for row in rows]
    for post in posts:
        post['image_url'] = get_post_image(post['slug'], post['category'])
    
    # Get distinct categories for filters
    categories = [row['category'] for row in conn.execute("SELECT DISTINCT category FROM posts WHERE status = 'Published'").fetchall()]
    
    # Get popular posts (by views DESC)
    pop_rows = conn.execute("SELECT * FROM posts WHERE status = 'Published' ORDER BY views DESC LIMIT 4").fetchall()
    popular_posts = [dict(row) for row in pop_rows]
    for post in popular_posts:
        post['image_url'] = get_post_image(post['slug'], post['category'])
    
    # Get recent posts (by date DESC/id DESC)
    rec_rows = conn.execute("SELECT * FROM posts WHERE status = 'Published' ORDER BY id DESC LIMIT 4").fetchall()
    recent_posts = [dict(row) for row in rec_rows]
    for post in recent_posts:
        post['image_url'] = get_post_image(post['slug'], post['category'])
    
    # Get categories with counts
    category_counts = conn.execute("SELECT category, COUNT(*) as count FROM posts WHERE status = 'Published' GROUP BY category").fetchall()
    
    conn.close()
    
    return render_template('blogs.html', 
                           posts=posts, 
                           categories=categories, 
                           popular_posts=popular_posts,
                           recent_posts=recent_posts,
                           category_counts=category_counts,
                           active_page='blogs', 
                           selected_category=category, 
                           search_query=q)

@app.route('/blogs/<slug>')
def blog_detail(slug):
    conn = get_db_connection()
    post = conn.execute("SELECT * FROM posts WHERE slug = ? AND status = 'Published'", (slug,)).fetchone()
    
    if not post:
        conn.close()
        abort(404)
        
    # Increment views count
    conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post['id'],))
    conn.commit()
    
    # Fetch related articles
    related_rows = conn.execute("SELECT * FROM posts WHERE category = ? AND id != ? AND status = 'Published' LIMIT 3", (post['category'], post['id'])).fetchall()
    conn.close()
    
    # Convert sqlite3.Row to standard dictionaries
    post_dict = dict(post)
    post_dict['image_url'] = get_post_image(post_dict['slug'], post_dict['category'])
    
    related = [dict(row) for row in related_rows]
    for r in related:
        r['image_url'] = get_post_image(r['slug'], r['category'])
    
    return render_template('blog_detail.html', post=post_dict, related=related, active_page='blogs')

# 3.5. Case Studies Frontend Routes & APIs
@app.route('/case-studies')
def case_studies_index():
    industry = request.args.get('industry')
    solution_area = request.args.get('solution_area')
    technology = request.args.get('technology')
    region = request.args.get('region')
    q = request.args.get('q')
    sort_by = request.args.get('sort', 'recent')
    
    conn = get_db_connection()
    
    # 1. Industries
    industries_rows = conn.execute("SELECT DISTINCT industry FROM case_studies WHERE status = 'Published' AND industry != ''").fetchall()
    industries = [r['industry'] for r in industries_rows]
    
    # 2. Solution Areas
    solutions_rows = conn.execute("SELECT DISTINCT solution_area FROM case_studies WHERE status = 'Published' AND solution_area != ''").fetchall()
    solution_areas = [r['solution_area'] for r in solutions_rows]
    
    # 3. Regions
    regions_rows = conn.execute("SELECT DISTINCT region FROM case_studies WHERE status = 'Published' AND region != ''").fetchall()
    regions = [r['region'] for r in regions_rows]
    
    # 4. Technologies (technologies are comma-separated)
    tech_rows = conn.execute("SELECT technologies FROM case_studies WHERE status = 'Published' AND technologies != ''").fetchall()
    all_techs = set()
    for row in tech_rows:
        for t in row['technologies'].split(','):
            cleaned = t.strip()
            if cleaned:
                all_techs.add(cleaned)
    technologies = sorted(list(all_techs))
    
    filter_options = {
        'industries': sorted(industries),
        'solution_areas': sorted(solution_areas),
        'regions': sorted(regions),
        'technologies': technologies
    }
    
    # Base query for published studies
    query = "SELECT * FROM case_studies WHERE status = 'Published'"
    params = []
    
    # Apply filters
    if industry:
        query += " AND industry = ?"
        params.append(industry)
    if solution_area:
        query += " AND solution_area = ?"
        params.append(solution_area)
    if region:
        query += " AND region = ?"
        params.append(region)
    if technology:
        query += " AND technologies LIKE ?"
        params.append(f'%{technology}%')
    if q:
        query += " AND (title LIKE ? OR executive_summary LIKE ? OR business_challenge LIKE ? OR solution_summary LIKE ? OR business_outcomes LIKE ? OR technologies LIKE ? OR tags LIKE ?)"
        q_wild = f'%{q}%'
        params.extend([q_wild, q_wild, q_wild, q_wild, q_wild, q_wild, q_wild])
        
    # Sorting
    if sort_by == 'featured':
        query += " ORDER BY featured DESC, id DESC"
    else:
        query += " ORDER BY id DESC"
        
    case_studies = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template(
        'case_studies.html',
        case_studies=case_studies,
        filter_options=filter_options,
        selected_industry=industry,
        selected_solution_area=solution_area,
        selected_technology=technology,
        selected_region=region,
        search_query=q,
        sort_by=sort_by,
        active_page='case-studies'
    )

@app.route('/case-studies/<slug>')
def case_study_detail(slug):
    conn = get_db_connection()
    post = conn.execute("SELECT * FROM case_studies WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    
    if not post:
        abort(404)
        
    is_admin = session.get('logged_in', False)
    if post['status'] != 'Published' and not is_admin:
        abort(404)
        
    return render_template('case_study_detail.html', post=post, is_admin=is_admin, active_page='case-studies')

@app.route('/api/case-studies')
def api_case_studies_list():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, title, slug, industry, region, solution_area, technologies, executive_summary, status FROM case_studies WHERE status = 'Published'").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/case-studies/<slug>')
def api_case_study_detail(slug):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM case_studies WHERE slug = ? AND status = 'Published'", (slug,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))

@app.route('/api/case-studies/<slug>/download', methods=['POST'])
def case_study_gated_download(slug):
    if request.form.get('website_url_honeypot'):
        return jsonify({'status': 'success', 'token': 'mock-token-spam-detected'})
        
    now = time.time()
    ip = request.remote_addr or '127.0.0.1'
    ips_timestamps = DOWNLOAD_RATE_LIMIT.get(ip, [])
    ips_timestamps = [t for t in ips_timestamps if now - t < 60]
    if len(ips_timestamps) >= 5:
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded. Maximum 5 downloads per minute allowed.'}), 429
    ips_timestamps.append(now)
    DOWNLOAD_RATE_LIMIT[ip] = ips_timestamps
    
    email = request.form.get('business_email')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    company = request.form.get('company')
    job_title = request.form.get('job_title')
    phone = request.form.get('phone')
    country = request.form.get('country')
    consent = 1 if request.form.get('consent') else 0
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    PERSONAL_DOMAINS = {
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    }
    
    email_parts = email.split('@')
    if len(email_parts) != 2:
        return jsonify({'status': 'error', 'message': 'Invalid email format.'}), 400
        
    domain = email_parts[1].lower().strip()
    if domain in PERSONAL_DOMAINS:
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    conn = get_db_connection()
    study = conn.execute("SELECT id, title, pdf_file_path FROM case_studies WHERE slug = ?", (slug,)).fetchone()
    if not study:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Case study not found.'}), 404
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    utm_source = request.form.get('utm_source', '')
    utm_medium = request.form.get('utm_medium', '')
    utm_campaign = request.form.get('utm_campaign', '')
    utm_term = request.form.get('utm_term', '')
    utm_content = request.form.get('utm_content', '')
    referrer = request.form.get('referrer', '')
    source_url = request.form.get('source_url', '')
    user_agent = request.headers.get('User-Agent', '')
    
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO case_study_leads (
        case_study_id, business_email, first_name, last_name, company, job_title, phone, country, consent,
        source_url, referrer, utm_source, utm_medium, utm_campaign, utm_term, utm_content, ip_address, user_agent, downloaded_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        study['id'], email, first_name, last_name, company, job_title, phone, country, consent,
        source_url, referrer, utm_source, utm_medium, utm_campaign, utm_term, utm_content, ip, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    print(f"[CRM Webhook Sync] New Qualified Lead: {email} ({company or 'No Company'}) downloaded '{study['title']}' at {now_str}")
    
    token_payload = {
        'case_study_id': study['id'],
        'pdf_path': study['pdf_file_path'],
        'timestamp': time.time()
    }
    token = serializer.dumps(token_payload)
    
    return jsonify({'status': 'success', 'token': token})

@app.route('/case-studies/download-pdf/<token>')
def case_study_download_pdf(token):
    try:
        payload = serializer.loads(token, max_age=600)
    except SignatureExpired:
        return render_template('base.html', active_page='none'), 403
    except BadTimeSignature:
        return render_template('base.html', active_page='none'), 403
    except Exception:
        abort(403)
        
    pdf_path = payload.get('pdf_path')
    if not pdf_path or not os.path.exists(pdf_path):
        abort(404)
        
    file_name = os.path.basename(pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name=file_name)

@app.route('/sitemap.xml')
def sitemap_xml():
    conn = get_db_connection()
    posts = conn.execute("SELECT slug FROM posts WHERE status = 'Published'").fetchall()
    cases = conn.execute("SELECT slug, updated_at FROM case_studies WHERE status = 'Published'").fetchall()
    microsite_pages = conn.execute("SELECT url, noindex FROM industry_microsite_pages WHERE status = 'Published'").fetchall()
    conn.close()
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    static_pages = [
        ('/', '1.0'),
        ('/artha-advantage', '0.8'),
        ('/data-solutions', '0.8'),
        ('/artificial-intelligence', '0.8'),
        ('/about-us', '0.7'),
        ('/careers', '0.6'),
        ('/solutions', '0.8'),
        ('/partners', '0.7'),
        ('/blogs', '0.8'),
        ('/case-studies', '0.9'),
        ('/contact-us', '0.7')
    ]
    for page, priority in static_pages:
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com{page}</loc>\n    <priority>{priority}</priority>\n  </url>\n'
        
    for slug in SOLUTIONS_DATA.keys():
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com/solutions/{slug}</loc>\n    <priority>0.8</priority>\n  </url>\n'
        
    for slug in INDUSTRIES_DATA.keys():
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com/industries/{slug}</loc>\n    <priority>0.8</priority>\n  </url>\n'

    for page in microsite_pages:
        if page['noindex'] == 0 and page['url'] != '/industries/healthcare':
            xml_content += f'  <url>\n    <loc>https://www.thinkartha.com{page["url"]}</loc>\n    <priority>0.8</priority>\n  </url>\n'

    for slug in PARTNERS_DATA.keys():
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com/partners/{slug}</loc>\n    <priority>0.7</priority>\n  </url>\n'

    for post in posts:
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com/blogs/{post["slug"]}</loc>\n    <priority>0.6</priority>\n  </url>\n'
        
    for case in cases:
        date_str = case['updated_at'].split(' ')[0] if case['updated_at'] else "2026-05-30"
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com/case-studies/{case["slug"]}</loc>\n    <lastmod>{date_str}</lastmod>\n    <priority>0.8</priority>\n  </url>\n'
        
    xml_content += '</urlset>'
    
    from flask import Response
    return Response(xml_content, mimetype='application/xml')

@app.route('/search')
def universal_search():
    q = request.args.get('q', '').strip()
    results = {
        'blogs': [],
        'case_studies': [],
        'services': []
    }
    
    if q:
        q_lower = q.lower()
        conn = get_db_connection()
        
        # Search published blog posts
        blog_rows = conn.execute(
            "SELECT id, title, slug, summary, date, category FROM posts WHERE status = 'Published' AND (title LIKE ? OR content LIKE ? OR summary LIKE ?)",
            (f'%{q}%', f'%{q}%', f'%{q}%')
        ).fetchall()
        results['blogs'] = [dict(r) for r in blog_rows]
        
        # Search published case studies
        case_rows = conn.execute(
            "SELECT id, title, slug, card_summary, executive_summary, industry, solution_area FROM case_studies WHERE status = 'Published' AND (title LIKE ? OR executive_summary LIKE ? OR business_challenge LIKE ? OR solution_summary LIKE ? OR business_outcomes LIKE ? OR technologies LIKE ? OR tags LIKE ?)",
            (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%')
        ).fetchall()
        results['case_studies'] = [dict(r) for r in case_rows]
        
        conn.close()
        
        # Search solutions from content registry
        for slug, data in SOLUTIONS_DATA.items():
            title = data.get('title', '')
            desc = data.get('desc', '')
            content = data.get('pitch', '') + ' ' + ' '.join(data.get('benefits', []))
            if q_lower in title.lower() or q_lower in desc.lower() or q_lower in content.lower():
                results['services'].append({
                    'title': title,
                    'type': 'Solution',
                    'slug': slug,
                    'url': f'/solutions/{slug}',
                    'summary': desc
                })
                
        # Search industries from content registry
        for slug, data in INDUSTRIES_DATA.items():
            title = data.get('title', '')
            desc = data.get('desc', '')
            content = data.get('pitch', '')
            if q_lower in title.lower() or q_lower in desc.lower() or q_lower in content.lower():
                results['services'].append({
                    'title': title,
                    'type': 'Industry Services',
                    'slug': slug,
                    'url': f'/industries/{slug}',
                    'summary': desc
                })
                
        # Search partners from content registry
        for slug, data in PARTNERS_DATA.items():
            title = data.get('title', '')
            desc = data.get('desc', '')
            content = data.get('pitch', '')
            if q_lower in title.lower() or q_lower in desc.lower() or q_lower in content.lower():
                results['services'].append({
                    'title': title,
                    'type': 'Partner Solutions',
                    'slug': slug,
                    'url': f'/partners/{slug}',
                    'summary': desc
                })
                
    total_count = len(results['blogs']) + len(results['case_studies']) + len(results['services'])
    
    return render_template('search_results.html', q=q, results=results, total_count=total_count, active_page='none')

# 4. Wordpress-style Admin Dashboard Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'logged_in' in session:
        return redirect('/admin/dashboard')
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['username'] = username
            return redirect('/admin/dashboard')
        else:
            return render_template('admin_login.html', error='Invalid Username or Password.')
            
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect('/admin/login')

# 4.1. Admin Events & Webinars routes
@app.route('/admin/resources')
def admin_resources():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    webinars = conn.execute("SELECT * FROM webinars ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template('admin_resources.html', events=events, webinars=webinars)

@app.route('/admin/resource/new', methods=['GET', 'POST'])
def admin_resource_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        res_type = request.form.get('type')
        title = request.form.get('title')
        slug = request.form.get('slug')
        date_or_duration = request.form.get('date')
        loc_or_host = request.form.get('location')
        summary = request.form.get('summary')
        description = request.form.get('description')
        
        conn = get_db_connection()
        try:
            if res_type == 'Webinar':
                conn.execute('''
                INSERT INTO webinars (slug, title, host, duration, summary, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (slug, title, loc_or_host, date_or_duration, summary, description))
            else:
                conn.execute('''
                INSERT INTO events (slug, title, date, location, summary, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (slug, title, date_or_duration, loc_or_host, summary, description))
            conn.commit()
            conn.close()
            return redirect('/admin/resources')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_resource_editor.html', resource=None, type=res_type, error='Slug already exists. Please choose a unique slug.')
        except Exception as e:
            conn.close()
            return render_template('admin_resource_editor.html', resource=None, type=res_type, error=str(e))
            
    return render_template('admin_resource_editor.html', resource=None, type='Event')

@app.route('/admin/event/edit/<int:event_id>', methods=['GET', 'POST'])
def admin_event_edit(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    
    if not event:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        date_val = request.form.get('date')
        location_val = request.form.get('location')
        summary = request.form.get('summary')
        description = request.form.get('description')
        
        try:
            conn.execute('''
            UPDATE events 
            SET title = ?, slug = ?, date = ?, location = ?, summary = ?, description = ?
            WHERE id = ?
            ''', (title, slug, date_val, location_val, summary, description, event_id))
            conn.commit()
            conn.close()
            return redirect('/admin/resources')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_resource_editor.html', resource=event, type='Event', error='Slug already exists. Please choose a unique slug.')
        except Exception as e:
            conn.close()
            return render_template('admin_resource_editor.html', resource=event, type='Event', error=str(e))
            
    conn.close()
    return render_template('admin_resource_editor.html', resource=event, type='Event')

@app.route('/admin/event/delete/<int:event_id>')
def admin_event_delete(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/resources')

@app.route('/admin/webinar/edit/<int:webinar_id>', methods=['GET', 'POST'])
def admin_webinar_edit(webinar_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    webinar = conn.execute("SELECT * FROM webinars WHERE id = ?", (webinar_id,)).fetchone()
    
    if not webinar:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        duration_val = request.form.get('date')
        host_val = request.form.get('location')
        summary = request.form.get('summary')
        description = request.form.get('description')
        
        try:
            conn.execute('''
            UPDATE webinars 
            SET title = ?, slug = ?, duration = ?, host = ?, summary = ?, description = ?
            WHERE id = ?
            ''', (title, slug, duration_val, host_val, summary, description, webinar_id))
            conn.commit()
            conn.close()
            return redirect('/admin/resources')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_resource_editor.html', resource=webinar, type='Webinar', error='Slug already exists. Please choose a unique slug.')
        except Exception as e:
            conn.close()
            return render_template('admin_resource_editor.html', resource=webinar, type='Webinar', error=str(e))
            
    conn.close()
    return render_template('admin_resource_editor.html', resource=webinar, type='Webinar')

@app.route('/admin/webinar/delete/<int:webinar_id>')
def admin_webinar_delete(webinar_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM webinars WHERE id = ?", (webinar_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/resources')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    
    # Calculate stats widgets
    total_posts = len(posts)
    published = sum(1 for p in posts if p['status'] == 'Published')
    drafts = total_posts - published
    total_views = sum(p['views'] for p in posts)
    avg_seo = int(sum(p['seo_score'] for p in posts) / total_posts) if total_posts > 0 else 0
    
    conn.close()
    
    return render_template('admin_dashboard.html', posts=posts, total_posts=total_posts, published=published, drafts=drafts, total_views=total_views, avg_seo=avg_seo)

@app.route('/admin/post/new', methods=['GET', 'POST'])
def admin_post_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        date_str = request.form.get('date', 'May 30, 2026')
        category = request.form.get('category', 'Data Solutions')
        content = request.form.get('content')
        status = request.form.get('status', 'Draft')
        
        meta_title = request.form.get('meta_title', title)
        meta_desc = request.form.get('meta_desc', '')
        keywords = request.form.get('keywords', '')
        seo_score = int(request.form.get('seo_score', 0))
        
        # Simple auto summary
        summary = content[:150] + '...' if len(content) > 150 else content
        
        conn = get_db_connection()
        try:
            conn.execute('''
            INSERT INTO posts (title, slug, date, category, content, summary, status, meta_title, meta_desc, keywords, seo_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug, date_str, category, content, summary, status, meta_title, meta_desc, keywords, seo_score))
            conn.commit()
            conn.close()
            return redirect('/admin/dashboard')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_editor.html', post=None, error='Slug already exists. Please choose a unique slug.')
            
    return render_template('admin_editor.html', post=None)

@app.route('/admin/post/edit/<int:post_id>', methods=['GET', 'POST'])
def admin_post_edit(post_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    
    if not post:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        date_str = request.form.get('date', post['date'])
        category = request.form.get('category')
        content = request.form.get('content')
        status = request.form.get('status')
        
        meta_title = request.form.get('meta_title')
        meta_desc = request.form.get('meta_desc')
        keywords = request.form.get('keywords')
        seo_score = int(request.form.get('seo_score', 0))
        
        summary = content[:150] + '...' if len(content) > 150 else content
        
        try:
            conn.execute('''
            UPDATE posts 
            SET title = ?, slug = ?, date = ?, category = ?, content = ?, summary = ?, status = ?, meta_title = ?, meta_desc = ?, keywords = ?, seo_score = ?
            WHERE id = ?
            ''', (title, slug, date_str, category, content, summary, status, meta_title, meta_desc, keywords, seo_score, post_id))
            conn.commit()
            conn.close()
            return redirect('/admin/dashboard')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_editor.html', post=post, error='Slug already exists. Please choose a unique slug.')
            
    conn.close()
    return render_template('admin_editor.html', post=post)

@app.route('/admin/post/delete/<int:post_id>', methods=['POST', 'GET'])
def admin_post_delete(post_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/dashboard')

# 4.5. Case Studies Admin Dashboard & Control Panel
@app.route('/admin/case-studies')
def admin_case_studies_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    case_studies = conn.execute("SELECT * FROM case_studies ORDER BY id DESC").fetchall()
    
    # Calculate stats
    total = len(case_studies)
    published = sum(1 for c in case_studies if c['status'] == 'Published')
    needs_review = sum(1 for c in case_studies if c['status'] == 'Needs Review')
    
    # Calculate average confidence
    total_confidence = sum(c['extraction_confidence_score'] for c in case_studies)
    avg_confidence = int((total_confidence / total) * 100) if total > 0 else 0
    
    stats = {
        'total': total,
        'published': published,
        'needs_review': needs_review,
        'avg_confidence': avg_confidence
    }
    
    conn.close()
    return render_template('admin_case_studies.html', case_studies=case_studies, stats=stats)

@app.route('/admin/case-studies/scan', methods=['POST'])
def admin_case_studies_scan():
    if 'logged_in' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    try:
        result = pdf_extractor.scan_case_studies_folder(db_path='blog.db', folder_path='./CaseStudies')
        return jsonify({'status': 'success', 'processed': result['processed'], 'logs': result['logs']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/case-studies/new', methods=['GET', 'POST'])
def admin_case_study_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        # File upload option takes priority
        pdf_file = request.files.get('pdf_file')
        if pdf_file and pdf_file.filename:
            if not pdf_file.filename.lower().endswith('.pdf'):
                return render_template('admin_case_study_editor.html', post=None, error='Only PDF files are allowed.')
                
            os.makedirs('./CaseStudies', exist_ok=True)
            filename = secure_filename(pdf_file.filename)
            save_path = os.path.join('./CaseStudies', filename)
            pdf_file.save(save_path)
            
            try:
                file_hash = pdf_extractor.calculate_file_hash(save_path)
                
                conn = get_db_connection()
                existing = conn.execute("SELECT id FROM case_studies WHERE pdf_file_hash = ?", (file_hash,)).fetchone()
                if existing:
                    conn.close()
                    return render_template('admin_case_study_editor.html', post=None, error=f'PDF file "{filename}" has already been processed.')
                
                extracted = pdf_extractor.parse_pdf(save_path)
                cursor = conn.cursor()
                unique_slug = pdf_extractor.make_unique_slug(cursor, extracted['slug'])
                extracted['slug'] = unique_slug
                extracted['canonical_url'] = f"/case-studies/{unique_slug}"
                
                try:
                    schema = json.loads(extracted['schema_json'])
                    schema['url'] = f"https://www.thinkartha.com/case-studies/{unique_slug}"
                    extracted['schema_json'] = json.dumps(schema)
                except:
                    pass
                    
                now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                INSERT INTO case_studies (
                    title, slug, status, featured, client_name, client_display_name, is_client_anonymized,
                    industry, region, solution_area, technologies, business_challenge, solution_summary,
                    implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                    ai_summary, card_summary, detail_content, faq_json, tags, seo_title, seo_description,
                    seo_keywords, canonical_url, og_title, og_description, schema_json, pdf_file_path,
                    pdf_file_hash, extraction_confidence_score, seo_score, genai_seo_score, created_at, updated_at
                ) VALUES (?, ?, 'Needs Review', 0, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    extracted['title'], extracted['slug'], extracted['client_name'], extracted['client_display_name'],
                    extracted['industry'], extracted['region'], extracted['solution_area'], extracted['technologies'],
                    extracted['business_challenge'], extracted['solution_summary'], extracted['implementation_approach'],
                    extracted['business_outcomes'], extracted['key_metrics'], extracted['quote'], extracted['executive_summary'],
                    extracted['ai_summary'], extracted['card_summary'], extracted['detail_content'], extracted['faq_json'],
                    extracted['tags'], extracted['seo_title'], extracted['seo_description'], extracted['seo_keywords'],
                    extracted['canonical_url'], extracted['og_title'], extracted['og_description'], extracted['schema_json'],
                    save_path, file_hash, extracted['extraction_confidence_score'], extracted['seo_score'], extracted['genai_seo_score'],
                    now_str, now_str
                ))
                
                new_id = cursor.lastrowid
                
                cursor.execute('''
                INSERT INTO case_study_import_logs (
                    pdf_file_name, pdf_file_path, pdf_file_hash, status, extraction_summary, created_case_study_id, processed_at
                ) VALUES (?, ?, ?, 'Success', ?, ?, ?)
                ''', (filename, save_path, file_hash, f"Manually uploaded and extracted {extracted['title']}", new_id, now_str))
                
                conn.commit()
                conn.close()
                
                return redirect(f'/admin/case-studies/edit/{new_id}')
            except Exception as e:
                return render_template('admin_case_study_editor.html', post=None, error=f'Failed to process uploaded PDF: {str(e)}')
        else:
            title = request.form.get('title')
            slug = request.form.get('slug')
            status = request.form.get('status', 'Draft')
            featured = 1 if request.form.get('featured') else 0
            client_name = request.form.get('client_name', '')
            client_display_name = request.form.get('client_display_name', '')
            is_client_anonymized = 1 if request.form.get('is_client_anonymized') else 0
            industry = request.form.get('industry', '')
            region = request.form.get('region', '')
            solution_area = request.form.get('solution_area', '')
            technologies = request.form.get('technologies', '')
            business_challenge = request.form.get('business_challenge', '')
            solution_summary = request.form.get('solution_summary', '')
            implementation_approach = request.form.get('implementation_approach', '')
            business_outcomes = request.form.get('business_outcomes', '')
            key_metrics = request.form.get('key_metrics', '[]')
            quote = request.form.get('quote', '')
            executive_summary = request.form.get('executive_summary', '')
            ai_summary = request.form.get('ai_summary', '')
            card_summary = request.form.get('card_summary', '')
            detail_content = request.form.get('detail_content', '')
            faq_json = request.form.get('faq_json', '[]')
            tags = request.form.get('tags', '')
            seo_title = request.form.get('seo_title', '')
            seo_description = request.form.get('seo_description', '')
            seo_keywords = request.form.get('seo_keywords', '')
            og_title = request.form.get('og_title', '')
            og_description = request.form.get('og_description', '')
            schema_json = request.form.get('schema_json', '{}')
            
            thumbnail_path = request.form.get('thumbnail_path')
            cover_image_file = request.files.get('cover_image_file')
            if cover_image_file and cover_image_file.filename:
                os.makedirs('static/img/case-studies/uploads', exist_ok=True)
                _, ext = os.path.splitext(cover_image_file.filename)
                ext = ext.lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                    filename = f"{slug or title.lower().replace(' ', '-')}-cover{ext}"
                    save_path = os.path.join('static/img/case-studies/uploads', filename)
                    cover_image_file.save(save_path)
                    thumbnail_path = f"/static/img/case-studies/uploads/{filename}"
            
            now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            conn = get_db_connection()
            cursor = conn.cursor()
            unique_slug = pdf_extractor.make_unique_slug(cursor, slug or title.lower().replace(' ', '-'))
            canonical_url = f"/case-studies/{unique_slug}"
            
            try:
                cursor.execute('''
                INSERT INTO case_studies (
                    title, slug, status, featured, client_name, client_display_name, is_client_anonymized,
                    industry, region, solution_area, technologies, business_challenge, solution_summary,
                    implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                    ai_summary, card_summary, detail_content, faq_json, tags, seo_title, seo_description,
                    seo_keywords, canonical_url, og_title, og_description, schema_json, created_at, updated_at,
                    thumbnail_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    title, unique_slug, status, featured, client_name, client_display_name, is_client_anonymized,
                    industry, region, solution_area, technologies, business_challenge, solution_summary,
                    implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                    ai_summary, card_summary or executive_summary[:180] + '...', detail_content, faq_json, tags,
                    seo_title, seo_description, seo_keywords, canonical_url, og_title, og_description, schema_json,
                    now_str, now_str, thumbnail_path
                ))
                new_id = cursor.lastrowid
                conn.commit()
                conn.close()
                return redirect('/admin/case-studies')
            except Exception as e:
                conn.close()
                return render_template('admin_case_study_editor.html', post=None, error=f'Database insert failed: {str(e)}')
                
    return render_template('admin_case_study_editor.html', post=None)

@app.route('/admin/case-studies/edit/<int:study_id>', methods=['GET', 'POST'])
def admin_case_study_edit(study_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    post = conn.execute("SELECT * FROM case_studies WHERE id = ?", (study_id,)).fetchone()
    
    if not post:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        status = request.form.get('status')
        featured = 1 if request.form.get('featured') else 0
        client_name = request.form.get('client_name')
        client_display_name = request.form.get('client_display_name')
        is_client_anonymized = 1 if request.form.get('is_client_anonymized') else 0
        industry = request.form.get('industry')
        region = request.form.get('region')
        solution_area = request.form.get('solution_area')
        technologies = request.form.get('technologies')
        business_challenge = request.form.get('business_challenge')
        solution_summary = request.form.get('solution_summary')
        implementation_approach = request.form.get('implementation_approach')
        business_outcomes = request.form.get('business_outcomes')
        key_metrics = request.form.get('key_metrics')
        quote = request.form.get('quote')
        executive_summary = request.form.get('executive_summary')
        ai_summary = request.form.get('ai_summary')
        card_summary = request.form.get('card_summary')
        detail_content = request.form.get('detail_content')
        faq_json = request.form.get('faq_json')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        schema_json = request.form.get('schema_json')
        
        thumbnail_path = request.form.get('thumbnail_path')
        cover_image_file = request.files.get('cover_image_file')
        if cover_image_file and cover_image_file.filename:
            os.makedirs('static/img/case-studies/uploads', exist_ok=True)
            _, ext = os.path.splitext(cover_image_file.filename)
            ext = ext.lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                filename = f"{slug}-cover{ext}"
                save_path = os.path.join('static/img/case-studies/uploads', filename)
                cover_image_file.save(save_path)
                thumbnail_path = f"/static/img/case-studies/uploads/{filename}"
                
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        published_at = post['published_at']
        if status == 'Published' and not published_at:
            published_at = now_str
        elif status != 'Published':
            published_at = None
            
        previous_data = dict(post)
        new_data = {
            'title': title, 'slug': slug, 'status': status, 'featured': featured,
            'client_name': client_name, 'client_display_name': client_display_name,
            'is_client_anonymized': is_client_anonymized, 'industry': industry,
            'region': region, 'solution_area': solution_area, 'technologies': technologies,
            'business_challenge': business_challenge, 'solution_summary': solution_summary,
            'implementation_approach': implementation_approach, 'business_outcomes': business_outcomes,
            'key_metrics': key_metrics, 'quote': quote, 'executive_summary': executive_summary,
            'ai_summary': ai_summary, 'card_summary': card_summary, 'detail_content': detail_content,
            'faq_json': faq_json, 'tags': tags, 'seo_title': seo_title, 'seo_description': seo_description,
            'seo_keywords': seo_keywords, 'og_title': og_title, 'og_description': og_description,
            'schema_json': schema_json, 'thumbnail_path': thumbnail_path
        }
        
        changes = []
        for k, v in new_data.items():
            prev_v = previous_data.get(k)
            if str(prev_v) != str(v):
                changes.append(k)
                
        if changes:
            change_summary = f"Updated: {', '.join(changes)}"
            try:
                conn.execute('''
                INSERT INTO case_study_version_history (case_study_id, changed_by, previous_data, new_data, change_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (study_id, session.get('username', 'admin'), json.dumps(previous_data), json.dumps(new_data), change_summary, now_str))
            except Exception as ex:
                print(f"Error logging version history: {ex}")
                
        try:
            conn.execute('''
            UPDATE case_studies SET
                title = ?, slug = ?, status = ?, featured = ?, client_name = ?, client_display_name = ?, is_client_anonymized = ?,
                industry = ?, region = ?, solution_area = ?, technologies = ?, business_challenge = ?, solution_summary = ?,
                implementation_approach = ?, business_outcomes = ?, key_metrics = ?, quote = ?, executive_summary = ?,
                ai_summary = ?, card_summary = ?, detail_content = ?, faq_json = ?, tags = ?, seo_title = ?, seo_description = ?,
                seo_keywords = ?, og_title = ?, og_description = ?, schema_json = ?, updated_at = ?, published_at = ?,
                thumbnail_path = ?
            WHERE id = ?
            ''', (
                title, slug, status, featured, client_name, client_display_name, is_client_anonymized,
                industry, region, solution_area, technologies, business_challenge, solution_summary,
                implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                ai_summary, card_summary, detail_content, faq_json, tags, seo_title, seo_description,
                seo_keywords, og_title, og_description, schema_json, now_str, published_at,
                thumbnail_path, study_id
            ))
            conn.commit()
            conn.close()
            return redirect('/admin/case-studies')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('admin_case_study_editor.html', post=post, study_tags=post['tags'], error='Slug already exists. Please choose a unique slug.')
        except Exception as e:
            conn.close()
            return render_template('admin_case_study_editor.html', post=post, study_tags=post['tags'], error=f'Save failed: {str(e)}')
            
    conn.close()
    return render_template('admin_case_study_editor.html', post=post, study_tags=post['tags'])

@app.route('/admin/case-studies/delete/<int:study_id>')
def admin_case_study_delete(study_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM case_studies WHERE id = ?", (study_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/case-studies')

@app.route('/admin/case-studies/reprocess/<int:study_id>')
def admin_case_study_reprocess(study_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    post = conn.execute("SELECT pdf_file_path FROM case_studies WHERE id = ?", (study_id,)).fetchone()
    
    if not post or not post['pdf_file_path'] or not os.path.exists(post['pdf_file_path']):
        conn.close()
        abort(404)
        
    try:
        extracted = pdf_extractor.parse_pdf(post['pdf_file_path'])
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
        UPDATE case_studies SET
            title = ?, client_name = ?, client_display_name = ?,
            industry = ?, region = ?, solution_area = ?, technologies = ?, business_challenge = ?, solution_summary = ?,
            implementation_approach = ?, business_outcomes = ?, key_metrics = ?, quote = ?, executive_summary = ?,
            ai_summary = ?, card_summary = ?, detail_content = ?, faq_json = ?, tags = ?, seo_title = ?, seo_description = ?,
            seo_keywords = ?, og_title = ?, og_description = ?, schema_json = ?, extraction_confidence_score = ?,
            seo_score = ?, genai_seo_score = ?, updated_at = ?
        WHERE id = ?
        ''', (
            extracted['title'], extracted['client_name'], extracted['client_display_name'],
            extracted['industry'], extracted['region'], extracted['solution_area'], extracted['technologies'],
            extracted['business_challenge'], extracted['solution_summary'], extracted['implementation_approach'],
            extracted['business_outcomes'], extracted['key_metrics'], extracted['quote'], extracted['executive_summary'],
            extracted['ai_summary'], extracted['card_summary'], extracted['detail_content'], extracted['faq_json'],
            extracted['tags'], extracted['seo_title'], extracted['seo_description'], extracted['seo_keywords'],
            extracted['og_title'], extracted['og_description'], extracted['schema_json'],
            extracted['extraction_confidence_score'], extracted['seo_score'], extracted['genai_seo_score'],
            now_str, study_id
        ))
        conn.commit()
        conn.close()
        return redirect(f'/admin/case-studies/edit/{study_id}')
    except Exception as e:
        conn.close()
        print(f"Reprocess error: {e}")
        return redirect(f'/admin/case-studies/edit/{study_id}')

@app.route('/admin/case-studies/leads')
def admin_case_study_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute('''
        SELECT l.*, c.title as study_title 
        FROM case_study_leads l
        LEFT JOIN case_studies c ON l.case_study_id = c.id
        ORDER BY l.id DESC
    ''').fetchall()
    conn.close()
    return render_template('admin_case_study_leads.html', leads=leads)

@app.route('/admin/case-studies/export-leads')
def admin_case_study_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute('''
        SELECT l.id, c.title as study_title, l.business_email, l.first_name, l.last_name, 
               l.company, l.job_title, l.phone, l.country, l.consent, l.source_url, 
               l.referrer, l.utm_source, l.utm_medium, l.utm_campaign, l.utm_term, 
               l.utm_content, l.ip_address, l.user_agent, l.downloaded_at
        FROM case_study_leads l
        LEFT JOIN case_studies c ON l.case_study_id = c.id
        ORDER BY l.id DESC
    ''').fetchall()
    conn.close()
    
    dest = io.StringIO()
    writer = csv.writer(dest)
    writer.writerow([
        'Lead ID', 'Downloaded Case Study', 'Business Email', 'First Name', 'Last Name',
        'Company', 'Job Title', 'Phone', 'Country', 'Consent Status', 'Source URL',
        'Referrer', 'UTM Source', 'UTM Medium', 'UTM Campaign', 'UTM Term',
        'UTM Content', 'IP Address', 'User Agent', 'Timestamp'
    ])
    
    for l in leads:
        writer.writerow([
            l['id'], l['study_title'] or f"ID: {l['case_study_id']}", l['business_email'], l['first_name'], l['last_name'],
            l['company'], l['job_title'], l['phone'], l['country'], 'Consented' if l['consent'] == 1 else 'No', l['source_url'],
            l['referrer'], l['utm_source'], l['utm_medium'], l['utm_campaign'], l['utm_term'],
            l['utm_content'], l['ip_address'], l['user_agent'], l['downloaded_at']
        ])
        
    output = make_response(dest.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=gated_pdf_leads_export.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/contact-us', methods=['GET', 'POST'])
def contact_us():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        return jsonify({
            'status': 'success',
            'message': f'Thank you, {name}! Your message regarding "{subject}" has been successfully sent. We will get back to you shortly.'
        })
    return render_template('contact_us.html', active_page='contact_us')

# ==========================================================================
# Healthcare Microsite Frontend Routes & Helpers
# ==========================================================================

def render_healthcare_page(page_key):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = ? AND status = 'Published'", (page_key,)).fetchone()
    conn.close()
    if not page:
        abort(404)
        
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    related_services = json.loads(page['related_services_json'] or '[]')
    
    template_name = 'healthcare_page.html'
    if page_key == 'overview':
        template_name = 'healthcare_overview.html'
    
    return render_template(
        template_name,
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        related_services=related_services,
        active_subpage=page_key,
        active_page='industries'
    )

@app.route('/industries/healthcare')
def healthcare_overview():
    return render_healthcare_page('overview')

@app.route('/industries/healthcare/providers')
def healthcare_providers():
    return render_healthcare_page('providers')

@app.route('/industries/healthcare/payers')
def healthcare_payers():
    return render_healthcare_page('payers')

@app.route('/industries/healthcare/data-governance')
def healthcare_governance():
    return render_healthcare_page('data-governance')

@app.route('/industries/healthcare/interoperability')
def healthcare_interoperability():
    return render_healthcare_page('interoperability')

@app.route('/industries/healthcare/analytics-ai')
def healthcare_analytics_ai():
    return render_healthcare_page('analytics-ai')

@app.route('/industries/healthcare/mdm')
def healthcare_mdm():
    return render_healthcare_page('mdm')

@app.route('/industries/healthcare/use-cases')
def healthcare_use_cases():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'use-cases' AND status = 'Published'").fetchone()
    use_cases = conn.execute("SELECT * FROM healthcare_use_cases WHERE status = 'Published'").fetchall()
    
    # Extract tags for filters
    all_tags = set()
    for uc in use_cases:
        if uc['tags']:
            for tag in uc['tags'].split(','):
                all_tags.add(tag.strip())
                
    conn.close()
    if not page:
        abort(404)
        
    return render_template(
        'healthcare_use_cases.html',
        page=page,
        use_cases=use_cases,
        tags=sorted(list(all_tags)),
        active_subpage='use-cases',
        active_page='industries'
    )

@app.route('/industries/healthcare/case-studies')
def healthcare_case_studies():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'case-studies' AND status = 'Published'").fetchone()
    
    # Query case_studies from DB matching Healthcare
    studies = conn.execute("SELECT * FROM case_studies WHERE status = 'Published' AND (industry LIKE '%Healthcare%' OR tags LIKE '%Healthcare%')").fetchall()
    conn.close()
    
    if not page:
        abort(404)
        
    return render_template(
        'healthcare_case_studies.html',
        page=page,
        case_studies=studies,
        active_subpage='case-studies',
        active_page='industries'
    )

@app.route('/industries/healthcare/submit-lead', methods=['POST'])
def healthcare_submit_lead():
    # Honeypot spam check
    if request.form.get('website_url_honeypot'):
        return jsonify({'status': 'success', 'message': 'Lead received (spam filter active)'})
        
    # Rate limiting
    now = time.time()
    ip = request.remote_addr or '127.0.0.1'
    ips_timestamps = DOWNLOAD_RATE_LIMIT.get(ip, [])
    ips_timestamps = [t for t in ips_timestamps if now - t < 60]
    if len(ips_timestamps) >= 5:
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded. Maximum 5 actions per minute allowed.'}), 429
    ips_timestamps.append(now)
    DOWNLOAD_RATE_LIMIT[ip] = ips_timestamps
    
    email = request.form.get('business_email')
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    phone = request.form.get('phone', '')
    country = request.form.get('country', '')
    message = request.form.get('message', '')
    consent = 1 if request.form.get('consent') else 0
    source_page = request.form.get('source_page', 'overview')
    cta_clicked = request.form.get('cta_clicked', 'Talk to a Healthcare Data Expert')
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    PERSONAL_DOMAINS = {
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    }
    
    email_parts = email.split('@')
    if len(email_parts) != 2:
        return jsonify({'status': 'error', 'message': 'Invalid email format.'}), 400
        
    domain = email_parts[1].lower().strip()
    if domain in PERSONAL_DOMAINS:
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    utm_source = request.form.get('utm_source', '')
    utm_medium = request.form.get('utm_medium', '')
    utm_campaign = request.form.get('utm_campaign', '')
    referrer = request.form.get('referrer', '')
    user_agent = request.headers.get('User-Agent', '')
    
    conn = get_db_connection()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO healthcare_leads (
            source_page, cta_clicked, first_name, last_name, business_email,
            company, job_title, phone, country, message, consent,
            utm_source, utm_medium, utm_campaign, referrer, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        source_page, cta_clicked, first_name, last_name, email,
        company, job_title, phone, country, message, consent,
        utm_source, utm_medium, utm_campaign, referrer, ip, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Thank you! Your request has been received. A healthcare data advisor will reach out shortly.'})

# ==========================================================================
# Healthcare Microsite Administrative Routes
# ==========================================================================

@app.route('/admin/industries/healthcare')
def admin_healthcare_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    
    conn = get_db_connection()
    total_leads = conn.execute("SELECT COUNT(*) FROM healthcare_leads").fetchone()[0]
    total_use_cases = conn.execute("SELECT COUNT(*) FROM healthcare_use_cases").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM industry_microsite_pages WHERE industry = 'healthcare'").fetchone()[0]
    recent_leads = conn.execute("SELECT * FROM healthcare_leads ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    return render_template(
        'admin_healthcare_dashboard.html',
        total_leads=total_leads,
        total_use_cases=total_use_cases,
        total_pages=total_pages,
        recent_leads=recent_leads,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/pages')
def admin_healthcare_pages():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE industry = 'healthcare' ORDER BY id ASC").fetchall()
    conn.close()
    return render_template(
        'admin_healthcare_pages.html',
        pages=pages,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/pages/<int:page_id>', methods=['GET', 'POST', 'PUT'])
def admin_healthcare_page_edit(page_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE id = ?", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        hero_title = request.form.get('hero_title')
        hero_subtitle = request.form.get('hero_subtitle')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        canonical_url = request.form.get('canonical_url')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        og_image = request.form.get('og_image')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        noindex = 1 if request.form.get('noindex') else 0
        
        # faq_json edit
        faqs = []
        faq_qs = request.form.getlist('faq_q[]')
        faq_as = request.form.getlist('faq_a[]')
        for q, a in zip(faq_qs, faq_as):
            if q.strip() and a.strip():
                faqs.append({'q': q.strip(), 'a': a.strip()})
        faq_json = json.dumps(faqs)
        
        # cta edit
        cta_text = request.form.get('primary_cta_text')
        cta_url = request.form.get('primary_cta_url')
        cta_json = json.dumps({
            'primary_cta_text': cta_text,
            'primary_cta_url': cta_url,
            'secondary_cta_text': request.form.get('secondary_cta_text', ''),
            'secondary_cta_url': request.form.get('secondary_cta_url', '')
        })
        
        # Parse and save body sections based on page key
        body_sections = json.loads(page['body_sections_json'] or '{}')
        
        if page['page_key'] == 'overview':
            bullets = request.form.getlist('hero_bullets[]')
            body_sections['hero_bullets'] = [b.strip() for b in bullets if b.strip()]
            
            challenge_title = request.form.get('challenge_title')
            challenge_desc = request.form.get('challenge_desc')
            body_sections['challenge_title'] = challenge_title
            body_sections['challenge_desc'] = challenge_desc
            
            c_titles = request.form.getlist('challenge_card_title[]')
            c_descs = request.form.getlist('challenge_card_desc[]')
            cards = []
            for ct, cd in zip(c_titles, c_descs):
                if ct.strip():
                    cards.append({'title': ct.strip(), 'desc': cd.strip()})
            body_sections['challenge_cards'] = cards
        
        elif page['page_key'] == 'providers':
            challenges = request.form.getlist('provider_challenges[]')
            body_sections['challenges'] = [c.strip() for c in challenges if c.strip()]
            
            s_titles = request.form.getlist('provider_sol_title[]')
            s_descs = request.form.getlist('provider_sol_desc[]')
            sols = []
            for st, sd in zip(s_titles, s_descs):
                if st.strip():
                    sols.append({'title': st.strip(), 'desc': sd.strip()})
            body_sections['solutions'] = sols
            
        elif page['page_key'] == 'payers':
            challenges = request.form.getlist('payer_challenges[]')
            body_sections['challenges'] = [c.strip() for c in challenges if c.strip()]
            
            s_titles = request.form.getlist('payer_sol_title[]')
            s_descs = request.form.getlist('payer_sol_desc[]')
            sols = []
            for st, sd in zip(s_titles, s_descs):
                if st.strip():
                    sols.append({'title': st.strip(), 'desc': sd.strip()})
            body_sections['solutions'] = sols
            
        elif page['page_key'] == 'data-governance':
            val_prop = request.form.get('value_proposition')
            val_desc = request.form.get('value_proposition_desc')
            body_sections['value_proposition'] = val_prop
            body_sections['value_desc'] = val_desc
            
            cap_titles = request.form.getlist('gov_cap_title[]')
            cap_descs = request.form.getlist('gov_cap_desc[]')
            caps = []
            for ct, cd in zip(cap_titles, cap_descs):
                if ct.strip():
                    caps.append({'title': ct.strip(), 'desc': cd.strip()})
            body_sections['capabilities'] = caps
            
        elif page['page_key'] == 'interoperability':
            cap_titles = request.form.getlist('int_cap_title[]')
            cap_descs = request.form.getlist('int_cap_desc[]')
            caps = []
            for ct, cd in zip(cap_titles, cap_descs):
                if ct.strip():
                    caps.append({'title': ct.strip(), 'desc': cd.strip()})
            body_sections['capabilities'] = caps
            
        elif page['page_key'] == 'analytics-ai':
            cap_titles = request.form.getlist('an_cap_title[]')
            cap_descs = request.form.getlist('an_cap_desc[]')
            caps = []
            for ct, cd in zip(cap_titles, cap_descs):
                if ct.strip():
                    caps.append({'title': ct.strip(), 'desc': cd.strip()})
            body_sections['analytics_capabilities'] = caps
            
            read_titles = request.form.getlist('ai_read_title[]')
            read_descs = request.form.getlist('ai_read_desc[]')
            reads = []
            for rt, rd in zip(read_titles, read_descs):
                if rt.strip():
                    reads.append({'title': rt.strip(), 'desc': rd.strip()})
            body_sections['ai_readiness_items'] = reads
            
        elif page['page_key'] == 'mdm':
            dom_titles = request.form.getlist('mdm_dom_title[]')
            dom_descs = request.form.getlist('mdm_dom_desc[]')
            doms = []
            for dt, dd in zip(dom_titles, dom_descs):
                if dt.strip():
                    doms.append({'title': dt.strip(), 'desc': dd.strip()})
            body_sections['domains'] = doms
            
            cap_titles = request.form.getlist('mdm_cap_title[]')
            cap_descs = request.form.getlist('mdm_cap_desc[]')
            caps = []
            for ct, cd in zip(cap_titles, cap_descs):
                if ct.strip():
                    caps.append({'title': ct.strip(), 'desc': cd.strip()})
            body_sections['capabilities'] = caps
            
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        body_sections_json = json.dumps(body_sections)
        
        conn.execute('''
            UPDATE industry_microsite_pages
            SET title = ?, hero_title = ?, hero_subtitle = ?, body_sections_json = ?, cta_json = ?, faq_json = ?,
                seo_title = ?, seo_description = ?, seo_keywords = ?, canonical_url = ?, og_title = ?,
                og_description = ?, og_image = ?, ai_summary = ?, status = ?, noindex = ?, updated_at = ?
            WHERE id = ?
        ''', (
            title, hero_title, hero_subtitle, body_sections_json, cta_json, faq_json,
            seo_title, seo_description, seo_keywords, canonical_url, og_title,
            og_description, og_image, ai_summary, status, noindex, now_str, page_id
        ))
        conn.commit()
        conn.close()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'PUT':
            return jsonify({'status': 'success', 'message': 'Page updated successfully.'})
            
        return redirect('/admin/industries/healthcare/pages')
        
    conn.close()
    
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    
    return render_template(
        'admin_healthcare_page_edit.html',
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/use-cases')
def admin_healthcare_use_cases():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    
    conn = get_db_connection()
    use_cases = conn.execute("SELECT * FROM healthcare_use_cases ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_healthcare_use_cases.html',
        use_cases=use_cases,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/use-cases/new', methods=['GET', 'POST'])
def admin_healthcare_use_case_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        if not slug:
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services', '')
        tags = request.form.get('tags', '')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO healthcare_use_cases (
                    title, slug, audience_type, problem, data_domains, artha_solution,
                    technologies, business_outcomes, related_services, tags,
                    seo_title, seo_description, ai_summary, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                title, slug, audience_type, problem, data_domains, artha_solution,
                technologies, business_outcomes, related_services, tags,
                seo_title or f"{title} | Healthcare Data Use Cases",
                seo_description or f"Healthcare use case detail for {title}.",
                ai_summary or f"Use case for {title} solving {problem} with {technologies}.",
                status, now_str, now_str
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Slug already exists. Please choose a unique slug.", 400
        conn.close()
        
        return redirect('/admin/industries/healthcare/use-cases')
        
    return render_template(
        'admin_healthcare_use_case_edit.html',
        use_case=None,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/use-cases/<int:uc_id>', methods=['GET', 'POST', 'PUT'])
def admin_healthcare_use_case_edit(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_case = conn.execute("SELECT * FROM healthcare_use_cases WHERE id = ?", (uc_id,)).fetchone()
    
    if not use_case:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        slug = request.form.get('slug')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services', '')
        tags = request.form.get('tags', '')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            conn.execute('''
                UPDATE healthcare_use_cases
                SET title = ?, slug = ?, audience_type = ?, problem = ?, data_domains = ?, artha_solution = ?,
                    technologies = ?, business_outcomes = ?, related_services = ?, tags = ?,
                    seo_title = ?, seo_description = ?, ai_summary = ?, status = ?, updated_at = ?
                WHERE id = ?
            ''', (
                title, slug, audience_type, problem, data_domains, artha_solution,
                technologies, business_outcomes, related_services, tags,
                seo_title, seo_description, ai_summary, status, now_str, uc_id
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Slug already exists. Please choose a unique slug.", 400
            
        conn.close()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'PUT':
            return jsonify({'status': 'success', 'message': 'Use case updated successfully.'})
            
        return redirect('/admin/industries/healthcare/use-cases')
        
    conn.close()
    return render_template(
        'admin_healthcare_use_case_edit.html',
        use_case=use_case,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/use-cases/<int:uc_id>/delete', methods=['POST', 'DELETE'])
def admin_healthcare_use_case_delete(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM healthcare_use_cases WHERE id = ?", (uc_id,))
    conn.commit()
    conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
        return jsonify({'status': 'success', 'message': 'Use case deleted.'})
        
    return redirect('/admin/industries/healthcare/use-cases')

@app.route('/admin/industries/healthcare/leads')
def admin_healthcare_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM healthcare_leads ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_healthcare_leads.html',
        leads=leads,
        active_page='healthcare_admin'
    )

@app.route('/admin/industries/healthcare/export-leads')
def admin_healthcare_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM healthcare_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Source Page', 'CTA Clicked', 'First Name', 'Last Name',
        'Business Email', 'Company', 'Job Title', 'Phone', 'Country',
        'Message', 'Consent', 'UTM Source', 'UTM Medium', 'UTM Campaign',
        'Referrer', 'IP Address', 'User Agent', 'Created At'
    ])
    
    for row in leads:
        writer.writerow([
            row['id'], row['source_page'], row['cta_clicked'], row['first_name'], row['last_name'],
            row['business_email'], row['company'], row['job_title'], row['phone'], row['country'],
            row['message'], row['consent'], row['utm_source'], row['utm_medium'], row['utm_campaign'],
            row['referrer'], row['ip_address'], row['user_agent'], row['created_at']
        ])
        
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=healthcare_leads.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

# ==========================================================================
# Artificial Intelligence Microsite Frontend Routes & Helpers
# ==========================================================================

def render_ai_page(page_key):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = ? AND status = 'Published'", (page_key,)).fetchone()
    conn.close()
    if not page:
        abort(404)
        
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    related_services = json.loads(page['related_services_json'] or '[]')
    
    template_name = 'ai_page.html'
    if page_key == 'ai-overview':
        template_name = 'artificial_intelligence.html'
    elif page_key == 'ai-roi-solutions':
        template_name = 'ai_roi_solutions.html'
    elif page_key == 'ai-campaign-future-ready':
        template_name = 'campaign_future_ready.html'
    elif page_key == 'ai-campaign-data-assessment':
        template_name = 'campaign_data_assessment.html'
        
    return render_template(
        template_name,
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        related_services=related_services,
        active_subpage=page_key.replace('ai-', ''),
        active_page='solutions'
    )

@app.route('/events/future-ready-data-foundation-from-ai-pilot-to-production-value')
def ai_campaign_future_ready():
    return render_ai_page('ai-campaign-future-ready')

@app.route('/intelligent-data-assessment-platform')
def ai_campaign_data_assessment():
    return render_ai_page('ai-campaign-data-assessment')

@app.route('/artificial-intelligence/submit-lead', methods=['POST'])
def ai_submit_lead():
    # Honeypot spam protection
    honeypot = request.form.get('website_url_honeypot', '')
    if honeypot:
        return jsonify({'status': 'error', 'message': 'Spam detected.'}), 400
        
    source_page = request.form.get('source_page', 'AI Microsite')
    cta_clicked = request.form.get('cta_clicked', 'General Contact')
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('business_email', '').strip().lower()
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    phone = request.form.get('phone', '')
    country = request.form.get('country', '')
    message = request.form.get('message', '')
    consent = 1 if request.form.get('consent') else 0
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    # Personal domain validation
    personal_domains = [
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    ]
    if '@' not in email:
        return jsonify({'status': 'error', 'message': 'Invalid email address.'}), 400
        
    domain = email.split('@')[1]
    if domain in personal_domains:
        return jsonify({'status': 'error', 'message': 'Please use your corporate business email address.'}), 400
        
    # UTM parameter extraction
    utm_source = request.form.get('utm_source', '')
    utm_medium = request.form.get('utm_medium', '')
    utm_campaign = request.form.get('utm_campaign', '')
    referrer = request.form.get('referrer', '')
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    
    conn = get_db_connection()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO ai_leads (
            source_page, cta_clicked, first_name, last_name, business_email,
            company, job_title, phone, country, message, consent,
            utm_source, utm_medium, utm_campaign, referrer, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        source_page, cta_clicked, first_name, last_name, email,
        company, job_title, phone, country, message, consent,
        utm_source, utm_medium, utm_campaign, referrer, ip, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Thank you! Your request has been received. An AI solutions advisor will reach out shortly.'})

# ==========================================================================
# Artificial Intelligence Microsite Administrative Routes
# ==========================================================================

@app.route('/admin/artificial-intelligence')
def admin_ai_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    total_leads = conn.execute("SELECT COUNT(*) FROM ai_leads").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM industry_microsite_pages WHERE industry = 'artificial-intelligence'").fetchone()[0]
    recent_leads = conn.execute("SELECT * FROM ai_leads ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    return render_template(
        'admin_ai_dashboard.html',
        total_leads=total_leads,
        total_pages=total_pages,
        recent_leads=recent_leads
    )

@app.route('/admin/artificial-intelligence/pages')
def admin_ai_pages():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE industry = 'artificial-intelligence' ORDER BY id ASC").fetchall()
    conn.close()
    
    return render_template(
        'admin_ai_pages.html',
        pages=pages
    )

@app.route('/admin/artificial-intelligence/pages/<int:page_id>', methods=['GET', 'POST', 'PUT'])
def admin_ai_page_edit(page_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE id = ? AND industry = 'artificial-intelligence'", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        hero_title = request.form.get('hero_title')
        hero_subtitle = request.form.get('hero_subtitle')
        body_sections_json = request.form.get('body_sections_json')
        cta_json = request.form.get('cta_json')
        faq_json = request.form.get('faq_json')
        related_services_json = request.form.get('related_services_json')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        canonical_url = request.form.get('canonical_url')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        og_image = request.form.get('og_image')
        schema_json = request.form.get('schema_json')
        ai_summary = request.form.get('ai_summary')
        genai_entities_json = request.form.get('genai_entities_json')
        status = request.form.get('status', 'Published')
        noindex = 1 if request.form.get('noindex') else 0
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute("""
            UPDATE industry_microsite_pages
            SET title = ?, hero_title = ?, hero_subtitle = ?, body_sections_json = ?,
                cta_json = ?, faq_json = ?, related_services_json = ?, seo_title = ?,
                seo_description = ?, seo_keywords = ?, canonical_url = ?, og_title = ?,
                og_description = ?, og_image = ?, schema_json = ?, ai_summary = ?,
                genai_entities_json = ?, status = ?, noindex = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, hero_title, hero_subtitle, body_sections_json,
            cta_json, faq_json, related_services_json, seo_title,
            seo_description, seo_keywords, canonical_url, og_title,
            og_description, og_image, schema_json, ai_summary,
            genai_entities_json, status, noindex, now_str, page_id
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/artificial-intelligence/pages')
        
    conn.close()
    return render_template(
        'admin_ai_page_edit.html',
        page=page
    )

@app.route('/admin/artificial-intelligence/leads')
def admin_ai_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM ai_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    return render_template(
        'admin_ai_leads.html',
        leads=leads
    )

@app.route('/admin/artificial-intelligence/export-leads')
def admin_ai_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM ai_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Source Page', 'CTA Clicked', 'First Name', 'Last Name',
        'Business Email', 'Company', 'Job Title', 'Phone', 'Country',
        'Message', 'Consent', 'UTM Source', 'UTM Medium', 'UTM Campaign',
        'Referrer', 'IP Address', 'User Agent', 'Created At'
    ])
    
    for row in leads:
        writer.writerow([
            row['id'], row['source_page'], row['cta_clicked'], row['first_name'], row['last_name'],
            row['business_email'], row['company'], row['job_title'], row['phone'], row['country'],
            row['message'], row['consent'], row['utm_source'], row['utm_medium'], row['utm_campaign'],
            row['referrer'], row['ip_address'], row['user_agent'], row['created_at']
        ])
        
    output.seek(0)
    return response

# ==========================================================================
# Manufacturing Industry Microsite Frontend Routes & Helpers
# ==========================================================================

def render_manufacturing_page(page_key):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = ? AND status = 'Published'", (page_key,)).fetchone()
    conn.close()
    if not page:
        abort(404)
        
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    related_services = json.loads(page['related_services_json'] or '[]')
    
    template_name = 'manufacturing_page.html'
    if page_key == 'mfg-overview':
        template_name = 'manufacturing_overview.html'
        
    return render_template(
        template_name,
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        related_services=related_services,
        active_subpage=page_key.replace('mfg-', ''),
        active_page='industries'
    )

@app.route('/industries/manufacturing')
def manufacturing_overview():
    return render_manufacturing_page('mfg-overview')

@app.route('/industries/manufacturing/use-cases')
def manufacturing_use_cases():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'mfg-use-cases' AND status = 'Published'").fetchone()
    use_cases = conn.execute("SELECT * FROM manufacturing_use_cases WHERE status = 'Published'").fetchall()
    
    # Extract tags for filters
    all_tags = set()
    for uc in use_cases:
        if uc['tags']:
            for tag in uc['tags'].split(','):
                all_tags.add(tag.strip())
                
    conn.close()
    if not page:
        abort(404)
        
    return render_template(
        'manufacturing_use_cases.html',
        page=page,
        use_cases=use_cases,
        tags=sorted(list(all_tags)),
        active_subpage='use-cases',
        active_page='industries'
    )

@app.route('/industries/manufacturing/case-studies')
def manufacturing_case_studies():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'mfg-case-studies' AND status = 'Published'").fetchone()
    # Query published global case studies tagged with Manufacturing
    db_case_studies = conn.execute(
        "SELECT * FROM case_studies WHERE status = 'Published' AND (tags LIKE '%Manufacturing%' OR industry LIKE '%Manufacturing%') ORDER BY id DESC"
    ).fetchall()
    conn.close()
    
    if not page:
        abort(404)
        
    return render_template(
        'manufacturing_case_studies.html',
        page=page,
        case_studies=db_case_studies,
        active_subpage='case-studies',
        active_page='industries'
    )

@app.route('/industries/manufacturing/<slug>')
def manufacturing_subpage(slug):
    clean_slug = slug.strip('/')
    page_key = f"mfg-{clean_slug}"
    
    conn = get_db_connection()
    db_slug = f"manufacturing/{clean_slug}"
    row = conn.execute(
        "SELECT page_key FROM industry_microsite_pages WHERE slug = ? OR page_key = ?",
        (db_slug, page_key)
    ).fetchone()
    conn.close()
    
    if row:
        return render_manufacturing_page(row['page_key'])
        
    abort(404)

@app.route('/industries/manufacturing/submit-lead', methods=['POST'])
def manufacturing_submit_lead():
    # Honeypot spam protection
    honeypot = request.form.get('website_url_honeypot', '')
    if honeypot:
        return jsonify({'status': 'error', 'message': 'Spam detected.'}), 400
        
    source_page = request.form.get('source_page', 'Manufacturing Microsite')
    cta_clicked = request.form.get('cta_clicked', 'General Contact')
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('business_email', '').strip().lower()
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    phone = request.form.get('phone', '')
    country = request.form.get('country', '')
    area_of_interest = request.form.get('area_of_interest', '')
    message = request.form.get('message', '')
    consent = 1 if request.form.get('consent') else 0
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    # Personal domain validation
    personal_domains = [
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    ]
    if '@' not in email:
        return jsonify({'status': 'error', 'message': 'Invalid email address.'}), 400
        
    domain = email.split('@')[1]
    if domain in personal_domains:
        return jsonify({'status': 'error', 'message': 'Please use your corporate business email address.'}), 400
        
    # UTM parameter extraction
    utm_source = request.form.get('utm_source', '')
    utm_medium = request.form.get('utm_medium', '')
    utm_campaign = request.form.get('utm_campaign', '')
    utm_term = request.form.get('utm_term', '')
    utm_content = request.form.get('utm_content', '')
    referrer = request.form.get('referrer', '')
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    
    conn = get_db_connection()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        INSERT INTO manufacturing_leads (
            source_page, cta_clicked, first_name, last_name, business_email,
            company, job_title, phone, country, area_of_interest, message, consent,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        source_page, cta_clicked, first_name, last_name, email,
        company, job_title, phone, country, area_of_interest, message, consent,
        utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Thank you! Your request has been received. A manufacturing data advisor will reach out shortly.'})

# ==========================================================================
# Manufacturing Industry Microsite Administrative Routes
# ==========================================================================

@app.route('/admin/industries/manufacturing')
def admin_manufacturing_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    total_leads = conn.execute("SELECT COUNT(*) FROM manufacturing_leads").fetchone()[0]
    total_use_cases = conn.execute("SELECT COUNT(*) FROM manufacturing_use_cases").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM industry_microsite_pages WHERE industry = 'manufacturing'").fetchone()[0]
    recent_leads = conn.execute("SELECT * FROM manufacturing_leads ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    return render_template(
        'admin_manufacturing_dashboard.html',
        total_leads=total_leads,
        total_use_cases=total_use_cases,
        total_pages=total_pages,
        recent_leads=recent_leads,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/pages')
def admin_manufacturing_pages():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE industry = 'manufacturing' ORDER BY id ASC").fetchall()
    conn.close()
    return render_template(
        'admin_manufacturing_pages.html',
        pages=pages,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/pages/<int:page_id>', methods=['GET', 'POST', 'PUT'])
def admin_manufacturing_page_edit(page_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE id = ? AND industry = 'manufacturing'", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        hero_title = request.form.get('hero_title')
        hero_subtitle = request.form.get('hero_subtitle')
        body_sections_json = request.form.get('body_sections_json')
        cta_json = request.form.get('cta_json')
        faq_json = request.form.get('faq_json')
        related_services_json = request.form.get('related_services_json')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        canonical_url = request.form.get('canonical_url')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        og_image = request.form.get('og_image')
        schema_json = request.form.get('schema_json')
        ai_summary = request.form.get('ai_summary')
        genai_entities_json = request.form.get('genai_entities_json')
        status = request.form.get('status', 'Published')
        noindex = 1 if request.form.get('noindex') else 0
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute("""
            UPDATE industry_microsite_pages
            SET title = ?, hero_title = ?, hero_subtitle = ?, body_sections_json = ?,
                cta_json = ?, faq_json = ?, related_services_json = ?, seo_title = ?,
                seo_description = ?, seo_keywords = ?, canonical_url = ?, og_title = ?,
                og_description = ?, og_image = ?, schema_json = ?, ai_summary = ?,
                genai_entities_json = ?, status = ?, noindex = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, hero_title, hero_subtitle, body_sections_json,
            cta_json, faq_json, related_services_json, seo_title,
            seo_description, seo_keywords, canonical_url, og_title,
            og_description, og_image, schema_json, ai_summary,
            genai_entities_json, status, noindex, now_str, page_id
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/industries/manufacturing/pages')
        
    conn.close()
    return render_template(
        'admin_manufacturing_page_edit.html',
        page=page,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/use-cases')
def admin_manufacturing_use_cases():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_cases = conn.execute("SELECT * FROM manufacturing_use_cases ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_manufacturing_use_cases.html',
        use_cases=use_cases,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/use-cases/new', methods=['GET', 'POST'])
def admin_manufacturing_use_case_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO manufacturing_use_cases (
                    title, slug, category, problem, data_domains, artha_solution,
                    technologies, business_outcomes, related_services, related_case_studies,
                    tags, seo_title, seo_description, ai_summary, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, slug, category, problem, data_domains, artha_solution,
                technologies, business_outcomes, related_services, related_case_studies,
                tags, seo_title, seo_description, ai_summary, status, now_str, now_str
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error: Slug must be unique.", 400
        conn.close()
        
        return redirect('/admin/industries/manufacturing/use-cases')
        
    return render_template(
        'admin_manufacturing_use_case_edit.html',
        use_case=None,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/use-cases/<int:uc_id>', methods=['GET', 'POST', 'PUT'])
def admin_manufacturing_use_case_edit(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_case = conn.execute("SELECT * FROM manufacturing_use_cases WHERE id = ?", (uc_id,)).fetchone()
    
    if not use_case:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute("""
            UPDATE manufacturing_use_cases
            SET title = ?, slug = ?, category = ?, problem = ?, data_domains = ?,
                artha_solution = ?, technologies = ?, business_outcomes = ?,
                related_services = ?, related_case_studies = ?, tags = ?,
                seo_title = ?, seo_description = ?, ai_summary = ?, status = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, slug, category, problem, data_domains, artha_solution,
            technologies, business_outcomes, related_services, related_case_studies,
            tags, seo_title, seo_description, ai_summary, status, now_str, uc_id
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/industries/manufacturing/use-cases')
        
    conn.close()
    return render_template(
        'admin_manufacturing_use_case_edit.html',
        use_case=use_case,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/use-cases/<int:uc_id>/delete', methods=['POST', 'DELETE'])
def admin_manufacturing_use_case_delete(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM manufacturing_use_cases WHERE id = ?", (uc_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/industries/manufacturing/use-cases')

@app.route('/admin/industries/manufacturing/leads')
def admin_manufacturing_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM manufacturing_leads ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_manufacturing_leads.html',
        leads=leads,
        active_page='manufacturing_admin'
    )

@app.route('/admin/industries/manufacturing/export-leads')
def admin_manufacturing_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM manufacturing_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Source Page', 'CTA Clicked', 'First Name', 'Last Name',
        'Business Email', 'Company', 'Job Title', 'Phone', 'Country',
        'Area of Interest', 'Message', 'Consent', 'UTM Source', 'UTM Medium', 'UTM Campaign',
        'Referrer', 'IP Address', 'User Agent', 'Created At'
    ])
    
    for row in leads:
        writer.writerow([
            row['id'], row['source_page'], row['cta_clicked'], row['first_name'], row['last_name'],
            row['business_email'], row['company'], row['job_title'], row['phone'], row['country'],
            row['area_of_interest'], row['message'], row['consent'], row['utm_source'], row['utm_medium'], row['utm_campaign'],
            row['referrer'], row['ip_address'], row['user_agent'], row['created_at']
        ])
        
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=manufacturing_leads.csv'
    response.headers['Content-type'] = 'text/csv'
    return response


# ==========================================================================
# BFSI Industry Microsite Frontend Routes & Helpers
# ==========================================================================

def render_bfsi_page(page_key):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = ? AND status = 'Published'", (page_key,)).fetchone()
    conn.close()
    if not page:
        abort(404)
        
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    related_services = json.loads(page['related_services_json'] or '[]')
    
    template_name = 'bfsi_page.html'
    if page_key == 'bfsi-overview':
        template_name = 'bfsi_overview.html'
        
    return render_template(
        template_name,
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        related_services=related_services,
        active_subpage=page_key.replace('bfsi-', ''),
        active_page='industries'
    )

@app.route('/industries/bfsi')
def bfsi_overview():
    return render_bfsi_page('bfsi-overview')

@app.route('/industries/bfsi/use-cases')
def bfsi_use_cases():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'bfsi-use-cases' AND status = 'Published'").fetchone()
    use_cases = conn.execute("SELECT * FROM bfsi_use_cases WHERE status = 'Published'").fetchall()
    
    # Extract tags for filters
    all_tags = set()
    for uc in use_cases:
        if uc['tags']:
            for tag in uc['tags'].split(','):
                all_tags.add(tag.strip())
                
    conn.close()
    if not page:
        abort(404)
        
    return render_template(
        'bfsi_use_cases.html',
        page=page,
        use_cases=use_cases,
        tags=sorted(list(all_tags)),
        active_subpage='use-cases',
        active_page='industries'
    )

@app.route('/industries/bfsi/case-studies')
def bfsi_case_studies():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'bfsi-case-studies' AND status = 'Published'").fetchone()
    # Query published global case studies tagged with BFSI/Banking/Insurance
    db_case_studies = conn.execute(
        "SELECT * FROM case_studies WHERE status = 'Published' AND (tags LIKE '%BFSI%' OR tags LIKE '%Banking%' OR tags LIKE '%Insurance%' OR industry LIKE '%BFSI%' OR industry LIKE '%Banking%' OR industry LIKE '%Insurance%') ORDER BY id DESC"
    ).fetchall()
    conn.close()
    
    if not page:
        abort(404)
        
    return render_template(
        'bfsi_case_studies.html',
        page=page,
        case_studies=db_case_studies,
        active_subpage='case-studies',
        active_page='industries'
    )

@app.route('/industries/bfsi/<slug>')
def bfsi_subpage(slug):
    clean_slug = slug.strip('/')
    page_key = f"bfsi-{clean_slug}"
    
    conn = get_db_connection()
    db_slug = f"bfsi/{clean_slug}"
    row = conn.execute(
        "SELECT page_key FROM industry_microsite_pages WHERE slug = ? OR page_key = ?",
        (db_slug, page_key)
    ).fetchone()
    conn.close()
    
    if row:
        return render_bfsi_page(row['page_key'])
        
    abort(404)

@app.route('/industries/bfsi/submit-lead', methods=['POST'])
def bfsi_submit_lead():
    # Honeypot spam protection
    honeypot = request.form.get('website_url_honeypot', '')
    if honeypot:
        return jsonify({'status': 'error', 'message': 'Spam detected.'}), 400
        
    source_page = request.form.get('source_page', 'BFSI Microsite')
    cta_clicked = request.form.get('cta_clicked', 'General Contact')
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('business_email', '').strip().lower()
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    phone = request.form.get('phone', '')
    country = request.form.get('country', '')
    area_of_interest = request.form.get('area_of_interest', '')
    message = request.form.get('message', '')
    consent = 1 if request.form.get('consent') else 0
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    # Personal domain validation
    personal_domains = [
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    ]
    domain = email.split('@')[1]
    if domain in personal_domains:
        return jsonify({'status': 'error', 'message': 'Please use your corporate business email address. Personal email domains are not accepted.'}), 400

    utm_source = request.args.get('utm_source') or request.form.get('utm_source')
    utm_medium = request.args.get('utm_medium') or request.form.get('utm_medium')
    utm_campaign = request.args.get('utm_campaign') or request.form.get('utm_campaign')
    utm_term = request.args.get('utm_term') or request.form.get('utm_term')
    utm_content = request.args.get('utm_content') or request.form.get('utm_content')
    referrer = request.referrer
    ip_address = request.remote_addr
    user_agent = request.user_agent.string
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO bfsi_leads (
            source_page, cta_clicked, first_name, last_name, business_email,
            company, job_title, phone, country, area_of_interest, message, consent,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_page, cta_clicked, first_name, last_name, email,
        company, job_title, phone, country, area_of_interest, message, consent,
        utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Thank you! Your request has been received. A BFSI data advisor will reach out shortly.'})


# ==========================================================================
# BFSI Industry Microsite Administrative Routes
# ==========================================================================

@app.route('/admin/industries/bfsi')
def admin_bfsi_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    total_leads = conn.execute("SELECT COUNT(*) FROM bfsi_leads").fetchone()[0]
    total_use_cases = conn.execute("SELECT COUNT(*) FROM bfsi_use_cases").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM industry_microsite_pages WHERE industry = 'bfsi'").fetchone()[0]
    recent_leads = conn.execute("SELECT * FROM bfsi_leads ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    return render_template(
        'admin_bfsi_dashboard.html',
        total_leads=total_leads,
        total_use_cases=total_use_cases,
        total_pages=total_pages,
        recent_leads=recent_leads,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/pages')
def admin_bfsi_pages():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE industry = 'bfsi' ORDER BY id ASC").fetchall()
    conn.close()
    return render_template(
        'admin_bfsi_pages.html',
        pages=pages,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/pages/<int:page_id>', methods=['GET', 'POST', 'PUT'])
def admin_bfsi_page_edit(page_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE id = ? AND industry = 'bfsi'", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        hero_title = request.form.get('hero_title')
        hero_subtitle = request.form.get('hero_subtitle')
        body_sections_json = request.form.get('body_sections_json')
        cta_json = request.form.get('cta_json')
        faq_json = request.form.get('faq_json')
        related_services_json = request.form.get('related_services_json')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        canonical_url = request.form.get('canonical_url')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        og_image = request.form.get('og_image')
        schema_json = request.form.get('schema_json')
        ai_summary = request.form.get('ai_summary')
        genai_entities_json = request.form.get('genai_entities_json')
        status = request.form.get('status', 'Published')
        noindex = 1 if request.form.get('noindex') else 0
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute("""
            UPDATE industry_microsite_pages
            SET title = ?, hero_title = ?, hero_subtitle = ?, body_sections_json = ?,
                cta_json = ?, faq_json = ?, related_services_json = ?, seo_title = ?,
                seo_description = ?, seo_keywords = ?, canonical_url = ?, og_title = ?,
                og_description = ?, og_image = ?, schema_json = ?, ai_summary = ?,
                genai_entities_json = ?, status = ?, noindex = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, hero_title, hero_subtitle, body_sections_json,
            cta_json, faq_json, related_services_json, seo_title,
            seo_description, seo_keywords, canonical_url, og_title,
            og_description, og_image, schema_json, ai_summary,
            genai_entities_json, status, noindex, now_str, page_id
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/industries/bfsi/pages')
        
    conn.close()
    return render_template(
        'admin_bfsi_page_edit.html',
        page=page,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/use-cases')
def admin_bfsi_use_cases():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_cases = conn.execute("SELECT * FROM bfsi_use_cases ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_bfsi_use_cases.html',
        use_cases=use_cases,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/use-cases/new', methods=['GET', 'POST'])
def admin_bfsi_use_case_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO bfsi_use_cases (
                    title, slug, category, audience_type, problem, data_domains, artha_solution,
                    technologies, business_outcomes, related_services, related_case_studies,
                    tags, seo_title, seo_description, ai_summary, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, slug, category, audience_type, problem, data_domains, artha_solution,
                technologies, business_outcomes, related_services, related_case_studies,
                tags, seo_title, seo_description, ai_summary, status, now_str, now_str
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error: Slug must be unique.", 400
        conn.close()
        
        return redirect('/admin/industries/bfsi/use-cases')
        
    return render_template(
        'admin_bfsi_use_case_edit.html',
        use_case=None,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/use-cases/<int:uc_id>', methods=['GET', 'POST'])
def admin_bfsi_use_case_edit(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_case = conn.execute("SELECT * FROM bfsi_use_cases WHERE id = ?", (uc_id,)).fetchone()
    
    if not use_case:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            conn.execute("""
                UPDATE bfsi_use_cases
                SET title = ?, slug = ?, category = ?, audience_type = ?, problem = ?, data_domains = ?,
                    artha_solution = ?, technologies = ?, business_outcomes = ?, related_services = ?,
                    related_case_studies = ?, tags = ?, seo_title = ?, seo_description = ?,
                    ai_summary = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (
                title, slug, category, audience_type, problem, data_domains,
                artha_solution, technologies, business_outcomes, related_services,
                related_case_studies, tags, seo_title, seo_description,
                ai_summary, status, now_str, uc_id
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error: Slug must be unique.", 400
            
        conn.close()
        return redirect('/admin/industries/bfsi/use-cases')
        
    conn.close()
    return render_template(
        'admin_bfsi_use_case_edit.html',
        use_case=use_case,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/use-cases/<int:uc_id>/delete', methods=['POST', 'DELETE'])
def admin_bfsi_use_case_delete(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM bfsi_use_cases WHERE id = ?", (uc_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/industries/bfsi/use-cases')

@app.route('/admin/industries/bfsi/leads')
def admin_bfsi_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM bfsi_leads ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_bfsi_leads.html',
        leads=leads,
        active_page='bfsi_admin'
    )

@app.route('/admin/industries/bfsi/export-leads')
def admin_bfsi_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM bfsi_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Source Page', 'CTA Clicked', 'First Name', 'Last Name',
        'Business Email', 'Company', 'Job Title', 'Phone', 'Country',
        'Area of Interest', 'Message', 'Consent', 'UTM Source', 'UTM Medium', 'UTM Campaign',
        'Referrer', 'IP Address', 'User Agent', 'Created At'
    ])
    
    for row in leads:
        writer.writerow([
            row['id'], row['source_page'], row['cta_clicked'], row['first_name'], row['last_name'],
            row['business_email'], row['company'], row['job_title'], row['phone'], row['country'],
            row['area_of_interest'], row['message'], row['consent'], row['utm_source'], row['utm_medium'], row['utm_campaign'],
            row['referrer'], row['ip_address'], row['user_agent'], row['created_at']
        ])
        
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=bfsi_leads.csv'
    response.headers['Content-type'] = 'text/csv'
    return response


# ==========================================================================
# Retail Industry Microsite Frontend Routes & Helpers
# ==========================================================================

def render_retail_page(page_key):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = ? AND status = 'Published'", (page_key,)).fetchone()
    conn.close()
    if not page:
        abort(404)
        
    body_sections = json.loads(page['body_sections_json'] or '{}')
    cta = json.loads(page['cta_json'] or '{}')
    faqs = json.loads(page['faq_json'] or '[]')
    related_services = json.loads(page['related_services_json'] or '[]')
    
    template_name = 'retail_page.html'
    if page_key == 'retail-overview':
        template_name = 'retail_overview.html'
        
    return render_template(
        template_name,
        page=page,
        body_sections=body_sections,
        cta=cta,
        faqs=faqs,
        related_services=related_services,
        active_subpage=page_key.replace('retail-', ''),
        active_page='industries'
    )

@app.route('/industries/retail')
def retail_overview():
    return render_retail_page('retail-overview')

@app.route('/industries/retail/use-cases')
def retail_use_cases():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'retail-use-cases' AND status = 'Published'").fetchone()
    use_cases = conn.execute("SELECT * FROM retail_use_cases WHERE status = 'Published'").fetchall()
    
    # Extract tags for filters
    all_tags = set()
    for uc in use_cases:
        if uc['tags']:
            for tag in uc['tags'].split(','):
                all_tags.add(tag.strip())
                
    conn.close()
    if not page:
        abort(404)
        
    return render_template(
        'retail_use_cases.html',
        page=page,
        use_cases=use_cases,
        tags=sorted(list(all_tags)),
        active_subpage='use-cases',
        active_page='industries'
    )

@app.route('/industries/retail/case-studies')
def retail_case_studies():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE page_key = 'retail-case-studies' AND status = 'Published'").fetchone()
    # Query published global case studies tagged with Retail/E-commerce/Consumer/Omnichannel/Customer 360/Product 360/Supplier/Inventory/ESG/Supply Chain
    db_case_studies = conn.execute(
        """SELECT * FROM case_studies WHERE status = 'Published' AND (
           tags LIKE '%Retail%' OR tags LIKE '%E-commerce%' OR tags LIKE '%Consumer%' OR tags LIKE '%Omnichannel%' OR
           tags LIKE '%Customer 360%' OR tags LIKE '%Product 360%' OR tags LIKE '%Supplier%' OR tags LIKE '%Inventory%' OR
           tags LIKE '%ESG%' OR tags LIKE '%Supply Chain%' OR
           industry LIKE '%Retail%' OR industry LIKE '%E-commerce%' OR industry LIKE '%Consumer%' OR industry LIKE '%Omnichannel%' OR
           industry LIKE '%Customer 360%' OR industry LIKE '%Product 360%' OR industry LIKE '%Supplier%' OR industry LIKE '%Inventory%' OR
           industry LIKE '%ESG%' OR industry LIKE '%Supply Chain%'
        ) ORDER BY id DESC"""
    ).fetchall()
    conn.close()
    
    if not page:
        abort(404)
        
    return render_template(
        'retail_case_studies.html',
        page=page,
        case_studies=db_case_studies,
        active_subpage='case-studies',
        active_page='industries'
    )

@app.route('/industries/retail/<slug>')
def retail_subpage(slug):
    clean_slug = slug.strip('/')
    page_key = f"retail-{clean_slug}"
    
    conn = get_db_connection()
    db_slug = f"retail/{clean_slug}"
    row = conn.execute(
        "SELECT page_key FROM industry_microsite_pages WHERE slug = ? OR page_key = ?",
        (db_slug, page_key)
    ).fetchone()
    conn.close()
    
    if row:
        return render_retail_page(row['page_key'])
        
    abort(404)

@app.route('/industries/retail/submit-lead', methods=['POST'])
def retail_submit_lead():
    # Honeypot spam protection
    honeypot = request.form.get('website_url_honeypot', '')
    if honeypot:
        return jsonify({'status': 'error', 'message': 'Spam detected.'}), 400
        
    source_page = request.form.get('source_page', 'Retail Microsite')
    cta_clicked = request.form.get('cta_clicked', 'General Contact')
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('business_email', '').strip().lower()
    company = request.form.get('company', '')
    job_title = request.form.get('job_title', '')
    phone = request.form.get('phone', '')
    country = request.form.get('country', '')
    area_of_interest = request.form.get('area_of_interest', '')
    message = request.form.get('message', '')
    consent = 1 if request.form.get('consent') else 0
    
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
        
    # Personal domain validation
    personal_domains = [
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
        'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk'
    ]
    
    email_parts = email.split('@')
    if len(email_parts) != 2:
        return jsonify({'status': 'error', 'message': 'Invalid email format.'}), 400
        
    domain = email_parts[1]
    if domain in personal_domains:
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Personal email domains such as Gmail/Yahoo/Outlook are not accepted.'}), 400

    utm_source = request.args.get('utm_source') or request.form.get('utm_source')
    utm_medium = request.args.get('utm_medium') or request.form.get('utm_medium')
    utm_campaign = request.args.get('utm_campaign') or request.form.get('utm_campaign')
    utm_term = request.args.get('utm_term') or request.form.get('utm_term')
    utm_content = request.args.get('utm_content') or request.form.get('utm_content')
    referrer = request.referrer
    ip_address = request.remote_addr
    user_agent = request.user_agent.string
    
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO retail_leads (
            source_page, cta_clicked, first_name, last_name, business_email,
            company, job_title, phone, country, area_of_interest, message, consent,
            utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_page, cta_clicked, first_name, last_name, email,
        company, job_title, phone, country, area_of_interest, message, consent,
        utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, now_str
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Thank you! Your request has been received. A ThinkArtha retail data expert will contact you shortly.'})


# ==========================================================================
# Retail Industry Microsite Administrative Routes
# ==========================================================================

@app.route('/admin/industries/retail')
def admin_retail_dashboard():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    total_leads = conn.execute("SELECT COUNT(*) FROM retail_leads").fetchone()[0]
    total_use_cases = conn.execute("SELECT COUNT(*) FROM retail_use_cases").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM industry_microsite_pages WHERE industry = 'retail'").fetchone()[0]
    recent_leads = conn.execute("SELECT * FROM retail_leads ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    
    return render_template(
        'admin_retail_dashboard.html',
        total_leads=total_leads,
        total_use_cases=total_use_cases,
        total_pages=total_pages,
        recent_leads=recent_leads,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/pages')
def admin_retail_pages():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE industry = 'retail' ORDER BY id ASC").fetchall()
    conn.close()
    return render_template(
        'admin_retail_pages.html',
        pages=pages,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/pages/<int:page_id>', methods=['GET', 'POST', 'PUT'])
def admin_retail_page_edit(page_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM industry_microsite_pages WHERE id = ? AND industry = 'retail'", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    if request.method in ['POST', 'PUT']:
        title = request.form.get('title')
        hero_title = request.form.get('hero_title')
        hero_subtitle = request.form.get('hero_subtitle')
        body_sections_json = request.form.get('body_sections_json')
        cta_json = request.form.get('cta_json')
        faq_json = request.form.get('faq_json')
        related_services_json = request.form.get('related_services_json')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        seo_keywords = request.form.get('seo_keywords')
        canonical_url = request.form.get('canonical_url')
        og_title = request.form.get('og_title')
        og_description = request.form.get('og_description')
        og_image = request.form.get('og_image')
        schema_json = request.form.get('schema_json')
        ai_summary = request.form.get('ai_summary')
        genai_entities_json = request.form.get('genai_entities_json')
        status = request.form.get('status', 'Published')
        noindex = 1 if request.form.get('noindex') else 0
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute("""
            UPDATE industry_microsite_pages
            SET title = ?, hero_title = ?, hero_subtitle = ?, body_sections_json = ?,
                cta_json = ?, faq_json = ?, related_services_json = ?, seo_title = ?,
                seo_description = ?, seo_keywords = ?, canonical_url = ?, og_title = ?,
                og_description = ?, og_image = ?, schema_json = ?, ai_summary = ?,
                genai_entities_json = ?, status = ?, noindex = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, hero_title, hero_subtitle, body_sections_json,
            cta_json, faq_json, related_services_json, seo_title,
            seo_description, seo_keywords, canonical_url, og_title,
            og_description, og_image, schema_json, ai_summary,
            genai_entities_json, status, noindex, now_str, page_id
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/industries/retail/pages')
        
    conn.close()
    return render_template(
        'admin_retail_page_edit.html',
        page=page,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/use-cases')
def admin_retail_use_cases():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_cases = conn.execute("SELECT * FROM retail_use_cases ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_retail_use_cases.html',
        use_cases=use_cases,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/use-cases/new', methods=['GET', 'POST'])
def admin_retail_use_case_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO retail_use_cases (
                    title, slug, category, audience_type, problem, data_domains, artha_solution,
                    technologies, business_outcomes, related_services, related_case_studies,
                    tags, seo_title, seo_description, ai_summary, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, slug, category, audience_type, problem, data_domains, artha_solution,
                technologies, business_outcomes, related_services, related_case_studies,
                tags, seo_title, seo_description, ai_summary, status, now_str, now_str
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error: Slug must be unique.", 400
        conn.close()
        
        return redirect('/admin/industries/retail/use-cases')
        
    return render_template(
        'admin_retail_use_case_edit.html',
        use_case=None,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/use-cases/<int:uc_id>', methods=['GET', 'POST'])
def admin_retail_use_case_edit(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    use_case = conn.execute("SELECT * FROM retail_use_cases WHERE id = ?", (uc_id,)).fetchone()
    
    if not use_case:
        conn.close()
        abort(404)
        
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        audience_type = request.form.get('audience_type')
        problem = request.form.get('problem')
        data_domains = request.form.get('data_domains')
        artha_solution = request.form.get('artha_solution')
        technologies = request.form.get('technologies')
        business_outcomes = request.form.get('business_outcomes')
        related_services = request.form.get('related_services')
        related_case_studies = request.form.get('related_case_studies')
        tags = request.form.get('tags')
        seo_title = request.form.get('seo_title')
        seo_description = request.form.get('seo_description')
        ai_summary = request.form.get('ai_summary')
        status = request.form.get('status', 'Published')
        
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            conn.execute("""
                UPDATE retail_use_cases
                SET title = ?, slug = ?, category = ?, audience_type = ?, problem = ?, data_domains = ?,
                    artha_solution = ?, technologies = ?, business_outcomes = ?, related_services = ?,
                    related_case_studies = ?, tags = ?, seo_title = ?, seo_description = ?,
                    ai_summary = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (
                title, slug, category, audience_type, problem, data_domains,
                artha_solution, technologies, business_outcomes, related_services,
                related_case_studies, tags, seo_title, seo_description,
                ai_summary, status, now_str, uc_id
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error: Slug must be unique.", 400
            
        conn.close()
        return redirect('/admin/industries/retail/use-cases')
        
    conn.close()
    return render_template(
        'admin_retail_use_case_edit.html',
        use_case=use_case,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/use-cases/<int:uc_id>/delete', methods=['POST', 'DELETE'])
def admin_retail_use_case_delete(uc_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM retail_use_cases WHERE id = ?", (uc_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/industries/retail/use-cases')

@app.route('/admin/industries/retail/leads')
def admin_retail_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM retail_leads ORDER BY id DESC").fetchall()
    conn.close()
    return render_template(
        'admin_retail_leads.html',
        leads=leads,
        active_page='retail_admin'
    )

@app.route('/admin/industries/retail/export-leads')
def admin_retail_export_leads():
    if 'logged_in' not in session:
        return redirect('/admin/login')
        
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM retail_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Source Page', 'CTA Clicked', 'First Name', 'Last Name',
        'Business Email', 'Company', 'Job Title', 'Phone', 'Country',
        'Area of Interest', 'Message', 'Consent', 'UTM Source', 'UTM Medium', 'UTM Campaign',
        'Referrer', 'IP Address', 'User Agent', 'Created At'
    ])
    
    for row in leads:
        writer.writerow([
            row['id'], row['source_page'], row['cta_clicked'], row['first_name'], row['last_name'],
            row['business_email'], row['company'], row['job_title'], row['phone'], row['country'],
            row['area_of_interest'], row['message'], row['consent'], row['utm_source'], row['utm_medium'], row['utm_campaign'],
            row['referrer'], row['ip_address'], row['user_agent'], row['created_at']
        ])
        
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=retail_leads.csv'
    response.headers['Content-type'] = 'text/csv'
    return response


# --- Dynamic Navigation API & Admin Routes ---

@app.route('/api/navigation/main')
def get_main_navigation():
    menu_data = load_navigation_menu()
    return jsonify(menu_data)

@app.route('/api/search/suggestions')
def search_suggestions():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    
    conn = sqlite3.connect('blog.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT title, slug FROM posts WHERE status = 'Published' AND (title LIKE ? OR summary LIKE ?) LIMIT 5", (f'%{q}%', f'%{q}%'))
    posts = [{'title': r['title'], 'url': f'/blog/{r["slug"]}', 'type': 'Blog'} for r in cursor.fetchall()]
    
    cursor.execute("SELECT title, slug FROM case_studies WHERE status = 'Published' AND (title LIKE ? OR solution_summary LIKE ?) LIMIT 5", (f'%{q}%', f'%{q}%'))
    cases = [{'title': r['title'], 'url': f'/case-studies/{r["slug"]}', 'type': 'Case Study'} for r in cursor.fetchall()]
    
    cursor.execute("SELECT title, url FROM industry_microsite_pages WHERE status = 'Published' AND (title LIKE ? OR hero_title LIKE ?) LIMIT 5", (f'%{q}%', f'%{q}%'))
    micropages = [{'title': r['title'], 'url': r['url'], 'type': 'Industry Page'} for r in cursor.fetchall()]
    
    conn.close()
    
    results = posts + cases + micropages
    return jsonify(results[:8])

# Admin Authentication Check Helper
def check_admin_auth():
    return 'logged_in' in session

@app.route('/admin/navigation')
def admin_navigation():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = sqlite3.connect('blog.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all menus
    cursor.execute("SELECT * FROM navigation_menus ORDER BY name")
    menus = [dict(m) for m in cursor.fetchall()]
    
    # Get all nav items
    cursor.execute("SELECT * FROM navigation_items ORDER BY parent_id, sort_order")
    items = [dict(item) for item in cursor.fetchall()]
    
    # Get all featured cards
    cursor.execute("SELECT * FROM navigation_featured_cards ORDER BY sort_order")
    featured_cards = [dict(c) for c in cursor.fetchall()]
    
    # Get all CTAs
    cursor.execute("SELECT * FROM navigation_ctas ORDER BY sort_order")
    ctas = [dict(cta) for cta in cursor.fetchall()]
    
    conn.close()
    
    # Organize hierarchy for template
    top_items = [i for i in items if i['is_top_level']]
    child_items = [i for i in items if not i['is_top_level']]
    
    return render_template(
        'admin_navigation.html',
        menus=menus,
        top_items=top_items,
        child_items=child_items,
        featured_cards=featured_cards,
        ctas=ctas
    )

@app.route('/admin/navigation/items', methods=['POST'])
def admin_add_nav_item():
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    label = data.get('label')
    if not label:
        return jsonify({'error': 'Label is required'}), 400
        
    menu_id = data.get('menu_id')
    parent_id = data.get('parent_id')
    parent_id = int(parent_id) if parent_id and str(parent_id).strip() not in ('', 'None') else None
    
    url = data.get('url', '#')
    description = data.get('description', '')
    icon = data.get('icon', '')
    badge = data.get('badge', '')
    group_label = data.get('group_label', '')
    sort_order = int(data.get('sort_order', 0))
    is_top_level = int(data.get('is_top_level', 0))
    is_featured = int(data.get('is_featured', 0))
    is_visible = int(data.get('is_visible', 1))
    opens_in_new_tab = int(data.get('opens_in_new_tab', 0))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO navigation_items (
            menu_id, parent_id, label, url, description, icon, badge, group_label, sort_order, is_top_level, is_featured, is_visible, opens_in_new_tab, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (menu_id, parent_id, label, url, description, icon, badge, group_label, sort_order, is_top_level, is_featured, is_visible, opens_in_new_tab, now, now))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/items/<int:id>', methods=['POST', 'PUT'])
def admin_edit_nav_item(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    label = data.get('label')
    if not label:
        return jsonify({'error': 'Label is required'}), 400
        
    parent_id = data.get('parent_id')
    parent_id = int(parent_id) if parent_id and str(parent_id).strip() not in ('', 'None') else None
    
    url = data.get('url', '#')
    description = data.get('description', '')
    icon = data.get('icon', '')
    badge = data.get('badge', '')
    group_label = data.get('group_label', '')
    sort_order = int(data.get('sort_order', 0))
    is_top_level = int(data.get('is_top_level', 0))
    is_featured = int(data.get('is_featured', 0))
    is_visible = int(data.get('is_visible', 1))
    opens_in_new_tab = int(data.get('opens_in_new_tab', 0))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE navigation_items SET
            parent_id = ?, label = ?, url = ?, description = ?, icon = ?, badge = ?, group_label = ?, sort_order = ?, is_top_level = ?, is_featured = ?, is_visible = ?, opens_in_new_tab = ?, updated_at = ?
        WHERE id = ?
    """, (parent_id, label, url, description, icon, badge, group_label, sort_order, is_top_level, is_featured, is_visible, opens_in_new_tab, now, id))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/items/<int:id>/delete', methods=['POST', 'DELETE'])
@app.route('/admin/navigation/items/<int:id>', methods=['DELETE'])
def admin_delete_nav_item(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    cursor.execute("UPDATE navigation_items SET parent_id = NULL WHERE parent_id = ?", (id,))
    cursor.execute("DELETE FROM navigation_items WHERE id = ?", (id,))
    
    conn.commit()
    conn.close()
    
    if request.form or request.method == 'POST':
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/featured-card', methods=['POST'])
def admin_add_featured_card():
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    title = data.get('title')
    menu_id = data.get('menu_id')
    parent_nav_item_id = int(data.get('parent_nav_item_id'))
    description = data.get('description', '')
    image_path = data.get('image_path', '')
    label = data.get('label', '')
    cta_text = data.get('cta_text', '')
    cta_url = data.get('cta_url', '')
    sort_order = int(data.get('sort_order', 0))
    is_visible = int(data.get('is_visible', 1))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO navigation_featured_cards (
            menu_id, parent_nav_item_id, title, description, image_path, label, cta_text, cta_url, sort_order, is_visible, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (menu_id, parent_nav_item_id, title, description, image_path, label, cta_text, cta_url, sort_order, is_visible, now, now))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/featured-card/<int:id>', methods=['POST', 'PUT'])
def admin_edit_featured_card(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    title = data.get('title')
    parent_nav_item_id = int(data.get('parent_nav_item_id'))
    description = data.get('description', '')
    image_path = data.get('image_path', '')
    label = data.get('label', '')
    cta_text = data.get('cta_text', '')
    cta_url = data.get('cta_url', '')
    sort_order = int(data.get('sort_order', 0))
    is_visible = int(data.get('is_visible', 1))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE navigation_featured_cards SET
            parent_nav_item_id = ?, title = ?, description = ?, image_path = ?, label = ?, cta_text = ?, cta_url = ?, sort_order = ?, is_visible = ?, updated_at = ?
        WHERE id = ?
    """, (parent_nav_item_id, title, description, image_path, label, cta_text, cta_url, sort_order, is_visible, now, id))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/featured-card/<int:id>/delete', methods=['POST', 'DELETE'])
@app.route('/admin/navigation/featured-card/<int:id>', methods=['DELETE'])
def admin_delete_featured_card(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM navigation_featured_cards WHERE id = ?", (id,))
    
    conn.commit()
    conn.close()
    
    if request.form or request.method == 'POST':
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/cta', methods=['POST'])
def admin_add_cta():
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    label = data.get('label')
    if not label:
        return jsonify({'error': 'Label is required'}), 400
        
    url = data.get('url', '')
    style = data.get('style', 'primary')
    location = data.get('location', 'header')
    is_visible = int(data.get('is_visible', 1))
    sort_order = int(data.get('sort_order', 0))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO navigation_ctas (
            label, url, style, location, is_visible, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (label, url, style, location, is_visible, sort_order, now, now))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/cta/<int:id>', methods=['POST', 'PUT'])
def admin_edit_cta(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.form if request.form else request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    label = data.get('label')
    if not label:
        return jsonify({'error': 'Label is required'}), 400
        
    url = data.get('url', '')
    style = data.get('style', 'primary')
    location = data.get('location', 'header')
    is_visible = int(data.get('is_visible', 1))
    sort_order = int(data.get('sort_order', 0))
    
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE navigation_ctas SET
            label = ?, url = ?, style = ?, location = ?, is_visible = ?, sort_order = ?, updated_at = ?
        WHERE id = ?
    """, (label, url, style, location, is_visible, sort_order, now, id))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/cta/<int:id>/delete', methods=['POST', 'DELETE'])
@app.route('/admin/navigation/cta/<int:id>', methods=['DELETE'])
def admin_delete_cta(id):
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM navigation_ctas WHERE id = ?", (id,))
    
    conn.commit()
    conn.close()
    
    if request.form or request.method == 'POST':
        return redirect('/admin/navigation')
    return jsonify({'success': True})

@app.route('/admin/navigation/publish', methods=['POST'])
def admin_publish_navigation():
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    now = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE navigation_menus 
        SET status = 'Published', published_at = ?, updated_at = ? 
        WHERE location = 'header'
    """, (now, now))
    
    conn.commit()
    conn.close()
    
    if request.form:
        return redirect('/admin/navigation')
    return jsonify({'success': True})


# Custom 404 Handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', active_page='none'), 404

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, host='127.0.0.1', port=5050)

