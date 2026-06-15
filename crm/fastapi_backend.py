import os
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

DB_PATH = os.environ.get("THINKARTHA_DB_PATH", "blog.db")


def require_internal_api_key(authorization: str | None = Header(default=None)) -> None:
    """Optional bearer-token guard for native FastAPI CRM/TeleCRM APIs.

    Set FASTAPI_INTERNAL_API_KEY in production to require:
        Authorization: Bearer <token>

    When unset, endpoints remain open for local compatibility and gradual
    migration behind the same trusted admin network as the legacy Flask app.
    """
    expected = os.environ.get("FASTAPI_INTERNAL_API_KEY")
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def one_value(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def grouped_counts(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> dict[str, int]:
    rows = conn.execute(query, params).fetchall()
    return {str(row[0] or "Unknown"): int(row[1] or 0) for row in rows}


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return one_value(conn, f"SELECT COUNT(*) FROM {table_name}")


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, 200))


crm_router = APIRouter(
    prefix="/api/v2/crm",
    tags=["CRM"],
    dependencies=[Depends(require_internal_api_key)],
)
telecrm_router = APIRouter(
    prefix="/api/v2/telecrm",
    tags=["TeleCRM"],
    dependencies=[Depends(require_internal_api_key)],
)


@crm_router.get("/health")
def crm_health() -> dict[str, Any]:
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        crm_users = table_count(conn, "crm_users")
        conn.close()
        return {"status": "ok", "backend": "fastapi", "module": "crm", "crm_users": crm_users}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"CRM database health check failed: {exc}") from exc


@crm_router.get("/summary")
def crm_summary() -> dict[str, Any]:
    try:
        conn = get_db_connection()
        payload = {
            "status": "ok",
            "backend": "fastapi",
            "totals": {
                "website_leads": table_count(conn, "website_leads"),
                "leads": table_count(conn, "leads"),
                "contacts": table_count(conn, "contacts"),
                "accounts": table_count(conn, "accounts"),
                "opportunities": table_count(conn, "opportunities"),
                "tasks": table_count(conn, "crm_tasks"),
            },
            "website_leads_by_status": grouped_counts(
                conn,
                "SELECT COALESCE(status, 'Unknown'), COUNT(*) FROM website_leads GROUP BY COALESCE(status, 'Unknown')",
            ),
            "opportunities_by_stage": grouped_counts(
                conn,
                "SELECT COALESCE(stage, 'Unknown'), COUNT(*) FROM opportunities GROUP BY COALESCE(stage, 'Unknown')",
            ),
            "open_opportunity_value": one_value(
                conn,
                "SELECT CAST(COALESCE(SUM(estimated_value), 0) AS INTEGER) FROM opportunities WHERE COALESCE(status, 'Open') = 'Open'",
            ),
        }
        conn.close()
        return payload
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"CRM summary failed: {exc}") from exc


@crm_router.get("/website-leads")
def crm_website_leads(
    status: str | None = Query(default=None),
    source_form: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = []
    params: list[Any] = []
    if status:
        filters.append("wl.status = ?")
        params.append(status)
    if source_form:
        filters.append("wl.source_form = ?")
        params.append(source_form)
    if search:
        filters.append("(wl.full_name LIKE ? OR wl.business_email LIKE ? OR wl.company LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(filters) if filters else "1=1"
    limit = clamp_limit(limit)
    try:
        conn = get_db_connection()
        total = one_value(conn, f"SELECT COUNT(*) FROM website_leads wl WHERE {where_clause}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT wl.id, wl.full_name, wl.business_email, wl.company, wl.job_title,
                   wl.phone, wl.country, wl.source_form, wl.source_page,
                   wl.cta_clicked, wl.status, wl.assigned_owner_id,
                   u.name AS owner_name, wl.created_at, wl.updated_at
            FROM website_leads wl
            LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id
            WHERE {where_clause}
            ORDER BY wl.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        conn.close()
        return {"total": total, "limit": limit, "offset": offset, "items": rows_to_dicts(rows)}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Website leads query failed: {exc}") from exc


@crm_router.get("/opportunities")
def crm_opportunities(
    status: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = []
    params: list[Any] = []
    if status:
        filters.append("o.status = ?")
        params.append(status)
    if stage:
        filters.append("o.stage = ?")
        params.append(stage)
    if search:
        filters.append("(o.opportunity_name LIKE ? OR o.company LIKE ? OR o.primary_contact_email LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(filters) if filters else "1=1"
    limit = clamp_limit(limit)
    try:
        conn = get_db_connection()
        total = one_value(conn, f"SELECT COUNT(*) FROM opportunities o WHERE {where_clause}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT o.id, o.opportunity_name, o.company, o.primary_contact_name,
                   o.primary_contact_email, o.stage, o.bucket, o.probability,
                   o.estimated_value, o.currency, o.status, o.owner_id,
                   u.name AS owner_name, o.created_at, o.updated_at
            FROM opportunities o
            LEFT JOIN crm_users u ON o.owner_id = u.id
            WHERE {where_clause}
            ORDER BY o.updated_at DESC, o.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        conn.close()
        return {"total": total, "limit": limit, "offset": offset, "items": rows_to_dicts(rows)}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Opportunities query failed: {exc}") from exc


@telecrm_router.get("/health")
def telecrm_health() -> dict[str, Any]:
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        campaigns = table_count(conn, "telecrm_lists")
        contacts = table_count(conn, "telecrm_contacts")
        conn.close()
        return {
            "status": "ok",
            "backend": "fastapi",
            "module": "telecrm",
            "campaigns": campaigns,
            "contacts": contacts,
        }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"TeleCRM database health check failed: {exc}") from exc


@telecrm_router.get("/summary")
def telecrm_summary() -> dict[str, Any]:
    try:
        conn = get_db_connection()
        payload = {
            "status": "ok",
            "backend": "fastapi",
            "totals": {
                "campaigns": table_count(conn, "telecrm_lists"),
                "contacts": table_count(conn, "telecrm_contacts"),
                "calls": table_count(conn, "telecrm_calls"),
                "meetings": table_count(conn, "telecrm_meetings"),
                "sql_records": table_count(conn, "telecrm_sql"),
                "templates": table_count(conn, "telecrm_templates"),
            },
            "contacts_by_dialing_status": grouped_counts(
                conn,
                "SELECT COALESCE(dialing_status, 'Unknown'), COUNT(*) FROM telecrm_contacts GROUP BY COALESCE(dialing_status, 'Unknown')",
            ),
            "contacts_by_sql_status": grouped_counts(
                conn,
                "SELECT COALESCE(sql_status, 'Unknown'), COUNT(*) FROM telecrm_contacts GROUP BY COALESCE(sql_status, 'Unknown')",
            ),
            "sql_by_status": grouped_counts(
                conn,
                "SELECT COALESCE(status, 'Unknown'), COUNT(*) FROM telecrm_sql GROUP BY COALESCE(status, 'Unknown')",
            ),
        }
        conn.close()
        return payload
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"TeleCRM summary failed: {exc}") from exc


@telecrm_router.get("/campaigns")
def telecrm_campaigns(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = []
    params: list[Any] = []
    if status:
        filters.append("(tl.status = ? OR tl.campaign_status = ?)")
        params.extend([status, status])
    if search:
        filters.append("(tl.name LIKE ? OR tl.campaign_name LIKE ? OR tl.description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(filters) if filters else "1=1"
    limit = clamp_limit(limit)
    try:
        conn = get_db_connection()
        total = one_value(conn, f"SELECT COUNT(*) FROM telecrm_lists tl WHERE {where_clause}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT tl.id, tl.name, tl.campaign_name, tl.description, tl.status,
                   tl.campaign_status, tl.total_contacts, tl.assigned_count,
                   tl.completed_count, tl.overall_completion_percentage,
                   tl.attempted_percentage, tl.finalized_percentage,
                   tl.conversion_percentage, tl.sql_percentage,
                   tl.created_at, tl.updated_at,
                   (SELECT COUNT(*) FROM telecrm_contacts tc WHERE tc.telecrm_list_id = tl.id) AS actual_contacts,
                   (SELECT COUNT(*) FROM telecrm_contacts tc WHERE tc.telecrm_list_id = tl.id AND tc.assigned_telecaller_id IS NOT NULL) AS actual_assigned,
                   (SELECT COUNT(*) FROM telecrm_contacts tc WHERE tc.telecrm_list_id = tl.id AND COALESCE(tc.sql_status, '') != 'Not SQL') AS actual_sql
            FROM telecrm_lists tl
            WHERE {where_clause}
            ORDER BY tl.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        conn.close()
        return {"total": total, "limit": limit, "offset": offset, "items": rows_to_dicts(rows)}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"TeleCRM campaign query failed: {exc}") from exc


@telecrm_router.get("/campaigns/{campaign_id}/summary")
def telecrm_campaign_summary(campaign_id: int) -> dict[str, Any]:
    try:
        conn = get_db_connection()
        campaign = conn.execute("SELECT * FROM telecrm_lists WHERE id = ?", (campaign_id,)).fetchone()
        if not campaign:
            conn.close()
            raise HTTPException(status_code=404, detail="TeleCRM campaign not found.")
        payload = {
            "campaign": dict(campaign),
            "contacts": {
                "total": one_value(conn, "SELECT COUNT(*) FROM telecrm_contacts WHERE telecrm_list_id = ?", (campaign_id,)),
                "assigned": one_value(
                    conn,
                    "SELECT COUNT(*) FROM telecrm_contacts WHERE telecrm_list_id = ? AND assigned_telecaller_id IS NOT NULL",
                    (campaign_id,),
                ),
                "finalized": one_value(
                    conn,
                    "SELECT COUNT(*) FROM telecrm_contacts WHERE telecrm_list_id = ? AND is_finalized = 1",
                    (campaign_id,),
                ),
                "sql": one_value(
                    conn,
                    "SELECT COUNT(*) FROM telecrm_contacts WHERE telecrm_list_id = ? AND COALESCE(sql_status, '') != 'Not SQL'",
                    (campaign_id,),
                ),
            },
            "dialing_status": grouped_counts(
                conn,
                """
                SELECT COALESCE(dialing_status, 'Unknown'), COUNT(*)
                FROM telecrm_contacts
                WHERE telecrm_list_id = ?
                GROUP BY COALESCE(dialing_status, 'Unknown')
                """,
                (campaign_id,),
            ),
            "call_status": grouped_counts(
                conn,
                """
                SELECT COALESCE(call_status, 'Unknown'), COUNT(*)
                FROM telecrm_calls
                WHERE campaign_id = ?
                GROUP BY COALESCE(call_status, 'Unknown')
                """,
                (campaign_id,),
            ),
        }
        conn.close()
        return payload
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"TeleCRM campaign summary failed: {exc}") from exc


@telecrm_router.get("/sql")
def telecrm_sql_records(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = []
    params: list[Any] = []
    if status:
        filters.append("s.status = ?")
        params.append(status)
    if search:
        filters.append("(s.contact_name LIKE ? OR s.email LIKE ? OR s.company LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(filters) if filters else "1=1"
    limit = clamp_limit(limit)
    try:
        conn = get_db_connection()
        total = one_value(conn, f"SELECT COUNT(*) FROM telecrm_sql s WHERE {where_clause}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT s.id, s.contact_name, s.email, s.phone, s.company, s.job_title,
                   s.meeting_status, s.meeting_scheduled_at, s.interest_level,
                   s.lead_quality_rating, s.status, s.assigned_owner_id,
                   u.name AS owner_name, s.created_at, s.updated_at
            FROM telecrm_sql s
            LEFT JOIN crm_users u ON s.assigned_owner_id = u.id
            WHERE {where_clause}
            ORDER BY s.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        conn.close()
        return {"total": total, "limit": limit, "offset": offset, "items": rows_to_dicts(rows)}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"TeleCRM SQL query failed: {exc}") from exc
