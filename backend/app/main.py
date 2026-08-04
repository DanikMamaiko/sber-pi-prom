from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.audit.middleware import AuditMiddleware
from app.audit.sink import DatabaseAuditSink, DisabledAuditSink
from app.core.config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.state.audit_sink = (
    DatabaseAuditSink(
        settings.audit_database_url,
        connect_timeout_seconds=settings.audit_connect_timeout_seconds,
        retry_seconds=settings.audit_retry_seconds,
    )
    if settings.audit_enabled
    else DisabledAuditSink()
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware, settings=settings)

app.include_router(api_router)


@app.middleware("http")
async def _cache_control_headers(request: Request, call_next):
    """Запретить браузеру кэшировать ответы API.

    Статику отдаёт nginx, а данные API всегда должны запрашиваться заново.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response
