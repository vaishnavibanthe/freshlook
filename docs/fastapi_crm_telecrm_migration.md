# FastAPI CRM and TeleCRM Backend Migration

The CRM and TeleCRM backend now has a production ASGI entrypoint at `asgi.py`.
It exposes native FastAPI endpoints for the CRM and TeleCRM data services while
mounting the existing Flask application for public pages, admin pages, and
legacy CRM/TeleCRM browser screens.

## Runtime

Use the ASGI app for production deployment:

```bash
export FLASK_SECRET_KEY="replace-with-deployment-secret"
export FASTAPI_INTERNAL_API_KEY="replace-with-internal-api-token"
.venv/bin/uvicorn asgi:app --host 0.0.0.0 --port 5050
```

`FASTAPI_INTERNAL_API_KEY` is optional for local development. When it is set,
native FastAPI CRM and TeleCRM API requests must include:

```http
Authorization: Bearer <token>
```

## Native FastAPI Endpoints

CRM:

- `GET /api/v2/crm/health`
- `GET /api/v2/crm/summary`
- `GET /api/v2/crm/website-leads`
- `GET /api/v2/crm/opportunities`

TeleCRM:

- `GET /api/v2/telecrm/health`
- `GET /api/v2/telecrm/summary`
- `GET /api/v2/telecrm/campaigns`
- `GET /api/v2/telecrm/campaigns/{campaign_id}/summary`
- `GET /api/v2/telecrm/sql`

System and OpenAPI:

- `GET /api/v2/health`
- `GET /api/v2/docs`
- `GET /api/v2/openapi.json`

## Compatibility Layer

The existing Flask app is mounted under `/` with `WSGIMiddleware`, so these
routes continue to work during the migration:

- Public website routes
- Existing `/crm/*` CRM screens
- Existing `/telecrm/*` TeleCRM screens
- Existing `/api/crm/*`, `/api/telecrm/*`, and `/api/admin/*` legacy endpoints

This lets production switch the server process to FastAPI without breaking the
current UI while CRM and TeleCRM endpoints are migrated module by module.

## Deployment Notes

- Keep `blog.db` in the deployment working directory or set `THINKARTHA_DB_PATH`.
- Keep `FLASK_SECRET_KEY` stable across deploys so existing signed tokens remain
  valid.
- Set `FASTAPI_INTERNAL_API_KEY` in production to protect native backend APIs.
- Use `/api/v2/docs` locally for contract review before wiring frontend calls to
  the new native endpoints.
