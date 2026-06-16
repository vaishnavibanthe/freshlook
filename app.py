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
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from werkzeug.utils import secure_filename
import pdf_extractor

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'artha-solutions-super-secret-key-2026')

# Configure Jinja2 to cache templates and disable auto-reloading to prevent OneDrive sync lock timeouts
app.config['TEMPLATES_AUTO_RELOAD'] = False
app.jinja_env.auto_reload = False

serializer = URLSafeTimedSerializer(app.secret_key)

# Register CRM Blueprint
from crm import crm_bp
app.register_blueprint(crm_bp)

@app.before_request
def handle_seo_and_referrals():
    # 1. Skip static assets, admin routes, CRM routes, and file downloads
    path = request.path
    if path.startswith('/static/') or path.startswith('/admin') or path.startswith('/api/') or path.startswith('/crm') or path.startswith('/uploads/'):
        return

    # 2. Check for redirect override
    try:
        conn = sqlite3.connect('blog.db')
        conn.row_factory = sqlite3.Row
        redirect_row = conn.execute("SELECT * FROM seo_redirects WHERE source_path = ? AND is_active = 1", (path,)).fetchone()
        conn.close()
        if redirect_row:
            target = redirect_row['target_path']
            code = redirect_row['redirect_type'] or 301
            return redirect(target, code=code)
    except Exception as e:
        print(f"Error checking redirects: {e}")

    # 3. Log traffic and referral source
    try:
        referrer = request.referrer or ''
        source_domain = ''
        referral_type = 'Direct'
        
        if referrer:
            from urllib.parse import urlparse
            parsed = urlparse(referrer)
            source_domain = parsed.netloc.lower()
            
            # Identify search engines
            search_engines = ['google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com', 'baidu.com', 'yandex.ru']
            # Identify AI search assistants
            ai_referrers = ['chatgpt.com', 'openai.com', 'perplexity.ai', 'gemini.google.com', 'copilot.microsoft.com', 'claude.ai', 'anthropic.com']
            
            if any(se in source_domain for se in search_engines):
                referral_type = 'Search Engine'
            elif any(ai in source_domain for ai in ai_referrers):
                referral_type = 'AI Assistant'
            else:
                referral_type = 'Referral'

        # Also capture UTMs
        utm_source = request.args.get('utm_source', '')
        utm_medium = request.args.get('utm_medium', '')
        utm_campaign = request.args.get('utm_campaign', '')
        
        # Simple IP hash for unique tracking (privacy compliant)
        import hashlib
        ip_hash = hashlib.sha256((request.remote_addr or '127.0.0.1').encode('utf-8')).hexdigest()[:16]
        
        # Log to db if not a duplicate visit in this session
        session_key = f"logged_visit_{path}_{referral_type}"
        if not session.get(session_key):
            conn = sqlite3.connect('blog.db')
            conn.execute("""
                INSERT INTO seo_traffic_logs (source_domain, referral_type, referrer_header, landing_page, utm_source, utm_medium, utm_campaign, ip_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_domain, referral_type, referrer, path, utm_source, utm_medium, utm_campaign, ip_hash))
            conn.commit()
            conn.close()
            session[session_key] = True
            session['last_traffic_log_path'] = path
    except Exception as e:
        print(f"Error logging traffic: {e}")

def mark_referral_conversion():
    try:
        # Check if we logged a visit
        last_path = session.get('last_traffic_log_path')
        if last_path:
            conn = sqlite3.connect('blog.db')
            # Update the latest visit record for this session
            conn.execute("""
                UPDATE seo_traffic_logs 
                SET converted = 1 
                WHERE landing_page = ? AND converted = 0 
                ORDER BY id DESC LIMIT 1
            """, (last_path,))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error marking conversion: {e}")

def forward_to_crm_wrapper(email, first_name, last_name, company, phone, job_title, geography, country, industry, message, source_form, source_page, cta_clicked, lead_source, utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer, ip_address, user_agent, consent_status=0):
    try:
        from crm.models import forward_lead_to_crm
        forward_lead_to_crm(
            email=email, first_name=first_name, last_name=last_name, company=company, phone=phone,
            job_title=job_title, geography=geography, country=country, industry=industry, message=message,
            source_form=source_form, source_page=source_page, cta_clicked=cta_clicked, lead_source=lead_source,
            utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign,
            utm_term=utm_term, utm_content=utm_content, referrer=referrer,
            ip_address=ip_address, user_agent=user_agent, consent_status=consent_status
        )
        mark_referral_conversion()
    except Exception as e:
        print(f"Error forwarding lead to CRM: {e}")

PERSONAL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'rediffmail.com',
    'protonmail.com', 'icloud.com', 'aol.com', 'mail.com', 'gmx.com',
    'yandex.com', 'zoho.com', 'proton.me', 'live.com', 'yahoo.co.in', 'hotmail.co.uk',
    'msn.com', 'comcast.net', 'yahoo.com.br', 'yahoo.co.jp', 'yahoo.fr', 'ymail.com',
    'mailinator.com', '123mail.org', 'fastmail.fm', 'web.de', 'gmx.net', 'libero.it',
    'wanadoo.fr', 'orange.fr', 'rambler.ru', 'mail.ru', 'mac.com', 'me.com'
}

def is_corporate_email(email):
    email = (email or '').strip().lower()
    if '@' not in email:
        return False
    parts = email.split('@')
    if len(parts) != 2:
        return False
    domain = parts[1].strip()
    if domain in PERSONAL_DOMAINS:
        return False
    return True

def validate_phone_number(phone):
    phone = (phone or '').strip()
    if not phone:
        return True
    if not re.match(r'^\+?[0-9\s.\-()]+$', phone):
        return False
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        return False
    if len(set(digits)) < 3:
        return False
    for i in range(len(digits) - 5):
        substring = digits[i:i+6]
        diffs = [int(substring[j+1]) - int(substring[j]) for j in range(5)]
        if all(d == 1 for d in diffs) or all(d == -1 for d in diffs):
            return False
    return True



# Global rate limiting cache for downloads: {ip: [timestamps]}
DOWNLOAD_RATE_LIMIT = {}

def get_db_connection():
    conn = sqlite3.connect('blog.db', timeout=30.0)
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

def categorize_content(text, tool_calls_str):
    combined = (text or "") + " " + (tool_calls_str or "")
    combined_lower = combined.lower()
    
    if any(k in combined_lower for k in ["admin_", "admin/", "admin"]):
        return "Admin Features"
    elif any(k in combined_lower for k in ["career", "job", "apply", "resume", "cv"]):
        return "Careers Section"
    elif any(k in combined_lower for k in ["case_study", "case_studies", "case-studies", "success story", "success_story"]):
        return "Case Studies"
    elif any(k in combined_lower for k in ["about_us", "about-us", "about us", "fetch_about"]):
        return "About Us Modernization"
    elif any(k in combined_lower for k in ["style.css", "design", "css", "layout", "aesthetic", "glow", "orbit"]):
        return "Design & Aesthetics"
    elif any(k in combined_lower for k in ["app.py", "content_store.py", "db_connection", "sqlite"]):
        return "Core Backend & Data"
    else:
        return "General / Infrastructure"

def sync_token_usage():
    import glob
    brain_dir = "/Users/amit/.gemini/antigravity-ide/brain"
    pattern = os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")
    log_files = glob.glob(pattern)
    if not log_files:
        return
    # Find the most recently modified transcript log file
    log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    log_file = log_files[0]
    
    if not os.path.exists(log_file):
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get max step_index
    try:
        cursor.execute("SELECT MAX(step_index) FROM token_usage")
        row = cursor.fetchone()
        max_step_index = row[0] if (row and row[0] is not None) else -1
    except Exception as e:
        max_step_index = -1
    
    new_rows = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    step_index = data.get("step_index")
                    if step_index is None or step_index <= max_step_index:
                        continue
                    
                    timestamp = data.get("created_at")
                    content = data.get("content") or ""
                    thinking = data.get("thinking") or ""
                    tool_calls = data.get("tool_calls")
                    tool_calls_str = json.dumps(tool_calls) if tool_calls else ""
                    
                    # Estimate tokens
                    content_tok = len(content) / 4.0
                    thinking_tok = len(thinking) / 4.0
                    tool_tok = len(tool_calls_str) / 4.0
                    
                    user_tokens = 0
                    system_tokens = 0
                    completion_tokens = 0
                    thinking_tokens = thinking_tok
                    
                    source = data.get("source")
                    msg_type = data.get("type")
                    
                    if source == "USER_EXPLICIT":
                        user_tokens = content_tok
                    elif source in ("SYSTEM", "TOOL"):
                        system_tokens = content_tok
                    elif source == "MODEL":
                        completion_tokens = content_tok + tool_tok
                    else:
                        if msg_type == "USER_INPUT":
                            user_tokens = content_tok
                        elif msg_type == "PLANNER_RESPONSE":
                            completion_tokens = content_tok + tool_tok
                        else:
                            system_tokens = content_tok
                            
                    category = categorize_content(content, tool_calls_str)
                    
                    new_rows.append((
                        step_index,
                        timestamp,
                        category,
                        user_tokens,
                        system_tokens,
                        completion_tokens,
                        thinking_tokens
                    ))
                except Exception:
                    continue
    except Exception as e:
        print(f"Error reading transcript.jsonl: {e}")
        conn.close()
        return
        
    if new_rows:
        try:
            cursor.executemany("""
                INSERT OR IGNORE INTO token_usage 
                (step_index, timestamp, category, user_tokens, system_tokens, completion_tokens, thinking_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, new_rows)
            conn.commit()
        except Exception as e:
            print(f"Error inserting token usage records: {e}")
            
    conn.close()

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
                            {'id': 9959, 'label': 'About Artha Solutions', 'url': '/about-us', 'description': 'Empower businesses with insightful innovations', 'icon': None},
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

def get_compiled_events():
    """Compile events and webinars into a unified, sorted list for widget display."""
    try:
        unified = get_event_listing_cards(public_only=True)
        if unified:
            return unified
    except Exception as e:
        print(f"Error compiling unified event cards: {e}")

    from datetime import datetime
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    combined = []
    for slug, item in get_db_events().items():
        loc_lower = item.get('location', '').lower()
        if 'virtual' in loc_lower or 'online' in loc_lower:
            del_type = 'Online'
        elif 'hybrid' in loc_lower:
            del_type = 'Hybrid'
        else:
            del_type = 'In-Person'
        combined.append({
            'type': 'Event',
            'slug': slug,
            'title': item.get('title'),
            'summary': item.get('summary'),
            'description': item.get('description'),
            'date_str': item.get('date'),
            'time': '10:00 AM EST' if 'north america' in item.get('title', '').lower() else '2:30 PM IST',
            'delivery_type': del_type,
            'location': item.get('location'),
            'url': f'/event-view/{slug}',
            'card_image': item.get('card_image')
        })
    for slug, item in get_db_webinars().items():
        combined.append({
            'type': 'Webinar',
            'slug': slug,
            'title': item.get('title'),
            'summary': item.get('summary'),
            'description': item.get('description'),
            'date_str': 'On-Demand',
            'time': item.get('duration', '45 min'),
            'delivery_type': 'Online',
            'location': item.get('host', 'Artha Solutions'),
            'url': f'/webinar-view/{slug}',
            'card_image': item.get('card_image')
        })

    def get_sort_key(ev):
        if ev['type'] == 'Webinar':
            return (1, ev['title'] or '')
        dt_str = ev.get('date_str', '')
        try:
            parts = (dt_str or '').replace(',', '').split()
            if len(parts) == 3:
                m = months.get(parts[0].lower(), 1)
                d = int(parts[1])
                y = int(parts[2])
                return (0, datetime(y, m, d))
        except Exception:
            pass
        return (0, datetime.max)

    combined.sort(key=get_sort_key)
    return combined

EVENT_CARD_IMAGES = [
    '/static/img/event_1.png',
    '/static/img/event_2.png',
    '/static/img/event_3.png',
    '/static/img/event_4.png',
    '/static/img/event_5.png',
    '/static/img/event_6.png'
]

EVENT_REGISTRATION_RATE_LIMIT = {}
EVENT_IMAGE_UPLOAD_ROOT = os.path.join(os.path.dirname(__file__), 'static', 'img', 'events', 'uploads')
EVENT_IMAGE_UPLOAD_URL_ROOT = '/static/img/events/uploads'
EVENT_ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg'}

EVENT_OPTIONAL_COLUMNS = {
    'event_label': 'TEXT',
    'tags': 'TEXT',
    'who_should_attend': 'TEXT',
    'why_attend': 'TEXT',
    'highlight_title': 'TEXT',
    'highlight_text': 'TEXT',
    'highlight_link': 'TEXT',
    'custom_cta_text': 'TEXT',
    'custom_cta_url': 'TEXT',
    'resource_download_url': 'TEXT',
    'calendar_details': 'TEXT',
    'business_email_only': 'INTEGER DEFAULT 1',
    'crm_integration_enabled': 'INTEGER DEFAULT 1',
    'product_solution_id': 'INTEGER',
    'partner_id': 'INTEGER'
}

def ensure_event_webinar_schema():
    conn = get_db_connection()
    try:
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_webinars'").fetchone()
        if not table:
            conn.close()
            from init_db import init_db
            init_db()
            conn = get_db_connection()

        cols = {
            row['name']
            for row in conn.execute("PRAGMA table_info(event_webinars)").fetchall()
        }
        for col_name, col_type in EVENT_OPTIONAL_COLUMNS.items():
            if col_name not in cols:
                conn.execute(f"ALTER TABLE event_webinars ADD COLUMN {col_name} {col_type}")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_webinars_slug ON event_webinars(slug)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_webinars_type_status ON event_webinars(content_type, publishing_status, lifecycle_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_registrations_event_id ON event_registrations(event_id)")
        conn.commit()
    finally:
        conn.close()

def slugify_value(value):
    value = (value or '').strip().lower()
    value = re.sub(r'[^a-z0-9\s-]', '', value)
    value = re.sub(r'\s+', '-', value)
    value = re.sub(r'-+', '-', value).strip('-')
    return value

def parse_event_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None

def build_event_datetime(date_value, time_value, fallback_time='09:00'):
    date_value = (date_value or '').strip()
    time_value = (time_value or fallback_time or '09:00').strip()
    if not date_value:
        return ''
    if len(time_value) == 5:
        time_value = f"{time_value}:00"
    return f"{date_value}T{time_value}"

def split_event_datetime(value):
    dt = parse_event_datetime(value)
    if not dt:
        return '', ''
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M')

def format_event_date(value, fallback='Date TBD'):
    dt = parse_event_datetime(value)
    if not dt:
        return fallback
    return dt.strftime('%B %d, %Y').replace(' 0', ' ')

def format_event_short_date(value, fallback='On Demand'):
    dt = parse_event_datetime(value)
    if not dt:
        return fallback
    return dt.strftime('%b %d, %Y').replace(' 0', ' ')

def format_event_time_range(event):
    if event.get('display_time_text'):
        return event.get('display_time_text')
    start_dt = parse_event_datetime(event.get('start_datetime'))
    end_dt = parse_event_datetime(event.get('end_datetime'))
    if not start_dt:
        return event.get('recording_duration') or 'Available anytime'
    start_text = start_dt.strftime('%I:%M %p').lstrip('0')
    if end_dt:
        end_text = end_dt.strftime('%I:%M %p').lstrip('0')
        return f"{start_text} - {end_text} {event.get('timezone') or ''}".strip()
    return f"{start_text} {event.get('timezone') or ''}".strip()

def event_public_url(event):
    slug = event['slug'] if isinstance(event, sqlite3.Row) else event.get('slug')
    content_type = event['content_type'] if isinstance(event, sqlite3.Row) else event.get('content_type')
    webinar_format = event['webinar_format'] if isinstance(event, sqlite3.Row) else event.get('webinar_format')
    lifecycle = event['lifecycle_status'] if isinstance(event, sqlite3.Row) else event.get('lifecycle_status')
    if content_type == 'Webinar':
        if webinar_format == 'On-Demand Webinar' or lifecycle == 'On-Demand':
            return f"/events/webinars/on-demand/{slug}"
        return f"/events/webinars/{slug}"
    return f"/events/{slug}"

def plain_text(value):
    value = re.sub(r'<[^>]+>', ' ', value or '')
    return re.sub(r'\s+', ' ', value).strip()

def is_valid_event_url(value):
    value = (value or '').strip()
    if not value:
        return True
    from urllib.parse import urlparse
    parsed = urlparse(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def log_event_activity(conn, event_id, action_type, description, previous_status=None, new_status=None, metadata_dict=None):
    conn.execute('''
        INSERT INTO event_activity_log (
            event_id, action_type, description, previous_status, new_status,
            performed_by, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_id,
        action_type,
        description,
        previous_status,
        new_status,
        session.get('username', 'Admin'),
        json.dumps(metadata_dict or {}),
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    ))

def run_event_status_update(conn=None):
    owns_conn = conn is None
    if owns_conn:
        ensure_event_webinar_schema()
    if owns_conn:
        conn = get_db_connection()
    updated = 0
    try:
        rows = conn.execute('''
            SELECT * FROM event_webinars
            WHERE publishing_status != 'Archived'
              AND lifecycle_status IN ('Upcoming', 'Live')
        ''').fetchall()
        now = datetime.utcnow()
        for row in rows:
            event = dict(row)
            end_dt = parse_event_datetime(event.get('end_datetime')) or parse_event_datetime(event.get('start_datetime'))
            if not end_dt or end_dt > now:
                continue

            if event.get('content_type') == 'Webinar' and event.get('webinar_format') == 'Live Webinar':
                if event.get('auto_convert_to_ondemand') and event.get('recording_link'):
                    conn.execute('''
                        UPDATE event_webinars
                        SET webinar_format = 'On-Demand Webinar',
                            lifecycle_status = 'On-Demand',
                            live_join_link = '',
                            registration_cta_text = COALESCE(NULLIF(registration_cta_text, ''), 'Watch On-Demand'),
                            converted_to_ondemand_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    ''', (now.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S'), event['id']))
                    log_event_activity(conn, event['id'], 'auto_convert_to_ondemand', 'Auto-converted webinar to on-demand after scheduled end time.', event.get('lifecycle_status'), 'On-Demand')
                else:
                    conn.execute('''
                        UPDATE event_webinars
                        SET lifecycle_status = 'Completed', updated_at = ?
                        WHERE id = ?
                    ''', (now.strftime('%Y-%m-%d %H:%M:%S'), event['id']))
                    log_event_activity(conn, event['id'], 'status_update', 'Marked live webinar completed. Recording link is required for on-demand conversion.', event.get('lifecycle_status'), 'Completed')
                updated += 1
            elif event.get('content_type') == 'Event':
                conn.execute('''
                    UPDATE event_webinars
                    SET lifecycle_status = 'Completed', updated_at = ?
                    WHERE id = ?
                ''', (now.strftime('%Y-%m-%d %H:%M:%S'), event['id']))
                log_event_activity(conn, event['id'], 'status_update', 'Marked event completed after scheduled end time.', event.get('lifecycle_status'), 'Completed')
                updated += 1
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()
    return updated

def get_event_listing_cards(public_only=True, limit=None, filters=None):
    ensure_event_webinar_schema()
    run_event_status_update()
    filters = filters or {}
    clauses = []
    params = []
    if public_only:
        clauses.append("publishing_status = 'Published'")
        clauses.append("lifecycle_status != 'Cancelled'")
    if filters.get('content_type'):
        clauses.append("content_type = ?")
        params.append(filters['content_type'])
    if filters.get('webinar_format'):
        clauses.append("webinar_format = ?")
        params.append(filters['webinar_format'])
    if filters.get('event_format'):
        clauses.append("event_format = ?")
        params.append(filters['event_format'])
    if filters.get('lifecycle_status'):
        clauses.append("lifecycle_status = ?")
        params.append(filters['lifecycle_status'])
    if filters.get('publishing_status'):
        clauses.append("publishing_status = ?")
        params.append(filters['publishing_status'])
    if filters.get('theme'):
        clauses.append("theme LIKE ?")
        params.append(f"%{filters['theme']}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    limit_sql = 'LIMIT ?' if limit else ''
    if limit:
        params.append(limit)

    conn = get_db_connection()
    try:
        rows = conn.execute(f'''
            SELECT ew.*,
                   (SELECT COUNT(*) FROM event_registrations er WHERE er.event_id = ew.id) as registration_count,
                   (SELECT COUNT(*) FROM event_speakers es WHERE es.event_id = ew.id AND es.is_active = 1) as speaker_count
            FROM event_webinars ew
            {where_sql}
            ORDER BY
                CASE WHEN start_datetime IS NULL OR start_datetime = '' THEN 1 ELSE 0 END,
                start_datetime ASC,
                updated_at DESC
            {limit_sql}
        ''', params).fetchall()
    finally:
        conn.close()

    cards = []
    for idx, row in enumerate(rows):
        event = dict(row)
        cards.append({
            'id': event['id'],
            'type': event.get('content_type') or 'Event',
            'format': event.get('webinar_format') or event.get('event_format') or '',
            'slug': event.get('slug'),
            'title': event.get('title'),
            'summary': event.get('short_description') or plain_text(event.get('full_description'))[:180],
            'date_str': 'On-Demand' if event.get('lifecycle_status') == 'On-Demand' else format_event_short_date(event.get('start_datetime'), 'Date TBD'),
            'time': event.get('recording_duration') if event.get('lifecycle_status') == 'On-Demand' else format_event_time_range(event),
            'delivery_type': event.get('location_type') or 'Online',
            'location': event.get('location') or ('Online' if event.get('content_type') == 'Webinar' else 'Location TBD'),
            'theme': event.get('theme') or '',
            'url': event_public_url(event),
            'card_image': event.get('featured_image') or event.get('hero_image') or EVENT_CARD_IMAGES[idx % len(EVENT_CARD_IMAGES)],
            'lifecycle_status': event.get('lifecycle_status'),
            'publishing_status': event.get('publishing_status'),
            'registration_count': event.get('registration_count') or 0,
            'speaker_count': event.get('speaker_count') or 0,
            'recording_ready': bool(event.get('recording_link'))
        })
    return cards

def fetch_event_webinar(event_id=None, slug=None):
    ensure_event_webinar_schema()
    conn = get_db_connection()
    try:
        if event_id is not None:
            row = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM event_webinars WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def fetch_event_bundle(event_id=None, slug=None, public_only=False):
    ensure_event_webinar_schema()
    conn = get_db_connection()
    try:
        if event_id is not None:
            row = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM event_webinars WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        event = dict(row)
        if public_only and event.get('publishing_status') != 'Published':
            return None
        event['speakers'] = [dict(r) for r in conn.execute(
            "SELECT * FROM event_speakers WHERE event_id = ? AND is_active = 1 ORDER BY display_order ASC, id ASC",
            (event['id'],)
        ).fetchall()]
        event['agenda_items'] = [dict(r) for r in conn.execute(
            "SELECT * FROM event_agenda_items WHERE event_id = ? ORDER BY day_number ASC, display_order ASC, start_time ASC, id ASC",
            (event['id'],)
        ).fetchall()]
        event['takeaways'] = [dict(r) for r in conn.execute(
            "SELECT * FROM event_key_takeaways WHERE event_id = ? ORDER BY display_order ASC, id ASC",
            (event['id'],)
        ).fetchall()]
        event['registration_count'] = conn.execute(
            "SELECT COUNT(*) as cnt FROM event_registrations WHERE event_id = ?",
            (event['id'],)
        ).fetchone()['cnt']
        return event
    finally:
        conn.close()

def build_event_detail_data(event):
    speakers = []
    accent_cycle = ['cyan', 'yellow', 'orange', 'violet']
    for idx, speaker in enumerate(event.get('speakers', [])):
        speakers.append({
            'name': speaker.get('name'),
            'role': speaker.get('designation') or '',
            'company': speaker.get('company') or '',
            'bio': speaker.get('short_bio') or '',
            'full_bio': speaker.get('full_bio') or '',
            'linkedin_url': speaker.get('linkedin_url') or '',
            'profile_url': speaker.get('profile_url') or '',
            'image_url': speaker.get('image_path') or '/static/img/event_2.png',
            'accent_class': accent_cycle[idx % len(accent_cycle)]
        })

    grouped = {}
    for item in event.get('agenda_items', []):
        day_num = item.get('day_number') or 1
        grouped.setdefault(day_num, []).append({
            'time_range': f"{item.get('start_time') or ''}{' - ' if item.get('end_time') else ''}{item.get('end_time') or ''}".strip(),
            'title': item.get('session_title'),
            'description': item.get('description') or '',
            'track': item.get('track') or ''
        })

    start_dt = parse_event_datetime(event.get('start_datetime'))
    agenda_days = []
    for day_num in sorted(grouped.keys()):
        day_date = ''
        if start_dt:
            day_date = (start_dt + timedelta(days=day_num - 1)).strftime('%b %d, %Y').replace(' 0', ' ')
        agenda_days.append({
            'label': f"Day {day_num:02d}",
            'date_str': day_date,
            'sessions': grouped[day_num]
        })

    is_on_demand = event.get('content_type') == 'Webinar' and (
        event.get('webinar_format') == 'On-Demand Webinar' or event.get('lifecycle_status') == 'On-Demand'
    )
    is_in_person = event.get('content_type') == 'Event' and event.get('location_type') in ('In-Person', 'Hybrid')
    label = event.get('event_label') or event.get('webinar_format') or event.get('event_format') or event.get('content_type')
    summary = event.get('short_description') or plain_text(event.get('full_description'))[:220]
    detail_text = plain_text(event.get('full_description'))
    date_label = 'Originally aired on ' + format_event_date(event.get('start_datetime')) if is_on_demand and event.get('start_datetime') else format_event_date(event.get('start_datetime'))

    return {
        'id': event.get('id'),
        'title': event.get('title'),
        'summary': summary,
        'description': detail_text,
        'date': date_label,
        'timezone_date': 'On-Demand' if is_on_demand else format_event_short_date(event.get('start_datetime'), 'Date TBD'),
        'timezone_times': event.get('recording_duration') if is_on_demand else format_event_time_range(event),
        'display_time_text': format_event_time_range(event),
        'location': event.get('location') or ('Online' if event.get('content_type') == 'Webinar' else 'Location TBD'),
        'is_in_person': is_in_person,
        'countdown_enabled': bool(event.get('countdown_enabled')) and not is_on_demand,
        'event_label': label,
        'event_tagline': event.get('theme') or 'Artha Solutions Event',
        'speakers': speakers,
        'agenda_days': agenda_days,
        'takeaways': [t.get('takeaway_text') for t in event.get('takeaways', [])],
        'highlight_title': event.get('highlight_title') or event.get('theme') or event.get('topic_category') or event.get('title'),
        'highlight_text': event.get('highlight_text') or detail_text or summary,
        'highlight_link': event.get('highlight_link') or event.get('related_solution_url') or event.get('related_industry_url') or '/solutions',
        'registration_form_title': event.get('registration_form_title') or ('Access On-Demand Webinar' if is_on_demand else f"Register for {event.get('content_type')}"),
        'registration_cta_text': event.get('registration_cta_text') or ('Watch On-Demand' if is_on_demand else 'Register Now'),
        'registration_endpoint': f"/api/events/{event.get('slug')}/register",
        'thank_you_message': event.get('thank_you_message') or 'Thank you. Your registration has been received.',
        'seo_title': event.get('seo_title') or event.get('title'),
        'seo_description': event.get('seo_description') or summary,
        'canonical_url': event.get('canonical_url') or event_public_url(event),
        'og_title': event.get('og_title') or event.get('seo_title') or event.get('title'),
        'og_description': event.get('og_description') or event.get('seo_description') or summary,
        'og_image': event.get('og_image') or event.get('featured_image') or event.get('hero_image'),
        'schema_json': event.get('schema_json') or '',
        'is_noindex': event.get('publishing_status') != 'Published',
        'recording_ready': bool(event.get('recording_link')),
        'is_on_demand': is_on_demand
    }

def build_event_form_context(event=None):
    event = dict(event or {})
    start_date, start_time = split_event_datetime(event.get('start_datetime'))
    end_date, end_time = split_event_datetime(event.get('end_datetime'))
    close_date, close_time = split_event_datetime(event.get('registration_close_datetime'))
    event['start_date'] = start_date
    event['start_time'] = start_time
    event['end_date'] = end_date
    event['end_time'] = end_time
    event['registration_close_date'] = close_date
    event['registration_close_time'] = close_time
    event.setdefault('content_type', 'Webinar')
    event.setdefault('webinar_format', 'Live Webinar')
    event.setdefault('event_format', 'Conference')
    event.setdefault('publishing_status', 'Draft')
    event.setdefault('lifecycle_status', 'Upcoming')
    event.setdefault('location_type', 'Online')
    event.setdefault('recording_access_type', 'redirect')
    event.setdefault('registration_required', 1)
    event.setdefault('countdown_enabled', 1)
    event.setdefault('business_email_only', 1)
    event.setdefault('crm_integration_enabled', 1)
    return event

def save_event_image_upload(field_name, category, slug_hint='', errors=None):
    uploaded_file = request.files.get(field_name)
    if not uploaded_file or not uploaded_file.filename:
        return ''

    original_name = secure_filename(uploaded_file.filename)
    _, ext = os.path.splitext(original_name)
    ext = ext.lower()
    if ext not in EVENT_ALLOWED_IMAGE_EXTENSIONS:
        if errors is not None:
            errors.append(f"{original_name} is not a supported image file. Use JPG, PNG, WebP, GIF, or SVG.")
        return ''

    category = secure_filename(category or 'general') or 'general'
    slug_hint = secure_filename(slug_hint or 'event') or 'event'
    upload_dir = os.path.join(EVENT_IMAGE_UPLOAD_ROOT, category)
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    filename = f"{slug_hint}-{field_name}-{timestamp}{ext}"
    save_path = os.path.join(upload_dir, filename)
    uploaded_file.save(save_path)
    return f"{EVENT_IMAGE_UPLOAD_URL_ROOT}/{category}/{filename}"

def validate_event_speaker_image_uploads(errors):
    for speaker_upload_key in request.form.getlist('speaker_upload_key'):
        uploaded_file = request.files.get(f"speaker_image_upload_{speaker_upload_key}")
        if not uploaded_file or not uploaded_file.filename:
            continue
        original_name = secure_filename(uploaded_file.filename)
        _, ext = os.path.splitext(original_name)
        if ext.lower() not in EVENT_ALLOWED_IMAGE_EXTENSIONS:
            errors.append(f"{original_name} is not a supported speaker image. Use JPG, PNG, WebP, GIF, or SVG.")

def save_event_children(conn, event_id, event_slug='', upload_errors=None):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("DELETE FROM event_speakers WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM event_agenda_items WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM event_key_takeaways WHERE event_id = ?", (event_id,))

    speaker_names = request.form.getlist('speaker_name')
    speaker_designations = request.form.getlist('speaker_designation')
    speaker_companies = request.form.getlist('speaker_company')
    speaker_images = request.form.getlist('speaker_image_path')
    speaker_upload_keys = request.form.getlist('speaker_upload_key')
    speaker_alts = request.form.getlist('speaker_image_alt_text')
    speaker_short_bios = request.form.getlist('speaker_short_bio')
    speaker_full_bios = request.form.getlist('speaker_full_bio')
    speaker_linkedins = request.form.getlist('speaker_linkedin_url')
    speaker_profiles = request.form.getlist('speaker_profile_url')
    for idx, name in enumerate(speaker_names):
        name = (name or '').strip()
        if not name:
            continue
        speaker_image_path = speaker_images[idx].strip() if idx < len(speaker_images) else ''
        speaker_upload_key = speaker_upload_keys[idx] if idx < len(speaker_upload_keys) else ''
        if speaker_upload_key:
            uploaded_path = save_event_image_upload(
                f"speaker_image_upload_{speaker_upload_key}",
                'speakers',
                event_slug or name,
                upload_errors
            )
            if uploaded_path:
                speaker_image_path = uploaded_path
        conn.execute('''
            INSERT INTO event_speakers (
                event_id, name, designation, company, image_path, image_alt_text,
                short_bio, full_bio, linkedin_url, profile_url, display_order,
                is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (
            event_id, name,
            speaker_designations[idx].strip() if idx < len(speaker_designations) else '',
            speaker_companies[idx].strip() if idx < len(speaker_companies) else '',
            speaker_image_path,
            speaker_alts[idx].strip() if idx < len(speaker_alts) else name,
            speaker_short_bios[idx].strip() if idx < len(speaker_short_bios) else '',
            speaker_full_bios[idx].strip() if idx < len(speaker_full_bios) else '',
            speaker_linkedins[idx].strip() if idx < len(speaker_linkedins) else '',
            speaker_profiles[idx].strip() if idx < len(speaker_profiles) else '',
            idx,
            now_str,
            now_str
        ))

    agenda_titles = request.form.getlist('agenda_session_title')
    agenda_days = request.form.getlist('agenda_day_number')
    agenda_starts = request.form.getlist('agenda_start_time')
    agenda_ends = request.form.getlist('agenda_end_time')
    agenda_tracks = request.form.getlist('agenda_track')
    agenda_descs = request.form.getlist('agenda_description')
    for idx, title in enumerate(agenda_titles):
        title = (title or '').strip()
        if not title:
            continue
        try:
            day_number = int(agenda_days[idx]) if idx < len(agenda_days) and agenda_days[idx] else 1
        except ValueError:
            day_number = 1
        conn.execute('''
            INSERT INTO event_agenda_items (
                event_id, day_number, session_title, start_time, end_time,
                track, description, display_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_id,
            day_number,
            title,
            agenda_starts[idx].strip() if idx < len(agenda_starts) else '',
            agenda_ends[idx].strip() if idx < len(agenda_ends) else '',
            agenda_tracks[idx].strip() if idx < len(agenda_tracks) else '',
            agenda_descs[idx].strip() if idx < len(agenda_descs) else '',
            idx,
            now_str,
            now_str
        ))

    takeaways = request.form.getlist('takeaway_text')
    for idx, takeaway in enumerate(takeaways):
        takeaway = (takeaway or '').strip()
        if not takeaway:
            continue
        conn.execute('''
            INSERT INTO event_key_takeaways (event_id, takeaway_text, display_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, takeaway, idx, now_str, now_str))

def get_event_payload_from_form(existing=None, upload_errors=None):
    existing = existing or {}
    content_type = request.form.get('content_type', 'Webinar')
    webinar_format = request.form.get('webinar_format') if content_type == 'Webinar' else ''
    event_format = request.form.get('event_format') if content_type == 'Event' else ''
    lifecycle_status = request.form.get('lifecycle_status') or ('On-Demand' if webinar_format == 'On-Demand Webinar' else 'Upcoming')
    title = request.form.get('title', '').strip()
    slug = slugify_value(request.form.get('slug') or title)
    start_datetime = build_event_datetime(request.form.get('start_date'), request.form.get('start_time'), '09:00')
    end_datetime = build_event_datetime(request.form.get('end_date') or request.form.get('start_date'), request.form.get('end_time'), '10:00')
    recording_link = request.form.get('recording_link', '').strip()

    if content_type == 'Webinar' and webinar_format == 'On-Demand Webinar':
        lifecycle_status = 'On-Demand'

    def image_value(field_name, category):
        uploaded_path = save_event_image_upload(f"{field_name}_upload", category, slug or title, upload_errors)
        return uploaded_path or request.form.get(field_name, '').strip()

    return {
        'content_type': content_type,
        'webinar_format': webinar_format,
        'event_format': event_format,
        'title': title,
        'slug': slug,
        'short_description': request.form.get('short_description', '').strip(),
        'full_description': request.form.get('full_description', '').strip(),
        'theme': request.form.get('theme', '').strip(),
        'topic_category': request.form.get('topic_category', '').strip(),
        'start_datetime': start_datetime,
        'end_datetime': end_datetime,
        'timezone': request.form.get('timezone', '').strip() or 'America/New_York',
        'display_time_text': request.form.get('display_time_text', '').strip(),
        'location_type': request.form.get('location_type', '').strip() or 'Online',
        'location': request.form.get('location', '').strip(),
        'event_link': request.form.get('event_link', '').strip(),
        'live_join_link': '' if lifecycle_status == 'On-Demand' else request.form.get('live_join_link', '').strip(),
        'recording_link': recording_link,
        'recording_duration': request.form.get('recording_duration', '').strip(),
        'recording_embed_code': request.form.get('recording_embed_code', '').strip(),
        'recording_access_type': request.form.get('recording_access_type', 'redirect'),
        'registration_required': 1 if request.form.get('registration_required') == '1' else 0,
        'registration_form_title': request.form.get('registration_form_title', '').strip(),
        'registration_cta_text': request.form.get('registration_cta_text', '').strip(),
        'thank_you_message': request.form.get('thank_you_message', '').strip(),
        'countdown_enabled': 1 if request.form.get('countdown_enabled') == '1' else 0,
        'capacity': int(request.form.get('capacity') or 0) or None,
        'registration_close_datetime': build_event_datetime(request.form.get('registration_close_date'), request.form.get('registration_close_time'), ''),
        'lifecycle_status': lifecycle_status,
        'publishing_status': request.form.get('publishing_status', 'Draft'),
        'auto_convert_to_ondemand': 1 if request.form.get('auto_convert_to_ondemand') == '1' else 0,
        'hero_image': image_value('hero_image', 'hero'),
        'featured_image': image_value('featured_image', 'featured'),
        'partner_logo': image_value('partner_logo', 'logos'),
        'sponsor_logo': image_value('sponsor_logo', 'logos'),
        'related_solution_url': request.form.get('related_solution_url', '').strip(),
        'related_industry_url': request.form.get('related_industry_url', '').strip(),
        'related_case_study_id': int(request.form.get('related_case_study_id') or 0) or None,
        'seo_title': request.form.get('seo_title', '').strip(),
        'seo_description': request.form.get('seo_description', '').strip(),
        'canonical_url': request.form.get('canonical_url', '').strip(),
        'og_title': request.form.get('og_title', '').strip(),
        'og_description': request.form.get('og_description', '').strip(),
        'og_image': image_value('og_image', 'og'),
        'ai_summary': request.form.get('ai_summary', '').strip(),
        'schema_json': request.form.get('schema_json', '').strip(),
        'event_label': request.form.get('event_label', '').strip(),
        'tags': request.form.get('tags', '').strip(),
        'who_should_attend': request.form.get('who_should_attend', '').strip(),
        'why_attend': request.form.get('why_attend', '').strip(),
        'highlight_title': request.form.get('highlight_title', '').strip(),
        'highlight_text': request.form.get('highlight_text', '').strip(),
        'highlight_link': request.form.get('highlight_link', '').strip(),
        'custom_cta_text': request.form.get('custom_cta_text', '').strip(),
        'custom_cta_url': request.form.get('custom_cta_url', '').strip(),
        'resource_download_url': request.form.get('resource_download_url', '').strip(),
        'calendar_details': request.form.get('calendar_details', '').strip(),
        'business_email_only': 1 if request.form.get('business_email_only') == '1' else 0,
        'crm_integration_enabled': 1 if request.form.get('crm_integration_enabled') == '1' else 0,
        'product_solution_id': int(request.form.get('product_solution_id') or 0) or None,
        'partner_id': int(request.form.get('partner_id') or 0) or None,
        'updated_by': session.get('username', 'Admin'),
        'updated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }

def validate_event_payload(payload, is_conversion=False):
    errors = []
    if not payload.get('title'):
        errors.append('Title is required.')
    if not payload.get('slug'):
        errors.append('Slug is required.')
    if not payload.get('short_description'):
        errors.append('Short description is required.')
    if not payload.get('theme'):
        errors.append('Theme is required.')
    if payload.get('content_type') == 'Webinar' and not payload.get('webinar_format'):
        errors.append('Webinar format is required.')
    if payload.get('content_type') == 'Event' and not payload.get('event_format'):
        errors.append('Event format is required.')
    if not payload.get('start_datetime') and payload.get('lifecycle_status') != 'On-Demand':
        errors.append('Date and start time are required.')
    if payload.get('content_type') == 'Webinar' and payload.get('lifecycle_status') == 'On-Demand' and not payload.get('recording_link'):
        errors.append('Recording link is required for on-demand webinars.')
    for field in ('recording_link', 'event_link', 'live_join_link', 'custom_cta_url', 'resource_download_url'):
        if payload.get(field) and not is_valid_event_url(payload[field]):
            errors.append(f"{field.replace('_', ' ').title()} must be a valid http(s) URL.")
    if payload.get('schema_json'):
        try:
            json.loads(payload['schema_json'])
        except Exception:
            errors.append('Schema JSON must be valid JSON.')
    return errors

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

    seo_page = None
    google_verification = ''
    bing_verification = ''
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (request.path,)).fetchone()
        if row:
            seo_page = dict(row)
        
        g_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'google_verification'").fetchone()
        if g_row:
            google_verification = g_row['value']
            
        b_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'bing_verification'").fetchone()
        if b_row:
            bing_verification = b_row['value']
            
        conn.close()
    except Exception as e:
        print(f"Error injecting SEO data: {e}")

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
        'navigation_menu': load_navigation_menu(),
        'seo_page_override': seo_page,
        'google_verification': google_verification,
        'bing_verification': bing_verification,
        'events_list': get_compiled_events()
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

# Serve uploaded files (whitepapers, case studies, blogs)
@app.route('/uploads/<path:filename>')
def download_file(filename):
    """Serve uploaded files from the uploads directory"""
    import os
    uploads_folder = os.path.join(os.path.dirname(__file__), 'uploads')
    file_path = os.path.join(uploads_folder, filename)
    
    # Security: ensure the file is within the uploads folder
    if not os.path.abspath(file_path).startswith(os.path.abspath(uploads_folder)):
        abort(403)
    
    if not os.path.exists(file_path):
        abort(404)
    
    # Get file extension
    _, ext = os.path.splitext(file_path)
    ext_lower = ext.lower()
    
    # Determine if it's a download or inline view
    is_pdf = ext_lower == '.pdf'
    
    # For PDFs, allow viewing inline; for other files, force download
    return send_file(file_path, as_attachment=not is_pdf)

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
            'url': f'/event-view/{slug}',
            'card_image': item.get('card_image')
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
            'url': f'/webinar-view/{slug}',
            'card_image': item.get('card_image')
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

def generate_expiring_resume_url(app_id):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(app.config.get('SECRET_KEY', 'default_careers_secret_key_2026'))
    token = serializer.dumps({'app_id': app_id}, salt='careers-resume-download')
    try:
        from flask import has_request_context
        if has_request_context():
            host_url = request.host_url
        else:
            host_url = 'http://127.0.0.1:5050/'
    except Exception:
        host_url = 'http://127.0.0.1:5050/'
    host_url = host_url.rstrip('/')
    return f"{host_url}/api/admin/careers/applications/download/{token}"

def format_email_body(poster_name, app_data, download_url=None):
    cover_letter = app_data.get('cover_letter') or 'Not provided'
    job_title = app_data.get('job_title') or 'N/A'
    job_location = app_data.get('job_location') or 'N/A'
    job_id = app_data.get('job_id') or 'N/A'
    job_dept = app_data.get('job_dept') or 'N/A'
    job_type = app_data.get('job_type') or 'N/A'
    
    try:
        from flask import has_request_context
        if has_request_context():
            host_url = request.host_url
        else:
            host_url = 'http://127.0.0.1:5050/'
    except Exception:
        host_url = 'http://127.0.0.1:5050/'
    admin_url = f"{host_url.rstrip('/')}/admin/careers/applications?open_notif={app_data['id']}"

    if download_url:
        resume_section = f"The candidate's resume/CV could not be attached due to size limits. You can download it securely using this expiring link (valid for 24 hours):\n{download_url}"
    else:
        resume_section = "The candidate’s resume/CV is attached to this email."

    body = f"""Hello {poster_name or 'Job Poster'},

A new candidate has applied for the following position:

Job: {job_title}
Location: {job_location}
Job Reference: {job_id}

Candidate Details:
Name: {app_data['full_name']}
Email: {app_data['email']}
Phone: {app_data['phone'] or 'Not provided'}
Current Location: Not provided
Experience: Not provided
Current Company: Not provided
Notice Period: Not provided
LinkedIn: {app_data['linkedin_url'] or 'Not provided'}

Cover Letter:
{cover_letter}

{resume_section}

View Application:
{admin_url}

Regards,
Artha Solutions Careers Portal"""
    return body

def update_application_notification_status(app_id, status, error_msg, recipient, cc):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT notification_attempt_count FROM career_applications WHERE id = ?", (app_id,)).fetchone()
        attempts = row[0] if row else 0
        new_attempts = attempts + 1
        
        final_status = status
        if status == 'Failed' and new_attempts < 3:
            final_status = 'Retrying'
            
        conn.execute("""
            UPDATE career_applications
            SET notification_status = ?,
                notification_error = ?,
                notification_attempt_count = ?,
                last_notification_attempt_at = ?,
                notification_sent_at = ?
            WHERE id = ?
        """, (
            final_status, error_msg, new_attempts, now_str,
            (now_str if status == 'Sent' else None),
            app_id
        ))
        conn.commit()
    except Exception as e:
        print(f"Error updating application notification status: {e}")
    finally:
        conn.close()

def _log_notification_attempt(conn, app_id, job_id, recipient, cc, subject, status, attachment_name, error_message, triggered_by):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""
        INSERT INTO job_application_notification_logs
        (job_application_id, job_id, recipient, cc, subject, status, attachment_name, attempted_at, sent_at, error_message, triggered_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app_id, job_id, recipient, cc, subject, status, attachment_name,
        now_str, (now_str if status == 'Sent' else None),
        error_message, triggered_by
    ))

def send_career_application_notification(app_id, recipient_override=None, cc_override=None, triggered_by='System'):
    import os
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    from crm.utils import decrypt_smtp_password

    conn = get_db_connection()
    try:
        app_row = conn.execute("""
            SELECT a.*, 
                   j.id as job_id_ref, j.title as job_title, j.location as job_location, j.posted_date, j.job_type, j.department as job_dept,
                   j.job_poster_name, j.job_poster_email, j.secondary_notification_email, j.notification_cc,
                   j.application_notification_enabled
            FROM career_applications a
            LEFT JOIN career_jobs j ON a.job_id = j.id
            WHERE a.id = ?
        """, (app_id,)).fetchone()

        if not app_row:
            return False, "Application not found."
            
        app_data = dict(app_row)
        
        if triggered_by == 'System' and not app_data.get('application_notification_enabled', 1):
            return True, "Notification disabled for this job."

        if recipient_override:
            recipient_val = recipient_override
            cc_val = cc_override
        else:
            recipient_val = app_data.get('notification_recipient')
            cc_val = app_data.get('notification_cc')
            
            if not recipient_val:
                recipients = []
                if app_data.get('job_poster_email'):
                    recipients.append(app_data['job_poster_email'].strip())
                if app_data.get('secondary_notification_email'):
                    recipients.append(app_data['secondary_notification_email'].strip())
                recipient_val = ",".join(recipients) if recipients else None
                cc_val = app_data.get('notification_cc') or None
                
                conn.execute("""
                    UPDATE career_applications 
                    SET notification_recipient = ?, notification_cc = ?
                    WHERE id = ?
                """, (recipient_val, cc_val, app_id))
                conn.commit()
                app_data['notification_recipient'] = recipient_val
                app_data['notification_cc'] = cc_val

        if not recipient_val:
            error_msg = "No recipient email configured for job poster."
            update_application_notification_status(app_id, 'Failed', error_msg, recipient_val, cc_val)
            _log_notification_attempt(conn, app_id, app_data['job_id'], recipient_val, cc_val, "", "Failed", None, error_msg, triggered_by)
            conn.commit()
            return False, error_msg

        settings_row = conn.execute("SELECT * FROM crm_settings LIMIT 1").fetchone()
        if not settings_row:
            error_msg = "SMTP settings missing in database."
            update_application_notification_status(app_id, 'Failed', error_msg, recipient_val, cc_val)
            _log_notification_attempt(conn, app_id, app_data['job_id'], recipient_val, cc_val, "", "Failed", None, error_msg, triggered_by)
            conn.commit()
            return False, error_msg

        settings = dict(settings_row)
        smtp_host = settings.get('smtp_host')
        smtp_port = settings.get('smtp_port') or 587
        smtp_username = settings.get('smtp_username')
        from_email = settings.get('from_email') or smtp_username
        smtp_password = decrypt_smtp_password(settings.get('smtp_password_encrypted', ''))

        if not smtp_host:
            error_msg = "SMTP host not configured."
            update_application_notification_status(app_id, 'Failed', error_msg, recipient_val, cc_val)
            _log_notification_attempt(conn, app_id, app_data['job_id'], recipient_val, cc_val, "", "Failed", None, error_msg, triggered_by)
            conn.commit()
            return False, error_msg

        job_title = app_data.get('job_title') or 'N/A'
        job_location = app_data.get('job_location') or 'N/A'
        subject = f"New Application: {app_data['full_name']} – {job_title} – {job_location}"

        resume_path = app_data.get('resume_path')
        resume_filename = app_data.get('resume_filename')
        original_name = None
        if resume_filename:
            parts = resume_filename.split('_', 2)
            original_name = parts[2] if len(parts) > 2 else resume_filename

        file_size = 0
        if resume_path and os.path.exists(resume_path):
            file_size = os.path.getsize(resume_path)

        download_url = None
        resume_attached = True
        if file_size > 3.5 * 1024 * 1024:
            resume_attached = False
            download_url = generate_expiring_resume_url(app_id)

        def try_smtp_send(attach_file, url_link):
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = recipient_val
            if cc_val:
                msg['Cc'] = cc_val
            msg['Subject'] = subject

            body = format_email_body(app_data.get('job_poster_name'), app_data, url_link)
            msg.attach(MIMEText(body, 'plain'))

            if attach_file and resume_path and os.path.exists(resume_path):
                with open(resume_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=original_name)
                part['Content-Disposition'] = f'attachment; filename="{original_name}"'
                msg.attach(part)

            recipients = [e.strip() for e in recipient_val.split(',') if e.strip()]
            if cc_val:
                recipients.extend([e.strip() for e in cc_val.split(',') if e.strip()])

            if int(smtp_port) == 465:
                server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=10)
                server.starttls()

            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)

            server.sendmail(from_email, recipients, msg.as_string())
            server.quit()

        try:
            try_smtp_send(resume_attached, download_url)
            status = 'Sent'
            err_details = None
        except Exception as smtp_err:
            smtp_err_str = str(smtp_err)
            if resume_attached and ("size" in smtp_err_str.lower() or "limit" in smtp_err_str.lower() or "552" in smtp_err_str):
                try:
                    download_url = generate_expiring_resume_url(app_id)
                    try_smtp_send(False, download_url)
                    status = 'Sent'
                    err_details = f"Sent with link fallback. Original error: {smtp_err_str}"
                except Exception as retry_err:
                    status = 'Failed'
                    err_details = f"Failed on fallback retry: {retry_err}"
            else:
                status = 'Failed'
                err_details = smtp_err_str

        update_application_notification_status(app_id, status, err_details, recipient_val, cc_val)
        _log_notification_attempt(
            conn, app_id, app_data['job_id'], recipient_val, cc_val, subject, status,
            (original_name if (status == 'Sent' and not download_url) else None),
            err_details, triggered_by
        )
        conn.commit()

        if status == 'Sent':
            return True, None
        else:
            return False, err_details

    except Exception as outer_err:
        print(f"Exception in send_career_application_notification: {outer_err}")
        return False, str(outer_err)
    finally:
        conn.close()

SCHEDULER_STARTED = False

def init_notification_scheduler(app_instance):
    global SCHEDULER_STARTED
    if SCHEDULER_STARTED:
        return
    SCHEDULER_STARTED = True
    
    import time
    import threading
    
    def retry_loop():
        time.sleep(15)
        while True:
            try:
                with app_instance.app_context():
                    conn = get_db_connection()
                    rows = conn.execute("""
                        SELECT id, last_notification_attempt_at FROM career_applications
                        WHERE (notification_status = 'Pending' OR notification_status = 'Retrying')
                          AND notification_attempt_count < 3
                    """).fetchall()
                    
                    for row in rows:
                        app_id = row['id']
                        last_attempt = row['last_notification_attempt_at']
                        should_retry = False
                        if not last_attempt:
                            should_retry = True
                        else:
                            try:
                                attempt_dt = datetime.strptime(last_attempt, '%Y-%m-%d %H:%M:%S')
                                elapsed = (datetime.now() - attempt_dt).total_seconds()
                                if elapsed >= 300:
                                    should_retry = True
                            except Exception:
                                should_retry = True
                                
                        if should_retry:
                            print(f"Scheduler: Retrying notification for application #{app_id}...")
                            send_career_application_notification(app_id, triggered_by='System')
                    conn.close()
            except Exception as loop_err:
                print(f"Error in scheduler retry loop: {loop_err}")
            time.sleep(60)

    t = threading.Thread(target=retry_loop, daemon=True)
    t.start()

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
    if phone and not validate_phone_number(phone):
        errors.append('Invalid phone number format or test number detected.')
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
            
            # Content signature scan / magic bytes check
            is_valid_file = True
            ext = resume_file.filename.rsplit('.', 1)[1].lower() if '.' in resume_file.filename else ''
            
            if not content or len(content) == 0:
                errors.append('Uploaded resume file is empty.')
                is_valid_file = False
            elif ext == 'pdf' and not content.startswith(b'%PDF'):
                errors.append('Invalid PDF file structure.')
                is_valid_file = False
            elif ext == 'docx' and not content.startswith(b'PK\x03\x04'):
                errors.append('Invalid DOCX file structure.')
                is_valid_file = False
            elif ext == 'doc' and not content.startswith(b'\xd0\xcf\x11\xe0') and not content.startswith(b'PK\x03\x04'):
                errors.append('Invalid DOC file structure.')
                is_valid_file = False
                
            if is_valid_file:
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
    # Resolve locked notification recipients for the application
    recipients = []
    if job.get('job_poster_email'):
        recipients.append(job['job_poster_email'].strip())
    if job.get('secondary_notification_email'):
        recipients.append(job['secondary_notification_email'].strip())
    app_recipient = ",".join(recipients) if recipients else None
    app_cc = job.get('notification_cc') or None

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO career_applications
        (job_id, job_title, full_name, email, phone, linkedin_url, cover_letter,
         resume_filename, resume_path, consent_given, status,
         notification_recipient, notification_cc, notification_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'new', ?, ?, 'Pending')
    """, (job['id'], job['title'], full_name, email, phone, linkedin_url, cover_letter,
          resume_filename, resume_path, app_recipient, app_cc))
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Trigger email notification asynchronously in a background thread
    import threading
    threading.Thread(
        target=send_career_application_notification,
        args=(app_id,),
        kwargs={'triggered_by': 'System'},
        daemon=True
    ).start()

    # Split name for CRM
    name_parts = (full_name or "").strip().split(' ', 1)
    c_first_name = name_parts[0]
    c_last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    # Forward to CRM (conditional settings check is inside wrapper)
    forward_to_crm_wrapper(
        email=email, first_name=c_first_name, last_name=c_last_name, company='', phone=phone, job_title=job['title'],
        geography='', country='', industry='', message=f"Applied for {job['title']}\nLinkedIn: {linkedin_url}\nCover Letter: {cover_letter}",
        source_form=f"Career Job Application - {job['title']}",
        source_page=f"/careers/{slug}", cta_clicked='Submit Application', lead_source='Careers Website',
        utm_source='', utm_medium='', utm_campaign='', utm_term='', utm_content='',
        referrer='', ip_address=request.remote_addr or 'unknown', user_agent=request.headers.get('User-Agent', ''), consent_status=1
    )

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

    conn_rec = get_db_connection()
    recruiters = [dict(r) for r in conn_rec.execute("SELECT id, name, email, department FROM crm_users WHERE is_active = 1").fetchall()]
    conn_rec.close()

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
                    description, responsibilities, requirements, additional_info, status, posted_date,
                    job_poster_name, job_poster_email, job_poster_phone, job_poster_department,
                    job_poster_user_id, secondary_notification_email, notification_cc, application_notification_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slug, request.form.get('title'), request.form.get('department'),
                request.form.get('location'), request.form.get('job_type', 'Full-Time'),
                request.form.get('summary'), request.form.get('description'),
                responsibilities, requirements, request.form.get('additional_info'),
                request.form.get('status', 'published'),
                request.form.get('posted_date', datetime.now().strftime('%Y-%m-%d')),
                request.form.get('job_poster_name'),
                request.form.get('job_poster_email'),
                request.form.get('job_poster_phone') or None,
                request.form.get('job_poster_department') or None,
                int(request.form.get('job_poster_user_id')) if request.form.get('job_poster_user_id') else None,
                request.form.get('secondary_notification_email') or None,
                request.form.get('notification_cc') or None,
                int(request.form.get('application_notification_enabled', 1))
            ))
            conn.commit()
        except Exception as e:
            conn.close()
            return render_template('admin_career_job_edit.html', job=None, recruiters=recruiters,
                                   error=str(e), active_admin='careers')
        conn.close()
        return redirect('/admin/careers')
    return render_template('admin_career_job_edit.html', job=None, recruiters=recruiters, active_admin='careers')

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

    conn_rec = get_db_connection()
    recruiters = [dict(r) for r in conn_rec.execute("SELECT id, name, email, department FROM crm_users WHERE is_active = 1").fetchall()]
    conn_rec.close()

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
            posted_date=?, job_poster_name=?, job_poster_email=?, job_poster_phone=?,
            job_poster_department=?, job_poster_user_id=?, secondary_notification_email=?,
            notification_cc=?, application_notification_enabled=?, updated_at=datetime('now')
            WHERE id=?
        """, (
            request.form.get('title'), request.form.get('department'),
            request.form.get('location'), request.form.get('job_type', 'Full-Time'),
            request.form.get('summary'), request.form.get('description'),
            responsibilities, requirements, request.form.get('additional_info'),
            request.form.get('status', 'published'),
            request.form.get('posted_date'),
            request.form.get('job_poster_name'),
            request.form.get('job_poster_email'),
            request.form.get('job_poster_phone') or None,
            request.form.get('job_poster_department') or None,
            int(request.form.get('job_poster_user_id')) if request.form.get('job_poster_user_id') else None,
            request.form.get('secondary_notification_email') or None,
            request.form.get('notification_cc') or None,
            int(request.form.get('application_notification_enabled', 1)),
            job_id
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
    return render_template('admin_career_job_edit.html', job=job, recruiters=recruiters, active_admin='careers')

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
    recruiters = conn.execute("SELECT id, name, email, department FROM crm_users WHERE is_active = 1").fetchall()
    conn.close()
    return render_template('admin_career_applications.html', applications=applications,
                           jobs=jobs, recruiters=[dict(r) for r in recruiters], job_filter=job_filter, status_filter=status_filter,
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

@app.route('/api/admin/careers/applications/<int:app_id>/notification-log')
def api_admin_career_notification_log(app_id):
    guard = _careers_admin_required()
    if guard:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    conn = get_db_connection()
    logs = conn.execute("""
        SELECT * FROM job_application_notification_logs
        WHERE job_application_id = ?
        ORDER BY id DESC
    """, (app_id,)).fetchall()
    conn.close()
    return jsonify({
        'status': 'success',
        'logs': [dict(log) for log in logs]
    })

@app.route('/api/admin/careers/applications/<int:app_id>/resend-notification', methods=['POST'])
def api_admin_career_resend_notification(app_id):
    guard = _careers_admin_required()
    if guard: return redirect('/admin/login')
    
    user_name = session.get('crm_user_name') or session.get('username') or 'Admin'
    success, err = send_career_application_notification(app_id, triggered_by=f"Admin: {user_name}")
    if success:
        flash("Application notification resent successfully.", "success")
    else:
        flash(f"Failed to resend notification: {err}", "error")
        
    return redirect('/admin/careers/applications')

@app.route('/api/admin/careers/applications/<int:app_id>/forward-to-recruiter', methods=['POST'])
def api_admin_career_forward_to_recruiter(app_id):
    guard = _careers_admin_required()
    if guard: return redirect('/admin/login')
    
    rec_id = request.form.get('recruiter_user_id')
    forward_email = request.form.get('forward_email', '').strip()
    
    target_email = None
    target_name = None
    
    if rec_id:
        conn = get_db_connection()
        user = conn.execute("SELECT name, email FROM crm_users WHERE id = ?", (rec_id,)).fetchone()
        conn.close()
        if user:
            target_email = user['email']
            target_name = user['name']
            
    if not target_email and forward_email:
        target_email = forward_email
        target_name = forward_email.split('@')[0]
        
    if not target_email:
        flash("Please select a recruiter or specify a valid email to forward.", "error")
        return redirect('/admin/careers/applications')
        
    user_name = session.get('crm_user_name') or session.get('username') or 'Admin'
    
    success, err = send_career_application_notification(
        app_id, 
        recipient_override=target_email, 
        triggered_by=f"Forwarded by {user_name} to {target_name}"
    )
    if success:
        flash(f"Application successfully forwarded to {target_name} ({target_email}).", "success")
    else:
        flash(f"Failed to forward application: {err}", "error")
        
    return redirect('/admin/careers/applications')

@app.route('/api/admin/careers/applications/download/<token>')
def api_admin_career_download_resume_by_token(token):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(app.config.get('SECRET_KEY', 'default_careers_secret_key_2026'))
    try:
        data = serializer.loads(token, salt='careers-resume-download', max_age=86400) # Valid for 24 hours
        app_id = data['app_id']
    except SignatureExpired:
        abort(403, description="This download link has expired.")
    except BadSignature:
        abort(403, description="Invalid download token.")

    conn = get_db_connection()
    app_row = conn.execute("SELECT * FROM career_applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    if not app_row or not app_row['resume_path']:
        abort(404)
        
    return send_file(app_row['resume_path'], as_attachment=True,
                     download_name=app_row['resume_filename'])

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
    return redirect('/events')

@app.route('/resources/webinars')
def resources_webinars():
    return redirect('/events?type=Webinar')

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

@app.route('/events')
def events_listing():
    filters = {
        'content_type': request.args.get('type', '').strip(),
        'webinar_format': request.args.get('webinar_format', '').strip(),
        'event_format': request.args.get('event_format', '').strip(),
        'lifecycle_status': request.args.get('status', '').strip(),
        'theme': request.args.get('theme', '').strip()
    }
    events = get_event_listing_cards(public_only=True, filters=filters)
    themes = sorted({e.get('theme') for e in events if e.get('theme')})
    return render_template('events_listing.html', events=events, filters=filters, themes=themes, active_page='resources')

def render_unified_event_detail(slug, expected_type=None, require_on_demand=False):
    event = fetch_event_bundle(slug=slug, public_only=True)
    if not event:
        abort(404)
    if expected_type and event.get('content_type') != expected_type:
        abort(404)
    is_on_demand = event.get('content_type') == 'Webinar' and (
        event.get('webinar_format') == 'On-Demand Webinar' or event.get('lifecycle_status') == 'On-Demand'
    )
    if require_on_demand and not is_on_demand:
        return redirect(f"/events/webinars/{slug}", code=302)
    data = build_event_detail_data(event)
    type_name = event.get('content_type') or 'Event'
    response = make_response(render_template('resource_detail.html', data=data, type=type_name, slug=slug, active_page='resources'))
    if data.get('is_noindex'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response

@app.route('/events/webinars/on-demand/<slug>')
def events_on_demand_webinar_detail(slug):
    return render_unified_event_detail(slug.strip('/'), expected_type='Webinar', require_on_demand=True)

@app.route('/events/webinars/<slug>')
def events_webinar_detail(slug):
    return render_unified_event_detail(slug.strip('/'), expected_type='Webinar')

@app.route('/events/<slug>')
def events_event_detail(slug):
    return render_unified_event_detail(slug.strip('/'), expected_type='Event')

@app.route('/api/events')
def api_events_list():
    return jsonify({'status': 'success', 'events': get_event_listing_cards(public_only=True)})

@app.route('/api/events/webinars')
def api_events_webinars():
    return jsonify({'status': 'success', 'events': get_event_listing_cards(public_only=True, filters={'content_type': 'Webinar'})})

@app.route('/api/events/webinars/on-demand')
def api_events_webinars_on_demand():
    return jsonify({'status': 'success', 'events': get_event_listing_cards(public_only=True, filters={'content_type': 'Webinar', 'lifecycle_status': 'On-Demand'})})

@app.route('/api/events/upcoming')
def api_events_upcoming():
    return jsonify({'status': 'success', 'events': get_event_listing_cards(public_only=True, filters={'lifecycle_status': 'Upcoming'})})

@app.route('/api/events/past')
def api_events_past():
    conn = get_db_connection()
    try:
        rows = conn.execute('''
            SELECT * FROM event_webinars
            WHERE publishing_status = 'Published'
              AND lifecycle_status IN ('Completed', 'On-Demand')
            ORDER BY updated_at DESC
        ''').fetchall()
    finally:
        conn.close()
    events = []
    for row in rows:
        item = dict(row)
        item.pop('recording_link', None)
        item.pop('live_join_link', None)
        events.append(item)
    return jsonify({'status': 'success', 'events': events})

@app.route('/api/events/<slug>')
def api_event_detail(slug):
    event = fetch_event_bundle(slug=slug.strip('/'), public_only=True)
    if not event:
        return jsonify({'status': 'error', 'message': 'Event not found.'}), 404
    public_event = dict(event)
    public_event.pop('recording_link', None)
    public_event.pop('live_join_link', None)
    return jsonify({'status': 'success', 'event': public_event, 'url': event_public_url(event)})

@app.route('/api/events/<slug>/register', methods=['POST'])
def api_event_register(slug):
    ensure_event_webinar_schema()
    event = fetch_event_webinar(slug=slug.strip('/'))
    if not event or event.get('publishing_status') != 'Published':
        return jsonify({'status': 'error', 'message': 'This event or webinar is not available for registration.'}), 404

    if request.form.get('website_url_honeypot'):
        return jsonify({'status': 'success', 'message': 'Registration received.'})

    now = time.time()
    ip = request.remote_addr or '127.0.0.1'
    timestamps = EVENT_REGISTRATION_RATE_LIMIT.get(ip, [])
    timestamps = [t for t in timestamps if now - t < 60]
    if len(timestamps) >= 5:
        return jsonify({'status': 'error', 'message': 'Too many registration attempts. Please try again in a minute.'}), 429
    timestamps.append(now)
    EVENT_REGISTRATION_RATE_LIMIT[ip] = timestamps

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('business_email', '').strip().lower()
    company = request.form.get('company', '').strip()
    job_title = request.form.get('job_title', '').strip()
    phone = request.form.get('phone', '').strip()
    country = request.form.get('country', '').strip()
    how_heard = request.form.get('how_did_you_hear', '').strip() or request.form.get('source_info', '').strip()
    consent = 1 if request.form.get('consent_status') in ('1', 'on', 'true', 'yes') else 0

    if not first_name or not last_name:
        return jsonify({'status': 'error', 'message': 'First name and last name are required.'}), 400
    if not email:
        return jsonify({'status': 'error', 'message': 'Business email is required.'}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'status': 'error', 'message': 'Please enter a valid email address.'}), 400
    if event.get('business_email_only', 1) and not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address.'}), 400
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Please enter a valid business phone number.'}), 400

    close_dt = parse_event_datetime(event.get('registration_close_datetime'))
    if close_dt and close_dt < datetime.utcnow():
        return jsonify({'status': 'error', 'message': 'Registration is closed for this event.'}), 400

    conn = get_db_connection()
    try:
        if event.get('capacity'):
            current_count = conn.execute("SELECT COUNT(*) as cnt FROM event_registrations WHERE event_id = ?", (event['id'],)).fetchone()['cnt']
            if current_count >= int(event['capacity']):
                return jsonify({'status': 'error', 'message': 'This event has reached registration capacity.'}), 400

        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO event_registrations (
                event_id, first_name, last_name, business_email, company, job_title,
                phone, country, how_did_you_hear, consent_status, attendee_status,
                source_page, referrer, utm_source, utm_medium, utm_campaign, utm_term,
                utm_content, registered_at, ip_address, user_agent, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Registered', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event['id'], first_name, last_name, email, company, job_title,
            phone, country, how_heard, consent,
            request.form.get('source_page') or request.path,
            request.form.get('referrer') or request.referrer or '',
            request.form.get('utm_source', ''),
            request.form.get('utm_medium', ''),
            request.form.get('utm_campaign', ''),
            request.form.get('utm_term', ''),
            request.form.get('utm_content', ''),
            now_str,
            ip,
            request.headers.get('User-Agent', ''),
            now_str,
            now_str
        ))
        registration_id = cursor.lastrowid
        conn.commit()

        crm_lead_id = None
        if event.get('crm_integration_enabled', 1):
            try:
                from crm.models import forward_lead_to_crm
                is_on_demand = event.get('content_type') == 'Webinar' and event.get('lifecycle_status') == 'On-Demand'
                source_form = 'Event Registration'
                if event.get('content_type') == 'Webinar':
                    source_form = 'On-Demand Webinar Registration' if is_on_demand else 'Live Webinar Registration'
                crm_lead_id = forward_lead_to_crm(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    company=company,
                    phone=phone,
                    job_title=job_title,
                    geography='',
                    country=country,
                    industry='',
                    message=f"Registered for {event.get('content_type')}: {event.get('title')} | Theme: {event.get('theme') or ''}",
                    source_form=source_form,
                    source_page=event_public_url(event),
                    cta_clicked=event.get('registration_cta_text') or 'Register',
                    lead_source='Website',
                    utm_source=request.form.get('utm_source', ''),
                    utm_medium=request.form.get('utm_medium', ''),
                    utm_campaign=request.form.get('utm_campaign', ''),
                    utm_term=request.form.get('utm_term', ''),
                    utm_content=request.form.get('utm_content', ''),
                    referrer=request.form.get('referrer') or request.referrer or '',
                    ip_address=ip,
                    user_agent=request.headers.get('User-Agent', ''),
                    consent_status=consent,
                    form_name=source_form,
                    product_solution_interest=event.get('theme') or '',
                    partner_interest=''
                )
                if crm_lead_id:
                    conn.execute("UPDATE event_registrations SET crm_website_lead_id = ? WHERE id = ?", (str(crm_lead_id), registration_id))
            except Exception as e:
                print(f"Error forwarding event registration to CRM: {e}")

        is_on_demand = event.get('content_type') == 'Webinar' and event.get('lifecycle_status') == 'On-Demand'
        redirect_url = None
        if is_on_demand and event.get('recording_link'):
            redirect_url = event.get('recording_link')
            conn.execute("UPDATE event_registrations SET accessed_recording_at = ? WHERE id = ?", (now_str, registration_id))
        log_event_activity(conn, event['id'], 'registration', f"Registration received from {email}.", None, None, {'registration_id': registration_id})
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        'status': 'success',
        'message': event.get('thank_you_message') or f"Thank you, {first_name}. Your registration has been received.",
        'registration_id': registration_id,
        'redirect_url': redirect_url
    })

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

@app.route('/clients')
def clients_page():
    import json
    import os
    try:
        json_path = os.path.join(app.root_path, 'clients_by_industry.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            clients_data = json.load(f)
    except Exception as e:
        app.logger.error(f"Error loading clients mapping: {e}")
        clients_data = {}
    return render_template('clients.html', clients_data=clients_data, active_page='about_us')

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
        
    if not is_corporate_email(email):
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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone='', job_title='',
        geography='', country='', industry='', message=f"Registered for {resource_type}: {resource_title}",
        source_form=f"{resource_type} Lead Form",
        source_page=f"/{resource_type.lower()}s/{resource_slug}" if resource_type else f"/resources/{resource_slug}",
        cta_clicked='Register/Download', lead_source='Website',
        utm_source='', utm_medium='', utm_campaign='', utm_term='', utm_content='',
        referrer=source_info, ip_address=ip, user_agent=request.headers.get('User-Agent', ''), consent_status=1
    )
    
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
        
    # Resolve background banner image URL based on industry vertical
    banner_url = None
    if post['banner_path']:
        banner_url = post['banner_path']
    else:
        ind = (post['industry'] or '').lower()
        if 'bfsi' in ind or 'bank' in ind or 'finance' in ind or 'insurance' in ind:
            banner_url = '/static/img/case-studies/industries/BFSI.jpg'
        elif 'health' in ind or 'pharma' in ind or 'clinical' in ind or 'medical' in ind:
            banner_url = '/static/img/case-studies/industries/Healthcare.jpg'
        elif 'manufact' in ind or 'factory' in ind or 'automotive' in ind:
            banner_url = '/static/img/case-studies/industries/Manufacturing.jpg'
        elif 'retail' in ind or 'commerce' in ind or 'consumer' in ind or 'goods' in ind:
            banner_url = '/static/img/case-studies/industries/Retail.jpg'
        elif 'telecom' in ind or 'network' in ind:
            banner_url = '/static/img/case-studies/industries/Telecom.jpg'
        elif 'hospit' in ind or 'hotel' in ind or 'travel' in ind or 'tourism' in ind:
            banner_url = '/static/img/case-studies/industries/Hospitality.jpg'
        else:
            banner_url = '/static/img/case-studies/industries/BFSI.jpg'
            
    return render_template('case_study_detail.html', post=post, is_admin=is_admin, active_page='case-studies', banner_url=banner_url)

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
        
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400
        
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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='', message=f"Downloaded Case Study: {study['title']}",
        source_form='Case Study Download Form',
        source_page=source_url or f"/case-studies/{slug}", cta_clicked='Download PDF', lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term=utm_term, utm_content=utm_content,
        referrer=referrer, ip_address=ip, user_agent=user_agent, consent_status=consent
    )
    
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
    try:
        event_rows = conn.execute("""
            SELECT slug, content_type, webinar_format, lifecycle_status, updated_at, published_at
            FROM event_webinars
            WHERE publishing_status = 'Published' AND lifecycle_status != 'Cancelled'
        """).fetchall()
    except Exception:
        event_rows = []
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
        ('/events', '0.8'),
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

    for event in event_rows:
        event_dict = dict(event)
        date_str = (event_dict.get('updated_at') or event_dict.get('published_at') or datetime.now().strftime('%Y-%m-%d'))[:10]
        xml_content += f'  <url>\n    <loc>https://www.thinkartha.com{event_public_url(event_dict)}</loc>\n    <lastmod>{date_str}</lastmod>\n    <priority>0.7</priority>\n  </url>\n'
        
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

# ==========================================================================
# Dynamic Robots.txt and XML Sitemap Handlers
# ==========================================================================

@app.route('/robots.txt')
def robots_txt():
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT value FROM seo_settings WHERE key = 'robots_policy'").fetchone()
        conn.close()
        
        policy = json.loads(row['value']) if row else {}
    except Exception as e:
        print(f"Error fetching robots policy: {e}")
        policy = {
            'Googlebot': {'allowed': True},
            'Bingbot': {'allowed': True},
            'OAI-SearchBot': {'allowed': True},
            'GPTBot': {'allowed': False},
            '*': {'allowed': True}
        }
        
    lines = []
    
    # Render user-agent rules
    for ua, rules in policy.items():
        lines.append(f"User-agent: {ua}")
        if rules.get('allowed', True):
            lines.append("Allow: /")
        else:
            lines.append("Disallow: /")
        if rules.get('crawl_delay'):
            lines.append(f"Crawl-delay: {rules['crawl_delay']}")
        lines.append("")
        
    # Standard disallowed private areas
    lines.append("# Private Areas")
    lines.append("Disallow: /admin/")
    lines.append("Disallow: /crm/")
    lines.append("Disallow: /api/")
    lines.append("")
    
    # Sitemap reference
    lines.append("Sitemap: https://www.thinkartha.com/sitemap.xml")
    
    response = make_response("\n".join(lines))
    response.headers["Content-Type"] = "text/plain"
    return response

@app.route('/sitemap.xml')
def sitemap_index():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    sub_sitemaps = ['main', 'services', 'industries', 'case_studies', 'blogs', 'jobs']
    now_str = datetime.now().strftime('%Y-%m-%d')
    
    for s in sub_sitemaps:
        xml.append('  <sitemap>')
        xml.append(f'    <loc>https://www.thinkartha.com/sitemap_{s}.xml</loc>')
        xml.append(f'    <lastmod>{now_str}</lastmod>')
        xml.append('  </sitemap>')
        
    xml.append('</sitemapindex>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_main.xml')
def sitemap_main():
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM seo_pages WHERE sitemap_inclusion = 1 AND robots_directive LIKE '%index%'").fetchall()
    conn.close()
    
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for p in pages:
        slug = p['route_slug']
        if any(prefix in slug for prefix in ['/blogs/', '/case-studies/', '/careers/']) and slug not in ['/blogs', '/case-studies', '/careers']:
            continue
            
        xml.append('  <url>')
        xml.append(f'    <loc>https://www.thinkartha.com{slug}</loc>')
        last_mod = p['last_updated'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
        xml.append(f'    <priority>{p["sitemap_priority"] or 0.8}</priority>')
        xml.append('  </url>')
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_services.xml')
def sitemap_services():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    xml.append('  <url>')
    xml.append('    <loc>https://www.thinkartha.com/solutions</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <priority>0.8</priority>')
    xml.append('  </url>')
    
    for slug in SOLUTIONS_DATA.keys():
        path = f'/solutions/{slug}'
        priority = 0.7
        last_mod = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (path,)).fetchone()
            conn.close()
            if row:
                if row['sitemap_inclusion'] == 0 or 'noindex' in (row['robots_directive'] or ''):
                    continue
                priority = row['sitemap_priority'] or 0.7
                if row['last_updated']:
                    last_mod = row['last_updated']
        except Exception:
            pass
            
        xml.append('  <url>')
        xml.append(f'    <loc>https://www.thinkartha.com{path}</loc>')
        xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
        xml.append(f'    <priority>{priority}</priority>')
        xml.append('  </url>')
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_industries.xml')
def sitemap_industries():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    xml.append('  <url>')
    xml.append('    <loc>https://www.thinkartha.com/industries</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <priority>0.8</priority>')
    xml.append('  </url>')
    
    for slug in INDUSTRIES_DATA.keys():
        path = f'/industries/{slug}'
        priority = 0.7
        last_mod = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (path,)).fetchone()
            conn.close()
            if row:
                if row['sitemap_inclusion'] == 0 or 'noindex' in (row['robots_directive'] or ''):
                    continue
                priority = row['sitemap_priority'] or 0.7
                if row['last_updated']:
                    last_mod = row['last_updated']
        except Exception:
            pass
            
        xml.append('  <url>')
        xml.append(f'    <loc>https://www.thinkartha.com{path}</loc>')
        xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
        xml.append(f'    <priority>{priority}</priority>')
        xml.append('  </url>')
        
    try:
        conn = get_db_connection()
        m_pages = conn.execute("SELECT * FROM industry_microsite_pages WHERE status = 'Published' AND noindex = 0").fetchall()
        conn.close()
        for p in m_pages:
            xml.append('  <url>')
            xml.append(f'    <loc>https://www.thinkartha.com{p["url"]}</loc>')
            last_mod = p['updated_at'] or datetime.now().strftime('%Y-%m-%d')
            xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
            xml.append('    <priority>0.7</priority>')
            xml.append('  </url>')
    except Exception:
        pass
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_case_studies.xml')
def sitemap_case_studies():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    xml.append('  <url>')
    xml.append('    <loc>https://www.thinkartha.com/case-studies</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <priority>0.8</priority>')
    xml.append('  </url>')
    
    try:
        conn = get_db_connection()
        studies = conn.execute("SELECT * FROM case_studies WHERE status = 'Published'").fetchall()
        conn.close()
        
        for s in studies:
            path = f'/case-studies/{s["slug"]}'
            priority = 0.6
            last_mod = s['updated_at'] or datetime.now().strftime('%Y-%m-%d')
            
            try:
                conn = get_db_connection()
                row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (path,)).fetchone()
                conn.close()
                if row:
                    if row['sitemap_inclusion'] == 0 or 'noindex' in (row['robots_directive'] or ''):
                        continue
                    priority = row['sitemap_priority'] or 0.6
                    if row['last_updated']:
                        last_mod = row['last_updated']
            except Exception:
                pass
                
            xml.append('  <url>')
            xml.append(f'    <loc>https://www.thinkartha.com{path}</loc>')
            xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
            xml.append(f'    <priority>{priority}</priority>')
            xml.append('  </url>')
    except Exception:
        pass
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_blogs.xml')
def sitemap_blogs():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    xml.append('  <url>')
    xml.append('    <loc>https://www.thinkartha.com/blogs</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <priority>0.8</priority>')
    xml.append('  </url>')
    
    try:
        conn = get_db_connection()
        blogs = conn.execute("SELECT * FROM posts WHERE status = 'Published'").fetchall()
        conn.close()
        
        for b in blogs:
            path = f'/blogs/{b["slug"]}'
            priority = 0.6
            last_mod = datetime.now().strftime('%Y-%m-%d')
            try:
                dt = datetime.strptime(b['date'], '%b %d, %Y')
                last_mod = dt.strftime('%Y-%m-%d')
            except Exception:
                pass
                
            try:
                conn = get_db_connection()
                row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (path,)).fetchone()
                conn.close()
                if row:
                    if row['sitemap_inclusion'] == 0 or 'noindex' in (row['robots_directive'] or ''):
                        continue
                    priority = row['sitemap_priority'] or 0.6
                    if row['last_updated']:
                        last_mod = row['last_updated']
            except Exception:
                pass
                
            xml.append('  <url>')
            xml.append(f'    <loc>https://www.thinkartha.com{path}</loc>')
            xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
            xml.append(f'    <priority>{priority}</priority>')
            xml.append('  </url>')
    except Exception:
        pass
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/sitemap_jobs.xml')
def sitemap_jobs():
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    xml.append('  <url>')
    xml.append('    <loc>https://www.thinkartha.com/careers</loc>')
    xml.append(f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('    <priority>0.8</priority>')
    xml.append('  </url>')
    
    try:
        conn = get_db_connection()
        jobs = conn.execute("SELECT * FROM career_jobs WHERE status = 'published'").fetchall()
        conn.close()
        
        for j in jobs:
            path = f'/careers/{j["slug"]}'
            priority = 0.5
            last_mod = j['posted_date'] or datetime.now().strftime('%Y-%m-%d')
            
            try:
                conn = get_db_connection()
                row = conn.execute("SELECT * FROM seo_pages WHERE route_slug = ?", (path,)).fetchone()
                conn.close()
                if row:
                    if row['sitemap_inclusion'] == 0 or 'noindex' in (row['robots_directive'] or ''):
                        continue
                    priority = row['sitemap_priority'] or 0.5
                    if row['last_updated']:
                        last_mod = row['last_updated']
            except Exception:
                pass
                
            xml.append('  <url>')
            xml.append(f'    <loc>https://www.thinkartha.com{path}</loc>')
            xml.append(f'    <lastmod>{last_mod[:10]}</lastmod>')
            xml.append(f'    <priority>{priority}</priority>')
            xml.append('  </url>')
    except Exception:
        pass
        
    xml.append('</urlset>')
    
    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

# ==========================================================================
# IndexNow Support and Verification Route
# ==========================================================================

def submit_to_indexnow(url, action='update'):
    try:
        conn = get_db_connection()
        key_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'indexnow_key'").fetchone()
        enabled_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'indexnow_enabled'").fetchone()
        conn.close()
        
        if not enabled_row or enabled_row['value'] != '1':
            return False
            
        key = key_row['value'] if key_row else None
        if not key:
            return False
            
        import urllib.request
        import json
        
        indexnow_url = "https://api.indexnow.org/IndexNow"
        data = {
            "host": "www.thinkartha.com",
            "key": key,
            "keyLocation": f"https://www.thinkartha.com/{key}.txt",
            "urlList": [url]
        }
        
        req_body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            indexnow_url,
            data=req_body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method='POST'
        )
        
        response_code = 0
        error_message = ""
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                response_code = response.getcode()
                status = "Success" if response_code == 200 else "Failed"
        except Exception as e_http:
            status = "Failed"
            if hasattr(e_http, 'code'):
                response_code = e_http.code
                error_message = f"HTTP Error {e_http.code}"
            else:
                error_message = str(e_http)
                
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO seo_indexnow_logs (url, action, status, response_code, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (url, action, status, response_code, error_message))
        conn.commit()
        conn.close()
        
        return status == "Success"
    except Exception as e:
        print(f"Error submitting to IndexNow: {e}")
        try:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO seo_indexnow_logs (url, action, status, response_code, error_message)
                VALUES (?, ?, 'Failed', 0, ?)
            """, (url, action, str(e)))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return False

@app.route('/<string:key_file>.txt')
def indexnow_verification(key_file):
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT value FROM seo_settings WHERE key = 'indexnow_key'").fetchone()
        conn.close()
        
        db_key = row['value'] if row else None
        if db_key and key_file == db_key:
            response = make_response(db_key)
            response.headers["Content-Type"] = "text/plain"
            return response
    except Exception as e:
        print(f"Error serving IndexNow verification key: {e}")
        
    abort(404)

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
@app.route('/admin/events')
def admin_events():
    if 'logged_in' not in session:
        return redirect('/admin/login')

    ensure_event_webinar_schema()
    conn = get_db_connection()
    try:
        updated_count = run_event_status_update(conn)
        if updated_count:
            conn.commit()

        filters = {
            'content_type': request.args.get('type', '').strip(),
            'webinar_format': request.args.get('webinar_format', '').strip(),
            'event_format': request.args.get('event_format', '').strip(),
            'lifecycle_status': request.args.get('status', '').strip(),
            'publishing_status': request.args.get('publishing_status', '').strip(),
            'theme': request.args.get('theme', '').strip()
        }
        clauses = []
        params = []
        for key, column in (
            ('content_type', 'ew.content_type'),
            ('webinar_format', 'ew.webinar_format'),
            ('event_format', 'ew.event_format'),
            ('lifecycle_status', 'ew.lifecycle_status'),
            ('publishing_status', 'ew.publishing_status')
        ):
            if filters.get(key):
                clauses.append(f"{column} = ?")
                params.append(filters[key])
        if filters.get('theme'):
            clauses.append("ew.theme LIKE ?")
            params.append(f"%{filters['theme']}%")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''

        rows = conn.execute(f'''
            SELECT ew.*,
                   (SELECT COUNT(*) FROM event_registrations er WHERE er.event_id = ew.id) as registration_count,
                   (SELECT COUNT(*) FROM event_speakers es WHERE es.event_id = ew.id AND es.is_active = 1) as speaker_count,
                   (SELECT COUNT(*) FROM event_agenda_items ea WHERE ea.event_id = ew.id) as agenda_count
            FROM event_webinars ew
            {where_sql}
            ORDER BY
                CASE WHEN ew.start_datetime IS NULL OR ew.start_datetime = '' THEN 1 ELSE 0 END,
                ew.start_datetime ASC,
                ew.updated_at DESC
        ''', params).fetchall()

        stats = {
            'total': conn.execute("SELECT COUNT(*) as cnt FROM event_webinars").fetchone()['cnt'],
            'events': conn.execute("SELECT COUNT(*) as cnt FROM event_webinars WHERE content_type = 'Event'").fetchone()['cnt'],
            'webinars': conn.execute("SELECT COUNT(*) as cnt FROM event_webinars WHERE content_type = 'Webinar'").fetchone()['cnt'],
            'on_demand': conn.execute("SELECT COUNT(*) as cnt FROM event_webinars WHERE lifecycle_status = 'On-Demand'").fetchone()['cnt'],
            'needs_recording': conn.execute("""
                SELECT COUNT(*) as cnt FROM event_webinars
                WHERE content_type = 'Webinar'
                  AND webinar_format = 'Live Webinar'
                  AND lifecycle_status = 'Completed'
                  AND (recording_link IS NULL OR recording_link = '')
            """).fetchone()['cnt']
        }
        themes = [r['theme'] for r in conn.execute(
            "SELECT DISTINCT theme FROM event_webinars WHERE theme IS NOT NULL AND theme != '' ORDER BY theme"
        ).fetchall()]
    finally:
        conn.close()

    events = []
    now = datetime.utcnow()
    for row in rows:
        item = dict(row)
        item['public_url'] = event_public_url(item)
        item['display_date'] = format_event_short_date(item.get('start_datetime'), 'On-Demand')
        item['display_time'] = format_event_time_range(item)
        end_dt = parse_event_datetime(item.get('end_datetime')) or parse_event_datetime(item.get('start_datetime'))
        item['is_conversion_eligible'] = (
            item.get('content_type') == 'Webinar'
            and item.get('webinar_format') == 'Live Webinar'
            and item.get('publishing_status') != 'Archived'
            and (item.get('lifecycle_status') == 'Completed' or (end_dt is not None and end_dt <= now))
        )
        events.append(item)

    return render_template('admin_events.html', events=events, stats=stats, filters=filters, themes=themes, active_admin='events')

@app.route('/admin/events/new', methods=['GET', 'POST'])
def admin_event_new():
    if 'logged_in' not in session:
        return redirect('/admin/login')

    ensure_event_webinar_schema()
    if request.method == 'POST':
        upload_errors = []
        payload = get_event_payload_from_form(upload_errors=upload_errors)
        validate_event_speaker_image_uploads(upload_errors)
        errors = upload_errors + validate_event_payload(payload)
        if errors:
            return render_template(
                'admin_event_editor.html',
                event=build_event_form_context(payload),
                speakers=[],
                agenda_items=[],
                takeaways=[],
                errors=errors,
                mode='new',
                active_admin='events'
            )

        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        payload['created_by'] = session.get('username', 'Admin')
        payload['created_at'] = now_str
        payload['published_at'] = now_str if payload.get('publishing_status') == 'Published' else None
        payload['archived_at'] = now_str if payload.get('publishing_status') == 'Archived' else None

        columns = list(payload.keys())
        placeholders = ','.join(['?'] * len(columns))
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO event_webinars ({','.join(columns)}) VALUES ({placeholders})",
                [payload[col] for col in columns]
            )
            event_id = cursor.lastrowid
            save_event_children(conn, event_id, payload.get('slug', ''), upload_errors)
            log_event_activity(conn, event_id, 'created', 'Created unified event/webinar record.', None, payload.get('lifecycle_status'))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return render_template(
                'admin_event_editor.html',
                event=build_event_form_context(payload),
                speakers=[],
                agenda_items=[],
                takeaways=[],
                errors=['Slug already exists. Please choose a unique slug.'],
                mode='new',
                active_admin='events'
            )
        finally:
            conn.close()
        return redirect('/admin/events')

    return render_template(
        'admin_event_editor.html',
        event=build_event_form_context(),
        speakers=[],
        agenda_items=[],
        takeaways=[],
        errors=[],
        mode='new',
        active_admin='events'
    )

@app.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
def admin_event_edit_unified(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')

    ensure_event_webinar_schema()
    event = fetch_event_bundle(event_id=event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        upload_errors = []
        payload = get_event_payload_from_form(event, upload_errors=upload_errors)
        validate_event_speaker_image_uploads(upload_errors)
        errors = upload_errors + validate_event_payload(payload)
        if errors:
            return render_template(
                'admin_event_editor.html',
                event=build_event_form_context({**event, **payload}),
                speakers=event.get('speakers', []),
                agenda_items=event.get('agenda_items', []),
                takeaways=event.get('takeaways', []),
                errors=errors,
                mode='edit',
                active_admin='events'
            )

        if payload.get('publishing_status') == 'Published' and not event.get('published_at'):
            payload['published_at'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if payload.get('publishing_status') == 'Archived' and not event.get('archived_at'):
            payload['archived_at'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        set_clause = ', '.join([f"{col} = ?" for col in payload.keys()])
        conn = get_db_connection()
        try:
            conn.execute(
                f"UPDATE event_webinars SET {set_clause} WHERE id = ?",
                [payload[col] for col in payload.keys()] + [event_id]
            )
            save_event_children(conn, event_id, payload.get('slug', ''), upload_errors)
            log_event_activity(conn, event_id, 'updated', 'Updated unified event/webinar record.', event.get('lifecycle_status'), payload.get('lifecycle_status'))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return render_template(
                'admin_event_editor.html',
                event=build_event_form_context({**event, **payload}),
                speakers=event.get('speakers', []),
                agenda_items=event.get('agenda_items', []),
                takeaways=event.get('takeaways', []),
                errors=['Slug already exists. Please choose a unique slug.'],
                mode='edit',
                active_admin='events'
            )
        finally:
            conn.close()
        return redirect('/admin/events')

    return render_template(
        'admin_event_editor.html',
        event=build_event_form_context(event),
        speakers=event.get('speakers', []),
        agenda_items=event.get('agenda_items', []),
        takeaways=event.get('takeaways', []),
        errors=[],
        mode='edit',
        active_admin='events'
    )

@app.route('/admin/events/<int:event_id>/publish', methods=['POST'])
def admin_event_publish(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    conn = get_db_connection()
    try:
        event = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        if not event:
            abort(404)
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE event_webinars SET publishing_status = 'Published', published_at = COALESCE(published_at, ?), updated_at = ? WHERE id = ?",
            (now_str, now_str, event_id)
        )
        log_event_activity(conn, event_id, 'published', 'Published event/webinar.', event['publishing_status'], 'Published')
        conn.commit()
    finally:
        conn.close()
    return redirect('/admin/events')

@app.route('/admin/events/<int:event_id>/archive', methods=['POST'])
def admin_event_archive(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    conn = get_db_connection()
    try:
        event = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        if not event:
            abort(404)
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE event_webinars SET publishing_status = 'Archived', archived_at = COALESCE(archived_at, ?), updated_at = ? WHERE id = ?",
            (now_str, now_str, event_id)
        )
        log_event_activity(conn, event_id, 'archived', 'Archived event/webinar.', event['publishing_status'], 'Archived')
        conn.commit()
    finally:
        conn.close()
    return redirect('/admin/events')

@app.route('/admin/events/<int:event_id>/duplicate', methods=['POST'])
def admin_event_duplicate(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')

    ensure_event_webinar_schema()
    conn = get_db_connection()
    try:
        source = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        if not source:
            abort(404)
        columns = [r['name'] for r in conn.execute("PRAGMA table_info(event_webinars)").fetchall() if r['name'] != 'id']
        source_dict = dict(source)
        base_slug = slugify_value(f"{source_dict.get('slug')}-copy")
        slug = base_slug
        suffix = 2
        while conn.execute("SELECT id FROM event_webinars WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        source_dict['title'] = f"{source_dict.get('title')} (Copy)"
        source_dict['slug'] = slug
        source_dict['publishing_status'] = 'Draft'
        source_dict['published_at'] = None
        source_dict['archived_at'] = None
        source_dict['created_at'] = now_str
        source_dict['updated_at'] = now_str
        source_dict['created_by'] = session.get('username', 'Admin')
        source_dict['updated_by'] = session.get('username', 'Admin')
        source_dict['converted_to_ondemand_at'] = None
        source_dict['converted_by'] = None
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO event_webinars ({','.join(columns)}) VALUES ({','.join(['?'] * len(columns))})",
            [source_dict.get(col) for col in columns]
        )
        new_id = cursor.lastrowid
        for speaker in conn.execute("SELECT * FROM event_speakers WHERE event_id = ?", (event_id,)).fetchall():
            s = dict(speaker)
            s.pop('id', None)
            s['event_id'] = new_id
            cols = list(s.keys())
            conn.execute(f"INSERT INTO event_speakers ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})", [s[c] for c in cols])
        for agenda in conn.execute("SELECT * FROM event_agenda_items WHERE event_id = ?", (event_id,)).fetchall():
            a = dict(agenda)
            a.pop('id', None)
            a['event_id'] = new_id
            cols = list(a.keys())
            conn.execute(f"INSERT INTO event_agenda_items ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})", [a[c] for c in cols])
        for takeaway in conn.execute("SELECT * FROM event_key_takeaways WHERE event_id = ?", (event_id,)).fetchall():
            t = dict(takeaway)
            t.pop('id', None)
            t['event_id'] = new_id
            cols = list(t.keys())
            conn.execute(f"INSERT INTO event_key_takeaways ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})", [t[c] for c in cols])
        log_event_activity(conn, new_id, 'duplicated', f"Duplicated from event/webinar #{event_id}.", None, 'Draft')
        conn.commit()
    finally:
        conn.close()
    return redirect(f'/admin/events/{new_id}/edit')

@app.route('/admin/events/<int:event_id>/add-recording-link', methods=['POST'])
def admin_event_add_recording_link(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    recording_link = request.form.get('recording_link', '').strip()
    if not recording_link or not is_valid_event_url(recording_link):
        return redirect(f'/admin/events/{event_id}/edit')
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE event_webinars
            SET recording_link = ?, recording_duration = ?, recording_access_type = ?, updated_at = ?
            WHERE id = ?
        ''', (
            recording_link,
            request.form.get('recording_duration', '').strip(),
            request.form.get('recording_access_type', 'redirect'),
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            event_id
        ))
        log_event_activity(conn, event_id, 'recording_added', 'Added or updated recording link.', None, None)
        conn.commit()
    finally:
        conn.close()
    return redirect('/admin/events')

@app.route('/admin/events/<int:event_id>/convert-to-ondemand', methods=['POST'])
def admin_event_convert_to_ondemand(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')

    recording_link = request.form.get('recording_link', '').strip()
    if not recording_link or not is_valid_event_url(recording_link):
        return redirect(f'/admin/events/{event_id}/edit')

    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        event = conn.execute("SELECT * FROM event_webinars WHERE id = ?", (event_id,)).fetchone()
        if not event:
            abort(404)
        conn.execute('''
            UPDATE event_webinars
            SET webinar_format = 'On-Demand Webinar',
                lifecycle_status = 'On-Demand',
                live_join_link = '',
                recording_link = ?,
                recording_access_type = ?,
                recording_duration = ?,
                registration_cta_text = ?,
                thank_you_message = ?,
                converted_to_ondemand_at = ?,
                converted_by = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            recording_link,
            request.form.get('recording_access_type', 'redirect'),
            request.form.get('recording_duration', '').strip(),
            request.form.get('registration_cta_text', '').strip() or 'Watch On-Demand',
            request.form.get('thank_you_message', '').strip() or 'Thank you. Your webinar access is ready.',
            now_str,
            session.get('username', 'Admin'),
            now_str,
            event_id
        ))
        log_event_activity(conn, event_id, 'convert_to_ondemand', 'Converted live webinar to on-demand.', event['lifecycle_status'], 'On-Demand')
        conn.commit()
    finally:
        conn.close()
    return redirect('/admin/events')

@app.route('/admin/events/run-status-update', methods=['POST'])
def admin_events_run_status_update():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    run_event_status_update()
    return redirect('/admin/events')

@app.route('/admin/events/<int:event_id>/registrations')
def admin_event_registrations(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    event = fetch_event_webinar(event_id=event_id)
    if not event:
        abort(404)
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    clauses = ["event_id = ?"]
    params = [event_id]
    if query:
        clauses.append("(business_email LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR company LIKE ?)")
        params.extend([f"%{query}%"] * 4)
    if status_filter:
        clauses.append("attendee_status = ?")
        params.append(status_filter)
    conn = get_db_connection()
    try:
        rows = conn.execute(f'''
            SELECT * FROM event_registrations
            WHERE {' AND '.join(clauses)}
            ORDER BY registered_at DESC, id DESC
        ''', params).fetchall()
    finally:
        conn.close()
    return render_template('admin_event_registrations.html', event=event, registrations=rows, query=query, status_filter=status_filter, active_admin='events')

@app.route('/admin/events/<int:event_id>/registrations/<int:registration_id>/status', methods=['POST'])
def admin_event_registration_status(event_id, registration_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    status_value = request.form.get('attendee_status', 'Registered')
    notes = request.form.get('notes', '').strip()
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE event_registrations
            SET attendee_status = ?, notes = ?, updated_at = ?
            WHERE id = ? AND event_id = ?
        ''', (status_value, notes, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), registration_id, event_id))
        log_event_activity(conn, event_id, 'registration_status_update', f"Updated registration #{registration_id} to {status_value}.", None, None)
        conn.commit()
    finally:
        conn.close()
    return redirect(f'/admin/events/{event_id}/registrations')

@app.route('/admin/events/<int:event_id>/registrations/export')
def admin_event_registrations_export(event_id):
    if 'logged_in' not in session:
        return redirect('/admin/login')
    event = fetch_event_webinar(event_id=event_id)
    if not event:
        abort(404)
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM event_registrations WHERE event_id = ? ORDER BY registered_at DESC", (event_id,)).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'first_name', 'last_name', 'business_email', 'company', 'job_title',
        'phone', 'country', 'how_did_you_hear', 'consent_status', 'attendee_status',
        'source_page', 'utm_source', 'utm_medium', 'utm_campaign', 'registered_at',
        'crm_website_lead_id', 'notes'
    ])
    for r in rows:
        writer.writerow([
            r['id'], r['first_name'], r['last_name'], r['business_email'], r['company'],
            r['job_title'], r['phone'], r['country'], r['how_did_you_hear'],
            r['consent_status'], r['attendee_status'], r['source_page'], r['utm_source'],
            r['utm_medium'], r['utm_campaign'], r['registered_at'], r['crm_website_lead_id'],
            r['notes']
        ])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f"attachment; filename=event-{event_id}-registrations.csv"
    return response

@app.route('/api/admin/events')
def api_admin_events():
    if 'logged_in' not in session:
        return jsonify({'status': 'error', 'message': 'Admin login required.'}), 401
    return jsonify({'status': 'success', 'events': get_event_listing_cards(public_only=False)})

@app.route('/api/admin/events/<int:event_id>')
def api_admin_event_detail(event_id):
    if 'logged_in' not in session:
        return jsonify({'status': 'error', 'message': 'Admin login required.'}), 401
    event = fetch_event_bundle(event_id=event_id)
    if not event:
        return jsonify({'status': 'error', 'message': 'Event not found.'}), 404
    return jsonify({'status': 'success', 'event': event})

@app.route('/admin/resources')
def admin_resources():
    if 'logged_in' not in session:
        return redirect('/admin/login')
    return redirect('/admin/events')

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
        card_image = request.form.get('card_image')
        
        conn = get_db_connection()
        try:
            if res_type == 'Webinar':
                conn.execute('''
                INSERT INTO webinars (slug, title, host, duration, summary, description, card_image)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (slug, title, loc_or_host, date_or_duration, summary, description, card_image))
            else:
                conn.execute('''
                INSERT INTO events (slug, title, date, location, summary, description, card_image)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (slug, title, date_or_duration, loc_or_host, summary, description, card_image))
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
        card_image = request.form.get('card_image')
        
        try:
            conn.execute('''
            UPDATE events 
            SET title = ?, slug = ?, date = ?, location = ?, summary = ?, description = ?, card_image = ?
            WHERE id = ?
            ''', (title, slug, date_val, location_val, summary, description, card_image, event_id))
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
        card_image = request.form.get('card_image')
        
        try:
            conn.execute('''
            UPDATE webinars 
            SET title = ?, slug = ?, duration = ?, host = ?, summary = ?, description = ?, card_image = ?
            WHERE id = ?
            ''', (title, slug, duration_val, host_val, summary, description, card_image, webinar_id))
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
        
        # Simple auto summary (stripping HTML tags first)
        clean_content = re.sub(r'<[^>]*>', ' ', content)
        clean_content = ' '.join(clean_content.split())
        summary = clean_content[:150] + '...' if len(clean_content) > 150 else clean_content
        
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
        
        # Simple auto summary (stripping HTML tags first)
        clean_content = re.sub(r'<[^>]*>', ' ', content)
        clean_content = ' '.join(clean_content.split())
        summary = clean_content[:150] + '...' if len(clean_content) > 150 else clean_content
        
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
            
            banner_path = request.form.get('banner_path')
            banner_image_file = request.files.get('banner_image_file')
            if banner_image_file and banner_image_file.filename:
                os.makedirs('static/img/case-studies/uploads', exist_ok=True)
                _, ext = os.path.splitext(banner_image_file.filename)
                ext = ext.lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                    filename = f"{slug or title.lower().replace(' ', '-')}-banner{ext}"
                    save_path = os.path.join('static/img/case-studies/uploads', filename)
                    banner_image_file.save(save_path)
                    banner_path = f"/static/img/case-studies/uploads/{filename}"
            
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
                    thumbnail_path, banner_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    title, unique_slug, status, featured, client_name, client_display_name, is_client_anonymized,
                    industry, region, solution_area, technologies, business_challenge, solution_summary,
                    implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                    ai_summary, card_summary or executive_summary[:180] + '...', detail_content, faq_json, tags,
                    seo_title, seo_description, seo_keywords, canonical_url, og_title, og_description, schema_json,
                    now_str, now_str, thumbnail_path, banner_path
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
                
        banner_path = request.form.get('banner_path')
        banner_image_file = request.files.get('banner_image_file')
        if banner_image_file and banner_image_file.filename:
            os.makedirs('static/img/case-studies/uploads', exist_ok=True)
            _, ext = os.path.splitext(banner_image_file.filename)
            ext = ext.lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                filename = f"{slug}-banner{ext}"
                save_path = os.path.join('static/img/case-studies/uploads', filename)
                banner_image_file.save(save_path)
                banner_path = f"/static/img/case-studies/uploads/{filename}"
                
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
            'schema_json': schema_json, 'thumbnail_path': thumbnail_path, 'banner_path': banner_path
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
                thumbnail_path = ?, banner_path = ?
            WHERE id = ?
            ''', (
                title, slug, status, featured, client_name, client_display_name, is_client_anonymized,
                industry, region, solution_area, technologies, business_challenge, solution_summary,
                implementation_approach, business_outcomes, key_metrics, quote, executive_summary,
                ai_summary, card_summary, detail_content, faq_json, tags, seo_title, seo_description,
                seo_keywords, og_title, og_description, schema_json, now_str, published_at,
                thumbnail_path, banner_path, study_id
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
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not name or not email or not subject or not message:
            return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
            
        if not is_corporate_email(email):
            return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Personal email domains are not accepted.'}), 400
        
        # Split name
        name_parts = (name or "").strip().split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        forward_to_crm_wrapper(
            email=email, first_name=first_name, last_name=last_name, company='', phone='', job_title='',
            geography='', country='', industry='', message=f"Subject: {subject}\nMessage: {message}", source_form='Contact Form',
            source_page='/contact-us', cta_clicked='Submit Message', lead_source='Website',
            utm_source='', utm_medium='', utm_campaign='', utm_term='', utm_content='',
            referrer='', ip_address=request.remote_addr or 'unknown', user_agent=request.headers.get('User-Agent', ''), consent_status=1
        )
        
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
        
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400
        
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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='Healthcare', message=message, source_form=f"Healthcare Form ({source_page})",
        source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term='', utm_content='',
        referrer=referrer, ip_address=ip, user_agent=user_agent, consent_status=consent
    )

    
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
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400
        
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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='AI / Technology', message=message, source_form=f"AI Form ({source_page})",
        source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term='', utm_content='',
        referrer=referrer, ip_address=ip or 'unknown', user_agent=user_agent, consent_status=consent
    )
    
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
        
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400
        
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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='Manufacturing', message=f"Area of Interest: {area_of_interest}\nMessage: {message}",
        source_form=f"Manufacturing Form ({source_page})",
        source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term=utm_term, utm_content=utm_content,
        referrer=referrer, ip_address=ip or 'unknown', user_agent=user_agent, consent_status=consent
    )
    
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
        
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400

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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='BFSI', message=f"Area of Interest: {area_of_interest}\nMessage: {message}",
        source_form=f"BFSI Form ({source_page})",
        source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term=utm_term, utm_content=utm_content,
        referrer=referrer, ip_address=ip_address or 'unknown', user_agent=user_agent, consent_status=consent
    )
    
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
        
    if not is_corporate_email(email):
        return jsonify({'status': 'error', 'message': 'Please use your official company business email address. Gmail/Yahoo/Outlook and other personal domains are not accepted.'}), 400
        
    if phone and not validate_phone_number(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format or test number detected.'}), 400

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
    
    # Forward to CRM
    forward_to_crm_wrapper(
        email=email, first_name=first_name, last_name=last_name, company=company, phone=phone, job_title=job_title,
        geography='', country=country, industry='Retail', message=f"Area of Interest: {area_of_interest}\nMessage: {message}",
        source_form=f"Retail Form ({source_page})",
        source_page=source_page, cta_clicked=cta_clicked, lead_source='Website',
        utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign, utm_term=utm_term, utm_content=utm_content,
        referrer=referrer, ip_address=ip_address or 'unknown', user_agent=user_agent, consent_status=consent
    )
    
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

@app.route('/admin/tokens')
def admin_tokens():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    sync_token_usage()
    
    conn = get_db_connection()
    # Get aggregated stats
    try:
        totals = conn.execute("""
            SELECT 
                SUM(user_tokens) as user_total,
                SUM(system_tokens) as system_total,
                SUM(completion_tokens) as completion_total,
                SUM(thinking_tokens) as thinking_total
            FROM token_usage
        """).fetchone()
    except Exception:
        totals = None
        
    user_tot = totals['user_total'] if (totals and totals['user_total'] is not None) else 0
    sys_tot = totals['system_total'] if (totals and totals['system_total'] is not None) else 0
    comp_tot = totals['completion_total'] if (totals and totals['completion_total'] is not None) else 0
    think_tot = totals['thinking_total'] if (totals and totals['thinking_total'] is not None) else 0
    grand_total = user_tot + sys_tot + comp_tot + think_tot
    
    # Breakdown by category
    try:
        categories = conn.execute("""
            SELECT 
                category,
                SUM(user_tokens) as user_total,
                SUM(system_tokens) as system_total,
                SUM(completion_tokens) as completion_total,
                SUM(thinking_tokens) as thinking_total,
                SUM(user_tokens + system_tokens + completion_tokens + thinking_tokens) as total
            FROM token_usage
            GROUP BY category
            ORDER BY total DESC
        """).fetchall()
    except Exception:
        categories = []
        
    # Recent activity
    try:
        recent_activity = conn.execute("""
            SELECT 
                step_index,
                timestamp,
                category,
                user_tokens,
                system_tokens,
                completion_tokens,
                thinking_tokens,
                (user_tokens + system_tokens + completion_tokens + thinking_tokens) as total_tokens
            FROM token_usage
            ORDER BY step_index DESC
            LIMIT 15
        """).fetchall()
    except Exception:
        recent_activity = []
        
    conn.close()
    
    return render_template(
        'admin_tokens.html',
        grand_total=int(grand_total),
        user_tot=int(user_tot),
        sys_tot=int(sys_tot),
        comp_tot=int(comp_tot),
        think_tot=int(think_tot),
        categories=categories,
        recent_activity=recent_activity
    )

@app.route('/admin/tokens/data')
def admin_tokens_data():
    if not check_admin_auth():
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT 
                substr(timestamp, 1, 10) as date_val,
                category,
                SUM(user_tokens) as user_tot,
                SUM(system_tokens) as system_tot,
                SUM(completion_tokens) as completion_tot,
                SUM(thinking_tokens) as thinking_tot
            FROM token_usage
            GROUP BY date_val, category
            ORDER BY date_val ASC
        """).fetchall()
    except Exception as e:
        rows = []
        
    conn.close()
    
    data = []
    for r in rows:
        data.append({
            'date': r['date_val'],
            'category': r['category'],
            'user_tokens': r['user_tot'] or 0,
            'system_tokens': r['system_tot'] or 0,
            'completion_tokens': r['completion_tot'] or 0,
            'thinking_tokens': r['thinking_tot'] or 0,
            'total_tokens': (r['user_tot'] or 0) + (r['system_tot'] or 0) + (r['completion_tot'] or 0) + (r['thinking_tot'] or 0)
        })
        
    return jsonify(data)


# ==========================================================================
# SEO & AEO Admin Control Center Routes
# ==========================================================================

def run_publishing_quality_gate(p):
    results = {
        'critical': [],
        'warning': [],
        'opportunity': []
    }
    
    # 1. Title checks
    title = p.get('seo_title', '') or ''
    if not title:
        results['critical'].append("Missing SEO Title tag")
    elif len(title) < 10:
        results['critical'].append("SEO Title is extremely short")
    elif len(title) < 30 or len(title) > 65:
        results['warning'].append(f"SEO Title length is {len(title)} chars (recommended 30-65)")
        
    if title and any(kw in title.lower() for kw in ['todo', 'placeholder', 'draft', '[', ']']):
        results['warning'].append("SEO Title contains placeholder text")
        
    # 2. Meta description checks
    desc = p.get('meta_description', '') or ''
    if not desc:
        results['critical'].append("Missing meta description")
    elif len(desc) < 70 or len(desc) > 160:
        results['warning'].append(f"Description length is {len(desc)} chars (recommended 70-160)")
        
    if desc and any(kw in desc.lower() for kw in ['todo', 'placeholder', 'draft', '[', ']']):
        results['warning'].append("Meta description contains placeholder text")
        
    # 3. H1 checks
    h1 = p.get('h1', '') or ''
    if not h1:
        results['warning'].append("Missing H1 heading override")
    elif any(kw in h1.lower() for kw in ['todo', 'placeholder', 'draft', '[', ']']):
        results['warning'].append("H1 heading contains placeholder text")
        
    # 4. Canonical checks
    canonical = p.get('canonical_url', '') or ''
    if canonical and not (canonical.startswith('http://') or canonical.startswith('https://')):
        results['warning'].append("Canonical URL must be absolute (starting with http/https)")
        
    # 5. Schema validation
    schema = p.get('schema_json', '') or ''
    if schema:
        try:
            parsed = json.loads(schema)
            if not parsed.get('@context'):
                results['warning'].append("Custom schema JSON-LD is missing '@context'")
            if not parsed.get('@type'):
                results['warning'].append("Custom schema JSON-LD is missing '@type'")
        except Exception:
            results['warning'].append("Custom Schema is not valid JSON-LD format")
            
    # 6. E-E-A-T authorship warnings
    if not p.get('author_name'):
        results['warning'].append("Missing Author name for E-E-A-T trust signals")
    if not p.get('reviewer_name'):
        results['warning'].append("Missing Subject-matter reviewer for E-E-A-T trust signals")
    if not p.get('last_reviewed_date'):
        results['warning'].append("Missing Last reviewed date")
        
    # 7. AEO / GEO quick answer checks
    quick_ans = p.get('aeo_quick_answer', '') or ''
    if not quick_ans:
        results['opportunity'].append("Missing AEO Quick Answer block")
    else:
        words = len(quick_ans.split())
        if words < 40 or words > 80:
            results['opportunity'].append(f"Quick Answer is {words} words (recommended 40-80)")
        if any(ph in quick_ans.lower() for ph in ['[audience]', '[problem]', 'todo']):
            results['opportunity'].append("Quick Answer contains unresolved template/placeholder brackets")
            
    # 8. Key facts checks
    key_facts = p.get('aeo_key_facts', '') or ''
    if not key_facts or key_facts in ('[]', 'None'):
        results['opportunity'].append("Key Facts grid is empty")
    else:
        try:
            facts = json.loads(key_facts)
            if not isinstance(facts, list) or len(facts) == 0:
                results['opportunity'].append("Key Facts is empty or not an array")
        except Exception:
            results['opportunity'].append("Key Facts is not valid JSON array format")
            
    # 9. FAQ / Conversational QA checks
    questions = p.get('aeo_questions', '') or ''
    if not questions or questions in ('[]', 'None'):
        results['opportunity'].append("FAQ QA Accordion list is empty")
    else:
        try:
            q_list = json.loads(questions)
            if not isinstance(q_list, list) or len(q_list) < 4:
                results['opportunity'].append(f"Conversational QA has only {len(q_list) if isinstance(q_list, list) else 0} items (recommended 4-8)")
        except Exception:
            results['opportunity'].append("Conversational QA is not valid JSON array format")
            
    return results

def calculate_page_scores(page):
    # Dynamic SEO Score calculations
    seo = 0
    if page.get('seo_title'): seo += 20
    if page.get('meta_description'):
        desc_len = len(page['meta_description'])
        if 70 <= desc_len <= 160: seo += 20
        else: seo += 10
    if page.get('canonical_url'): seo += 15
    if page.get('h1'): seo += 15
    if page.get('schema_json'): seo += 15
    if page.get('robots_directive'): seo += 10
    if page.get('sitemap_inclusion') == 1: seo += 5
    
    # Dynamic AEO Score calculations
    aeo = 0
    if page.get('aeo_quick_answer'):
        ans_len = len(page['aeo_quick_answer'].split())
        if 40 <= ans_len <= 80: aeo += 30
        else: aeo += 15
    if page.get('aeo_key_facts'):
        try:
            facts = json.loads(page['aeo_key_facts'])
            if len(facts) > 0: aeo += 20
        except Exception:
            pass
    if page.get('aeo_questions'):
        try:
            qs = json.loads(page['aeo_questions'])
            if len(qs) >= 4: aeo += 30
            elif len(qs) > 0: aeo += 15
        except Exception:
            pass
    if page.get('author_name') or page.get('reviewer_name'): aeo += 10
    if page.get('last_reviewed_date'): aeo += 10
    
    return seo, aeo

@app.route('/admin/seo')
def admin_seo_dashboard():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages_count = conn.execute("SELECT COUNT(*) FROM seo_pages").fetchone()[0]
    redirects_count = conn.execute("SELECT COUNT(*) FROM seo_redirects").fetchone()[0]
    
    # Calculate average scores
    scores_row = conn.execute("SELECT AVG(seo_score) as avg_seo, AVG(aeo_score) as avg_aeo FROM seo_pages").fetchone()
    avg_seo = int(scores_row['avg_seo'] or 0)
    avg_aeo = int(scores_row['avg_aeo'] or 0)
    
    # Crawlers policy status
    crawlers_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'robots_policy'").fetchone()
    crawlers = json.loads(crawlers_row['value']) if crawlers_row else {}
    
    gptbot_allowed = crawlers.get('GPTBot', {}).get('allowed', False)
    searchbot_allowed = crawlers.get('OAI-SearchBot', {}).get('allowed', True)
    
    # Fetch recent audits
    recent_audits = conn.execute("SELECT * FROM seo_audits ORDER BY id DESC LIMIT 5").fetchall()
    
    # IndexNow key
    key_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'indexnow_key'").fetchone()
    indexnow_key = key_row['value'] if key_row else ''
    
    conn.close()
    
    return render_template(
        'admin/seo/dashboard.html',
        pages_count=pages_count,
        redirects_count=redirects_count,
        avg_seo=avg_seo,
        avg_aeo=avg_aeo,
        gptbot_allowed=gptbot_allowed,
        searchbot_allowed=searchbot_allowed,
        recent_audits=recent_audits,
        indexnow_key=indexnow_key
    )

@app.route('/admin/seo/audit', methods=['GET', 'POST'])
def admin_seo_audit():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    
    # Pre-sync dynamic pages: Ensure all posts, case studies, jobs, and microsite pages have seo_pages records
    posts = conn.execute("SELECT slug, title FROM posts WHERE status = 'Published'").fetchall()
    for p in posts:
        slug = f"/blogs/{p['slug']}"
        conn.execute("""
            INSERT OR IGNORE INTO seo_pages (route_slug, seo_title, meta_description, canonical_url, h1, robots_directive, sitemap_inclusion, sitemap_priority, content_status)
            VALUES (?, ?, ?, ?, ?, 'index, follow', 1, 0.6, 'Published')
        """, (slug, f"{p['title']} | Artha Solutions Blog", f"Read our latest article: {p['title']}.", f"https://www.thinkartha.com{slug}", p['title']))
        
    studies = conn.execute("SELECT slug, title, card_summary FROM case_studies WHERE status = 'Published'").fetchall()
    for s in studies:
        slug = f"/case-studies/{s['slug']}"
        conn.execute("""
            INSERT OR IGNORE INTO seo_pages (route_slug, seo_title, meta_description, canonical_url, h1, robots_directive, sitemap_inclusion, sitemap_priority, content_status)
            VALUES (?, ?, ?, ?, ?, 'index, follow', 1, 0.7, 'Published')
        """, (slug, f"{s['title']} | ThinkArtha Case Studies", s['card_summary'] or f"Case study detail for: {s['title']}.", f"https://www.thinkartha.com{slug}", s['title']))
        
    jobs = conn.execute("SELECT slug, title, summary FROM career_jobs WHERE status = 'published'").fetchall()
    for j in jobs:
        slug = f"/careers/{j['slug']}"
        conn.execute("""
            INSERT OR IGNORE INTO seo_pages (route_slug, seo_title, meta_description, canonical_url, h1, robots_directive, sitemap_inclusion, sitemap_priority, content_status)
            VALUES (?, ?, ?, ?, ?, 'index, follow', 1, 0.5, 'Published')
        """, (slug, f"{j['title']} Careers Opportunity | Artha Solutions", j['summary'] or f"Job position detail for: {j['title']}.", f"https://www.thinkartha.com{slug}", j['title']))
        
    microsites = conn.execute("SELECT url, title, seo_title, seo_description FROM industry_microsite_pages WHERE status = 'Published'").fetchall()
    for m in microsites:
        conn.execute("""
            INSERT OR IGNORE INTO seo_pages (route_slug, seo_title, meta_description, canonical_url, h1, robots_directive, sitemap_inclusion, sitemap_priority, content_status)
            VALUES (?, ?, ?, ?, ?, 'index, follow', 1, 0.8, 'Published')
        """, (m['url'], m['seo_title'] or f"{m['title']} | Artha Solutions", m['seo_description'] or f"Dynamic industry page for {m['title']}.", f"https://www.thinkartha.com{m['url']}", m['title']))

    conn.commit()
    
    if request.method == 'POST':
        # Perform live audit / score recalculation over all routes
        all_pages = conn.execute("SELECT * FROM seo_pages").fetchall()
        
        pages_audited = len(all_pages)
        total_seo = 0
        total_aeo = 0
        critical_errors = 0
        warnings = 0
        opportunities = 0
        results = []
        
        for p in all_pages:
            p_dict = dict(p)
            seo_score, aeo_score = calculate_page_scores(p_dict)
            
            # Update individual page scores in DB
            conn.execute("UPDATE seo_pages SET seo_score = ?, aeo_score = ? WHERE id = ?", (seo_score, aeo_score, p['id']))
            
            # Collect details of issues via Quality Gate
            gate_results = run_publishing_quality_gate(p_dict)
            critical_errors += len(gate_results['critical'])
            warnings += len(gate_results['warning'])
            opportunities += len(gate_results['opportunity'])
            issues = gate_results['critical'] + gate_results['warning'] + gate_results['opportunity']
                
            total_seo += seo_score
            total_aeo += aeo_score
            
            results.append({
                'path': p['route_slug'],
                'seo_score': seo_score,
                'aeo_score': aeo_score,
                'issues': issues
            })
            
        conn.commit()
        
        health_score = int(total_seo / pages_audited) if pages_audited > 0 else 0
        aeo_avg = int(total_aeo / pages_audited) if pages_audited > 0 else 0
        
        # Save audit report
        conn.execute("""
            INSERT INTO seo_audits 
            (run_date, health_score, technical_score, content_score, schema_score, page_exp_score, aeo_score, pages_audited, critical_errors, warnings, opportunities, audit_results_json)
            VALUES (?, ?, ?, ?, ?, 80, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            health_score, health_score, health_score, health_score, aeo_avg,
            pages_audited, critical_errors, warnings, opportunities, json.dumps(results)
        ))
        conn.commit()
        
        conn.close()
        return redirect('/admin/seo')
        
    recent_audits = conn.execute("SELECT * FROM seo_audits ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return render_template('admin/seo/audit.html', audits=recent_audits)

@app.route('/admin/seo/pages')
def admin_seo_pages():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    pages = conn.execute("SELECT * FROM seo_pages ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin/seo/pages.html', pages=pages)

@app.route('/admin/seo/pages/edit/<int:page_id>', methods=['GET', 'POST'])
def admin_seo_page_edit(page_id):
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM seo_pages WHERE id = ?", (page_id,)).fetchone()
    
    if not page:
        conn.close()
        abort(404)
        
    page = dict(page)
    
    # Quality gate checks on validation warnings
    warnings_list = []
    
    if request.method == 'POST':
        seo_title = request.form.get('seo_title', '').strip()
        meta_description = request.form.get('meta_description', '').strip()
        canonical_url = request.form.get('canonical_url', '').strip()
        h1 = request.form.get('h1', '').strip()
        breadcrumb_title = request.form.get('breadcrumb_title', '').strip()
        og_title = request.form.get('og_title', '').strip()
        og_description = request.form.get('og_description', '').strip()
        og_image = request.form.get('og_image', '').strip()
        robots_directive = request.form.get('robots_directive', 'index, follow').strip()
        sitemap_inclusion = int(request.form.get('sitemap_inclusion', 1))
        sitemap_priority = float(request.form.get('sitemap_priority', 0.5))
        schema_json = request.form.get('schema_json', '').strip()
        aeo_quick_answer = request.form.get('aeo_quick_answer', '').strip()
        aeo_key_facts = request.form.get('aeo_key_facts', '[]').strip()
        aeo_questions = request.form.get('aeo_questions', '[]').strip()
        author_name = request.form.get('author_name', '').strip()
        author_role = request.form.get('author_role', '').strip()
        author_expertise = request.form.get('author_expertise', '').strip()
        reviewer_name = request.form.get('reviewer_name', '').strip()
        reviewer_role = request.form.get('reviewer_role', '').strip()
        reviewer_expertise = request.form.get('reviewer_expertise', '').strip()
        last_reviewed_date = request.form.get('last_reviewed_date', '').strip()
        content_status = request.form.get('content_status', 'Draft').strip()
        
        # Compile page data dictionary
        p_dict = {
            'seo_title': seo_title, 'meta_description': meta_description, 'canonical_url': canonical_url,
            'h1': h1, 'schema_json': schema_json, 'robots_directive': robots_directive,
            'sitemap_inclusion': sitemap_inclusion, 'sitemap_priority': sitemap_priority,
            'aeo_quick_answer': aeo_quick_answer, 'aeo_key_facts': aeo_key_facts, 'aeo_questions': aeo_questions,
            'author_name': author_name, 'author_role': author_role, 'author_expertise': author_expertise,
            'reviewer_name': reviewer_name, 'reviewer_role': reviewer_role, 'reviewer_expertise': reviewer_expertise,
            'last_reviewed_date': last_reviewed_date
        }
        
        # Validations (Quality Gates)
        gate_results = run_publishing_quality_gate(p_dict)
        warnings_list = gate_results['critical'] + gate_results['warning'] + gate_results['opportunity']
        
        seo_score, aeo_score = calculate_page_scores(p_dict)
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("""
            UPDATE seo_pages 
            SET seo_title = ?, meta_description = ?, canonical_url = ?, h1 = ?, breadcrumb_title = ?,
                og_title = ?, og_description = ?, og_image = ?, robots_directive = ?, sitemap_inclusion = ?,
                sitemap_priority = ?, schema_json = ?, aeo_quick_answer = ?, aeo_key_facts = ?, aeo_questions = ?,
                author_name = ?, author_role = ?, author_expertise = ?, reviewer_name = ?, reviewer_role = ?,
                reviewer_expertise = ?, last_reviewed_date = ?, content_status = ?, seo_score = ?, aeo_score = ?,
                last_updated = ?, updated_at = ?
            WHERE id = ?
        """, (
            seo_title, meta_description, canonical_url, h1, breadcrumb_title,
            og_title, og_description, og_image, robots_directive, sitemap_inclusion,
            sitemap_priority, schema_json, aeo_quick_answer, aeo_key_facts, aeo_questions,
            author_name, author_role, author_expertise, reviewer_name, reviewer_role,
            reviewer_expertise, last_reviewed_date, content_status, seo_score, aeo_score,
            now_str, now_str, page_id
        ))
        conn.commit()
        
        # Trigger IndexNow automatically if page is Published
        if content_status == 'Published':
            full_url = f"https://www.thinkartha.com{page['route_slug']}"
            submit_to_indexnow(full_url, action='update')
            
        conn.close()
        
        if warnings_list:
            # Re-read page record and render edit view with errors
            conn = get_db_connection()
            page = conn.execute("SELECT * FROM seo_pages WHERE id = ?", (page_id,)).fetchone()
            page = dict(page)
            conn.close()
            return render_template('admin/seo/page_edit.html', page=page, errors=warnings_list, success=True)
            
        return redirect('/admin/seo/pages')
        
    conn.close()
    return render_template('admin/seo/page_edit.html', page=page)

@app.route('/admin/seo/redirects', methods=['GET', 'POST'])
def admin_seo_redirects():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        source = request.form.get('source_path', '').strip()
        target = request.form.get('target_path', '').strip()
        code = int(request.form.get('redirect_type', 301))
        
        if source and target:
            try:
                conn.execute("""
                    INSERT INTO seo_redirects (source_path, target_path, redirect_type, is_active)
                    VALUES (?, ?, ?, 1)
                """, (source, target, code))
                conn.commit()
            except Exception as e:
                print(f"Error adding redirect: {e}")
                
        return redirect('/admin/seo/redirects')
        
    redirects = conn.execute("SELECT * FROM seo_redirects ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin/seo/redirects.html', redirects=redirects)

@app.route('/admin/seo/redirects/delete/<int:r_id>')
def admin_seo_redirect_delete(r_id):
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    conn.execute("DELETE FROM seo_redirects WHERE id = ?", (r_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/seo/redirects')

@app.route('/admin/seo/crawlers', methods=['GET', 'POST'])
def admin_seo_crawlers():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        google_verification = request.form.get('google_verification', '').strip()
        bing_verification = request.form.get('bing_verification', '').strip()
        
        gptbot_allowed = request.form.get('gptbot_allowed') == '1'
        searchbot_allowed = request.form.get('searchbot_allowed') == '1'
        
        policy = {
            'Googlebot': {'allowed': True, 'crawl_delay': None},
            'Bingbot': {'allowed': True, 'crawl_delay': None},
            'OAI-SearchBot': {'allowed': searchbot_allowed, 'crawl_delay': None},
            'GPTBot': {'allowed': gptbot_allowed, 'crawl_delay': None},
            '*': {'allowed': True, 'crawl_delay': None}
        }
        
        conn.execute("INSERT OR REPLACE INTO seo_settings (key, value) VALUES ('google_verification', ?)", (google_verification,))
        conn.execute("INSERT OR REPLACE INTO seo_settings (key, value) VALUES ('bing_verification', ?)", (bing_verification,))
        conn.execute("INSERT OR REPLACE INTO seo_settings (key, value) VALUES ('robots_policy', ?)", (json.dumps(policy),))
        conn.commit()
        
        return redirect('/admin/seo/crawlers')
        
    # Fetch current
    g_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'google_verification'").fetchone()
    b_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'bing_verification'").fetchone()
    p_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'robots_policy'").fetchone()
    conn.close()
    
    google_verification = g_row['value'] if g_row else ''
    bing_verification = b_row['value'] if b_row else ''
    policy = json.loads(p_row['value']) if p_row else {}
    
    gptbot_allowed = policy.get('GPTBot', {}).get('allowed', False)
    searchbot_allowed = policy.get('OAI-SearchBot', {}).get('allowed', True)
    
    return render_template(
        'admin/seo/crawlers.html',
        google_verification=google_verification,
        bing_verification=bing_verification,
        gptbot_allowed=gptbot_allowed,
        searchbot_allowed=searchbot_allowed
    )

@app.route('/admin/seo/indexnow', methods=['GET', 'POST'])
def admin_seo_indexnow():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        action_type = request.form.get('action_type', 'update')
        url = request.form.get('url', '').strip()
        if url:
            submit_to_indexnow(url, action=action_type)
        return redirect('/admin/seo/indexnow')
        
    logs = conn.execute("SELECT * FROM seo_indexnow_logs ORDER BY id DESC LIMIT 50").fetchall()
    key_row = conn.execute("SELECT value FROM seo_settings WHERE key = 'indexnow_key'").fetchone()
    conn.close()
    
    indexnow_key = key_row['value'] if key_row else ''
    
    return render_template(
        'admin/seo/indexnow.html',
        logs=logs,
        indexnow_key=indexnow_key
    )

@app.route('/admin/seo/analytics')
def admin_seo_analytics():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    
    # Traffic metrics breakdown
    summary = conn.execute("""
        SELECT 
            referral_type, 
            COUNT(*) as total_visits, 
            SUM(converted) as total_conversions
        FROM seo_traffic_logs
        GROUP BY referral_type
    """).fetchall()
    
    recent_traffic = conn.execute("""
        SELECT * FROM seo_traffic_logs ORDER BY id DESC LIMIT 50
    """).fetchall()
    
    conn.close()
    return render_template('admin/seo/analytics.html', summary=summary, traffic=recent_traffic)

@app.route('/admin/seo/performance')
def admin_seo_performance():
    if not check_admin_auth():
        return redirect('/admin/login')
        
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM seo_settings WHERE key = 'performance_budget'").fetchone()
    conn.close()
    
    budget = json.loads(row['value']) if row else {}
    return render_template('admin/seo/performance.html', budget=budget)


# Custom 404 Handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', active_page='none'), 404

init_notification_scheduler(app)

if __name__ == '__main__':
    debug_enabled = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5050)))
    app.run(debug=debug_enabled, use_reloader=False, host=host, port=port)
