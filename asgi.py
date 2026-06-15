from a2wsgi import WSGIMiddleware
from fastapi import FastAPI

from app import app as flask_app
from crm.fastapi_backend import crm_router, telecrm_router

app = FastAPI(
    title="ThinkArtha CRM and TeleCRM Backend",
    version="1.0.0",
    description=(
        "Native FastAPI backend for CRM and TeleCRM APIs, with the existing "
        "Flask website and admin application mounted for compatibility."
    ),
    docs_url="/api/v2/docs",
    redoc_url="/api/v2/redoc",
    openapi_url="/api/v2/openapi.json",
)


@app.get("/api/v2/health", tags=["System"])
def health() -> dict[str, bool | str]:
    return {
        "status": "ok",
        "backend": "fastapi",
        "legacy_flask_mounted": True,
    }


app.include_router(crm_router)
app.include_router(telecrm_router)

# Keep the public website, admin screens, and legacy Flask CRM/TeleCRM routes
# available while the CRM backend moves to native FastAPI endpoints.
app.mount("/", WSGIMiddleware(flask_app))
