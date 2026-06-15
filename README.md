# ThinkArtha Website & TeleCRM Portal

This repository contains the ThinkArtha.com public website, content management system, and integrated TeleCRM application. It serves as an enterprise lead capture portal, recruiter platform, and tele-calling execution workbench.

---

## 🛠️ Tech Stack & Architecture

- **Backend**: Python 3 / Flask
- **Database**: SQLite3 (`blog.db`) with custom URI connection configurations for OneDrive synchronization stability (nolock enabled).
- **Frontend**: HTML5, Vanilla JavaScript, and Custom CSS (`static/css/style.css` and `static/js/main.js`).
- **CRM Integration**: Modular Flask blueprint routes (`crm/routes_crm.py`, `crm/routes_telecrm.py`, `crm/routes_admin.py`).

---

## 📦 Core Modules

### 1. Public Website & Microsites
- **Microsites**: Dedicated layouts for **Healthcare**, **Manufacturing**, **BFSI**, **Retail**, and **Artificial Intelligence** industries.
- **Case Studies Landing Page**: PDF downloads, dynamic tags, and industry client portfolios.
- **Resources**: Events tracker, Webinars, and Whitepapers.
- **Unified Events & Webinars Admin**: One `/admin/events` module for live webinars, on-demand webinars, conferences, partner events, virtual events, and in-person events. Requirements and production checks are documented in [`docs/events_webinars_requirements.md`](docs/events_webinars_requirements.md).

### 2. TeleCRM Portal
A lean, focus-driven system for tele-callers and sales managers:
- **Calling Workbench**: Dynamic contact display, dialing status trackers, next-contact navigation, lost-reason reports, and lead-quality ratings.
- **Campaign Execution**: Allocation of leads, campaign progress tracking, and group-level ownership.
- **Leaderboards**: Ranked telecaller performance displays, tracking first/last calls and call count details.
- **MEDDIC CRM**: Complete integration for Opportunity qualification (Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion).
- **Dynamic Permission Templates**: Access templates mapping role scopes (import/export restrictions, table views, caller actions) to team members.
- **Templates Builder**: Reusable SMS and Email template management panel with dynamic client placeholder tokens.
- **TeleCRM settings**: Manage simulated telephony auto-dialer delay, connector timeout, SMS provider configurations, and group SMTP mapping.
- **Analytics conversion funnel**: Conversion dashboard tracking leads from raw list imports to connected, spoken, scheduled, and SQL converted states.

### 3. Careers Module
- **Job Postings**: DB-backed job details with recruiter ownership mapping.
- **Poster Privacy**: Recruiter details are kept strictly private on the backend and are never exposed via public APIs, page source, or search engine metadata.
- **Application Portal**: Secure drag-and-drop CV/resume upload (restricted to PDF/DOC/DOCX, under 5MB).
- **Recruiter Notifications**: Background threads automatically trigger email alerts to job posters and CC recipients when new applications are submitted.

### 4. Public Web Form Validations
All public web forms feature dual client-side and server-side validation layers:
- **Corporate Domain Check**: Except for job applications, all public forms (Contact Us, Case Study Downloads, Resources, and Industry Leads) reject personal email domains (e.g. Gmail, Yahoo, Outlook) and require official company email IDs.
- **Phone Validation**: Standard E.164 length enforcement (7–15 digits) combined with algorithms to detect and reject generic/repeating digits (e.g. `9999999999`) or sequential patterns of 6+ digits (e.g. `1234567`).
- **Global JS Interceptor**: Implemented via a capture-phase listener on the `document` level to validate submissions before inline/bubble-phase triggers fire, updating UI borders and invoking error toast alerts.

---

## 🗄️ Database Schema Summary (`blog.db`)

Key tables in the database include:
- `leads`: CRM leads captured via website forms.
- `contacts` / `accounts`: Linked customer cards generated from leads.
- `career_jobs`: Recruiter job postings, departments, and notification details.
- `career_applications`: Candidate submission details, resume file paths, and notification statuses.
- `timeline_activities`: Historical action logging for accounts, opportunities, and leads.
- `telecrm_contacts` / `telecrm_campaigns`: Targets for calling campaigns and caller rankings.
- `telecrm_permission_templates`: Profile scopes for dynamic role permissions.
- `telecrm_templates`: SMS and Email templates and placeholder markers.
- `telecrm_sms_logs`: Outgoing text log tracker.
- `telecrm_settings`: Auto-dialer delays, gateways, and group SMTP properties.
- `case_studies` / `case_study_leads`: Metadata, tech stack tag mappings, and PDF download request histories.
- `event_webinars`: Unified Events/Webinars records with lifecycle, publishing, registration, recording, SEO, and highlight-card fields.
- `event_speakers` / `event_agenda_items` / `event_key_takeaways`: Editable child content for public event and webinar detail pages.
- `event_registrations` / `event_activity_log`: Registration capture and admin lifecycle audit history.

---

## 🚀 Recent Implementations & History

1. **TeleCRM Advanced Blueprints**: Seeded database-driven permission profiles, constructed a drag-and-drop SMS/Email templates builder, resolved placeholders via API rendering, added settings panel configurations, and added Lead Source Conversion Funnels inside performance analytics dashboard.
2. **Case Study Landing Pages**: Re-designed Case Study listing pages, dynamic PDF download verification tokens, and background banners.
3. **Careers Module Poster Notifications**: Integrated job-specific recruiter notification fields and backend email wrappers.
4. **Public Site Validation Framework**: Implemented global JavaScript capture-phase interceptors and backend helpers in `app.py`.
5. **Asset Staging**: Committed and synchronized ignored asset folders (`CaseStudies/`, `Logos/`, `WhitePapers/`) containing company PDFs, partner vectors, and client brand marks directly to the GitHub repository.
6. **Unified Events & Webinars Module**: Added one admin create/edit flow for Events, Live Webinars, and On-Demand Webinars; registration capture; CRM Website Lead staging; on-demand conversion; public `/events` listing/detail routes; and admin-mapped speakers, agenda, takeaways, highlight cards, SEO, and lifecycle fields.

---

## 🚦 How to Run & Verify

### 1. Create Virtual Environment
```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Launch Flask Server
```bash
.venv/bin/python app.py
```
*Port default: 5050*

For production-style serving, set a deployment secret and run Gunicorn:
```bash
export FLASK_SECRET_KEY="replace-with-deployment-secret"
.venv/bin/gunicorn app:app
```

### 3. Verify Validations (Automated Tests)
We have a local validation runner verifying both validation logic and exception behaviors:
```bash
.venv/bin/python verify_form_validations.py
```
This tests Contact Us, Careers, Case Study downloads, Whitepaper registrations, and Industry microsite forms against corporate email limits and invalid/test phone formats.

### 4. Verify Events & Webinars Module
```bash
.venv/bin/python -m py_compile app.py init_db.py migrate_events_unified.py sync_event_admin_content.py
.venv/bin/python sync_event_admin_content.py --check
```

For existing databases, run the one-time migration/backfill before launch:
```bash
.venv/bin/python migrate_events_unified.py
.venv/bin/python sync_event_admin_content.py --overwrite
.venv/bin/python sync_event_admin_content.py --check
```
