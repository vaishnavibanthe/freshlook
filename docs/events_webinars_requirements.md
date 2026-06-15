# Events and Webinars Module Requirements

## Purpose

ThinkArtha.com uses one unified Events and Webinars module for live webinars, on-demand webinars, conferences, summits, workshops, partner events, virtual events, hybrid events, and in-person events.

Admins should not manage these as separate modules. The production admin surface is:

- `/admin/events` for listing, filtering, lifecycle actions, registration access, and exports.
- `/admin/events/new` for unified creation.
- `/admin/events/<id>/edit` for unified editing.

Public routes are:

- `/events`
- `/events/<slug>`
- `/events/webinars/<slug>`
- `/events/webinars/on-demand/<slug>`
- `/api/events`
- `/api/events/<slug>`
- `/api/events/<slug>/register`

## Content Model

The canonical content record is `event_webinars`.

Required top-level fields:

- `content_type`: `Webinar` or `Event`
- `webinar_format`: `Live Webinar` or `On-Demand Webinar`, for webinars
- `event_format`: `Conference`, `Summit`, `Workshop`, `Roundtable`, `Partner Event`, `In-Person Event`, `Virtual Event`, or `Hybrid Event`, for events
- `title`
- `slug`
- `short_description`
- `full_description`
- `theme`
- `topic_category`
- `start_datetime`
- `end_datetime`
- `timezone`
- `location_type`
- `publishing_status`
- `lifecycle_status`

Related editable tables:

- `event_speakers`
- `event_agenda_items`
- `event_key_takeaways`
- `event_registrations`
- `event_activity_log`

## Admin Requirements

The admin must support one create/edit experience for both Events and Webinars.

The form must expose:

- Content type, format, lifecycle, publishing status, and event label
- Title, slug, theme, topic/category, tags, short description, full description
- Who should attend, why attend, and public highlight card content
- Date, start time, end time, timezone, display time text, location type, and location
- Registration settings, CTA text, thank-you message, capacity, close datetime, business-email-only mode, and CRM integration flag
- Live join link, external event link, recording link, recording duration, recording access type, embed code, and auto-convert setting
- Speakers with image, alt text, designation, company, bio, LinkedIn URL, and display order
- Agenda items with day number, start/end time, session title, track, and description
- Key takeaways
- Hero image, featured/card image, partner/sponsor logo, related URLs, resource URL, custom CTA, SEO, Open Graph, AEO summary, and schema JSON-LD

## Lifecycle Rules

Live webinars can become on-demand webinars.

When a webinar is converted to on-demand:

- `webinar_format` becomes `On-Demand Webinar`
- `lifecycle_status` becomes `On-Demand`
- `live_join_link` is cleared
- `recording_link` is required
- Registration CTA defaults to `Watch On-Demand`
- Registration success redirects to the recording link when `recording_access_type = redirect`
- Activity is logged in `event_activity_log`

Automatic lifecycle update:

- If a live webinar has ended and `auto_convert_to_ondemand = 1` and `recording_link` exists, it converts to on-demand.
- If a live webinar has ended and no recording link exists, it moves to `Completed`.
- Completed live webinars without recordings are surfaced in admin as needing recording.

## Frontend Rendering

Event and webinar public pages render from the unified backend data.

Live webinar pages show:

- Webinar label
- Title and short description
- Date/time card
- Registration form
- Speakers
- Agenda/topics
- Key takeaways
- Highlight card

On-demand webinar pages show:

- On-demand label
- Title and short description
- Recording duration
- Access form
- Speakers
- Agenda/topics covered
- Key takeaways
- Highlight card

Event pages show:

- Event label
- Title
- Date, time, location
- Countdown for upcoming events
- Registration CTA/form
- Featured speakers
- Agenda/timeline
- Key takeaways
- Highlight card

## Registration Requirements

One registration endpoint handles all content types:

- `POST /api/events/<slug>/register`

Stored registration fields include:

- Name, business email, company, job title, phone, country
- How the registrant heard about ThinkArtha
- Consent status
- Attendee status
- Source page, referrer, UTM values
- CRM Website Lead ID
- IP address and user agent
- Registration and recording-access timestamps

Validation:

- First name, last name, business email, company, and consent are required.
- Business email format is validated server-side.
- Personal email domains are blocked when business-email-only mode is enabled.
- Phone is optional, but validated when provided.
- Honeypot and in-memory rate limiting protect the public endpoint.

CRM mapping:

- Event registration: `source_form = Event Registration`
- Live webinar registration: `source_form = Live Webinar Registration`
- On-demand webinar access: `source_form = On-Demand Webinar Registration`

Registrations create Website Leads in CRM staging when CRM integration is enabled.

## SEO and Indexing

Published pages can be included in sitemap output.

Draft and archived records must not be indexed.

Each record supports:

- SEO title
- SEO description
- Canonical URL
- Open Graph title
- Open Graph description
- Open Graph image
- AI summary
- Schema JSON-LD

Structured data must match visible page content.

## Migration and Backfill

Legacy `events` and `webinars` tables are preserved for compatibility.

For existing environments:

```bash
python3 migrate_events_unified.py
python3 sync_event_admin_content.py --overwrite
python3 sync_event_admin_content.py --check
```

`migrate_events_unified.py` moves legacy rows into `event_webinars`.

`sync_event_admin_content.py` backfills editable admin content that used to be hard-coded at render time:

- Speakers
- Agenda
- Key takeaways
- Themes
- Topic categories
- Display time text
- Card and hero images
- Public highlight card title, text, and link
- SEO/Open Graph defaults

## Production Verification

Run these before deployment:

```bash
python3 -m py_compile app.py init_db.py migrate_events_unified.py sync_event_admin_content.py
python3 sync_event_admin_content.py --check
```

Run the Flask route mapping check:

```bash
python3 - <<'PY'
import html
import sqlite3
import app

client = app.app.test_client()
with client.session_transaction() as sess:
    sess['logged_in'] = True
    sess['username'] = 'admin'

conn = sqlite3.connect('blog.db')
conn.row_factory = sqlite3.Row
failures = []

for row in conn.execute('SELECT * FROM event_webinars ORDER BY id').fetchall():
    event = dict(row)
    admin_res = client.get(f"/admin/events/{event['id']}/edit")
    public_res = client.get(app.event_public_url(event))
    admin_html = html.unescape(admin_res.get_data(as_text=True))
    public_html = html.unescape(public_res.get_data(as_text=True))

    speaker = conn.execute('SELECT name FROM event_speakers WHERE event_id=? ORDER BY display_order LIMIT 1', (event['id'],)).fetchone()['name']
    agenda = conn.execute('SELECT session_title FROM event_agenda_items WHERE event_id=? ORDER BY display_order LIMIT 1', (event['id'],)).fetchone()['session_title']
    takeaway = conn.execute('SELECT takeaway_text FROM event_key_takeaways WHERE event_id=? ORDER BY display_order LIMIT 1', (event['id'],)).fetchone()['takeaway_text']
    highlight = event.get('highlight_title') or ''

    checks = [
        admin_res.status_code == 200,
        public_res.status_code == 200,
        speaker in admin_html and speaker in public_html,
        agenda in admin_html and agenda in public_html,
        takeaway in admin_html and takeaway in public_html,
        highlight in admin_html and highlight in public_html,
    ]
    if not all(checks):
        failures.append(event['slug'])

conn.close()

if failures:
    raise SystemExit(f"Mapping failures: {failures}")

print("All admin/public mapping checks passed.")
PY
```

## Acceptance Criteria

- `/admin/events` is the single admin listing for events and webinars.
- One create/edit form supports Events, Live Webinars, and On-Demand Webinars.
- Admin content maps to the public page without hidden render-time content.
- All records have editable speakers, agenda, key takeaways, highlight card content, images, theme, and SEO fields.
- Live webinars can be converted to on-demand only with a recording link.
- On-demand registration can redirect to the recording link after submission.
- Registrations are stored, exportable, and optionally forwarded into CRM Website Leads staging.
- Draft and archived records are kept out of public indexing.
- Migration and sync scripts are idempotent and auditable.
