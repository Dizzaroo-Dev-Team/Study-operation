import importlib
import os
import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.etag import install_etag_middleware
from app.utils.log_sanitize import sfmt
from app.middleware.timing import install_timing_middleware, mount_metrics_endpoint

from app.modules.agreements.aggregator import router as agreements_router
from app.modules.ai.routes import router as ai_router
from app.modules.assistant.routes import router as assistant_router
from app.modules.auth_profiles.routes import router as auth_profiles_router
from app.modules.clinical_workflow.routes import router as clinical_workflow_router
from app.modules.communications.routes import router as communications_router
from app.modules.facilities.routes import router as facilities_router
from app.modules.feasibility.routes import router as feasibility_router
from app.modules.operations.routes import router as operations_router
from app.modules.review_comments.routes import router as review_comments_router
from app.modules.sites.routes import router as sites_router
from app.modules.site_packages import router as site_packages_router
from app.modules.sso import router as sso_router
from app.modules.monitoring.aggregator import router as monitor_router
from app.modules.workflows.router import router as workflows_router
from app.db import init_db
from app.db.mongo import get_mongo_client, close_mongo_client, ensure_mongo_indexes
from app.websocket_manager import manager as ws_manager

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Silence access-log spam from unauthenticated probes hammering the PUBLIC Mailgun
# inbound webhook. They're rejected with 406 by the handler (no valid signature), but
# uvicorn still logs one access line per hit — which floods the log. Real inbound email
# is unaffected (it still processes); only the access-log line for this path is dropped.
class _DropInboundWebhookAccess(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 — logging API name
        args = record.args
        if isinstance(args, (tuple, list)) and len(args) >= 3:
            if "/webhooks/email/inbound" in str(args[2]):
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_DropInboundWebhookAccess())

# -------------------------------------------------
# Application lifespan (startup / shutdown)
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI application...")
    logger.warning(
        "DEPRECATION NOTICE: sites.study_id is deprecated and will be removed. "
        "All Study + Site resolution must use StudySite."
    )

    async def init_services():
        # ---------- PostgreSQL ----------
        try:
            logger.info("Initializing PostgreSQL...")
            await asyncio.wait_for(init_db(), timeout=10)
            logger.info("PostgreSQL initialized")
        except asyncio.TimeoutError:
            logger.exception("PostgreSQL init timed out – continuing startup")
        except Exception as e:
            logger.exception(f"PostgreSQL init failed: {e}")

        try:
            from app.modules.monitoring.aggregator import bootstrap_monitor_tables_at_startup

            logger.info("Ensuring monitoring tables...")
            await asyncio.wait_for(bootstrap_monitor_tables_at_startup(), timeout=30)
            logger.info("Monitoring tables ensured")
        except asyncio.TimeoutError:
            logger.warning("Monitoring table bootstrap timed out – continuing startup")
        except Exception as e:
            logger.warning(f"Monitoring table bootstrap failed: {e} – continuing startup")

        # ---------- MongoDB ----------
        # Block briefly on Mongo index creation so the first request after
        # deploy never pays index-build latency (~50-500ms cold). Wrapped in
        # wait_for so a broken Mongo can't stall startup forever — if it
        # times out, the lazy fire-and-forget path inside get_mongo_db()
        # still runs on first access as a safety net.
        try:
            logger.info("Ensuring MongoDB indexes...")
            await asyncio.wait_for(ensure_mongo_indexes(), timeout=10)
            logger.info("MongoDB indexes ensured")
        except asyncio.TimeoutError:
            logger.warning("MongoDB index ensure timed out – continuing startup")
        except Exception as e:
            logger.warning(f"MongoDB index ensure failed: {e} – continuing startup")

        # ---------- Redis pub/sub for WebSocket broadcast ----------
        # Connect to Redis and start the listener at startup so the FIRST
        # WS-connecting user no longer pays the ~6s Redis-init cost on their
        # handshake. When WEBSOCKET_REQUIRE_REDIS=true this also fails fast
        # on broker misconfig instead of degrading to in-memory broadcast
        # (which silently breaks cross-worker delivery).
        try:
            logger.info("Initializing WebSocket Redis pub/sub...")
            await asyncio.wait_for(ws_manager.startup_init(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("WebSocket Redis init timed out – continuing startup")
        except Exception as e:
            logger.warning(f"WebSocket Redis init failed: {e} – continuing startup")

    # Run DB initialization in background (NON-BLOCKING). Keep the task
    # referenced on app.state so the event loop can't GC it mid-flight.
    app.state.init_services_task = asyncio.create_task(init_services())

    # ---------- Azure Blob Storage for templates ----------
    if settings.azure_storage_connection_string:
        try:
            from app.utils.azure_storage import initialize_template_storage
            initialize_template_storage(
                settings.azure_storage_connection_string,
                settings.azure_templates_container_name,
            )
            logger.info("Azure template storage initialized (container=%s)",
                        settings.azure_templates_container_name)
        except Exception as e:
            logger.exception("Failed to initialize Azure template storage: %s", e)

    # -------------------------------------------------
    # START SITE-MILESTONE KAFKA PRODUCER (Study Operations → Data Platform)
    # Outbound: the site-status activation workflow publishes site_milestone.*
    # events to the shared `sites.milestones.events` Event Hub topic.
    # -------------------------------------------------
    if settings.start_milestones_producer or settings.start_documents_producer:
        try:
            from app.integrations.milestones_kafka import start_milestones_producer
            await start_milestones_producer()
            logger.info("✅ Data Platform Kafka producer started (milestones + documents)")
        except Exception as e:
            logger.exception(f"❌ Failed to start Data Platform Kafka producer: {e}")

    # -------------------------------------------------
    # START INBOUND IAM KAFKA CONSUMER (Data Platform → local IAM mirror)
    # Reuses the same Data Platform Event Hub connection as the producer above.
    # -------------------------------------------------
    if settings.start_iam_kafka_consumer:
        try:
            from app.integrations.kafka.data_platform_consumer import initialize_data_platform_consumer
            await initialize_data_platform_consumer()
            logger.info("✅ Data Platform Kafka consumer started (IAM sync → local mirror)")
        except Exception as e:
            logger.exception(f"❌ Failed to start Data Platform Kafka consumer: {e}")

    # -------------------------------------------------
    # START CELERY WORKER (SAME CONTAINER)
    # -------------------------------------------------
    if os.getenv("START_CELERY", "false").lower() == "true":
        try:
            logger.info("🚀 Starting Celery worker (+ embedded beat) inside backend container")
            # Let Celery worker logs go to the main process stdout/stderr so we can
            # see SMTP / task errors in App Service logs (especially in production).
            #
            # --beat embeds the beat scheduler in this single worker process so the
            # 30s workflow timer/job sweeps (celery_app.beat_schedule) actually fire
            # in production. This combined worker+beat is correct ONLY for a SINGLE
            # worker instance (the current Azure App Service setup). If this is ever
            # scaled to multiple worker instances, --beat must be split into its own
            # single dedicated `celery beat` process — otherwise every worker would
            # run its own beat and double-schedule (duplicate) the sweeps.
            app.state.celery_process = await asyncio.create_subprocess_exec(
                "celery",
                "-A",
                "app.workers.celery_app",
                "worker",
                "--beat",
                "--loglevel=info",
            )
            logger.info("✅ Celery worker started successfully")
        except Exception as e:
            logger.exception(f"❌ Failed to start Celery worker: {e}")

    # -------------------------------------------------
    # DEV BACKGROUND SWEEPER (timers + jobs) — dev only, flag-gated.
    # Production runs the Celery beat schedule instead; this loop must stay OFF
    # there (running both would double-sweep). It lets a job/timer advance in the
    # background even when no V2 panel is open to trigger /run-sweeps.
    # -------------------------------------------------
    app.state.dev_sweeper_task = None
    if settings.workflow_dev_sweep:
        async def _dev_sweeper_loop():
            from app.db import AsyncSessionLocal, transactional
            from app.modules.workflows import service as wf_service
            interval = max(1, int(settings.workflow_dev_sweep_interval_seconds))
            logger.info("🧹 Workflow dev sweeper started (every %ss)", interval)
            while True:
                try:
                    await asyncio.sleep(interval)
                    async with AsyncSessionLocal() as sweep_db:
                        async with transactional(sweep_db):
                            await wf_service.run_sweeps_once(sweep_db)
                except asyncio.CancelledError:
                    # Propagate so the task is marked cancelled (shutdown awaits
                    # it inside a suppress block).
                    raise
                except Exception:  # noqa: BLE001 — never let a tick kill the loop
                    logger.exception("Workflow dev sweeper tick failed; continuing")
        app.state.dev_sweeper_task = asyncio.create_task(_dev_sweeper_loop())

    # App is now considered STARTED
    yield

    # -------------------------------------------------
    # Shutdown
    # -------------------------------------------------
    dev_sweeper_task = getattr(app.state, "dev_sweeper_task", None)
    if dev_sweeper_task is not None:
        dev_sweeper_task.cancel()
        try:
            await dev_sweeper_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    if settings.start_milestones_producer or settings.start_documents_producer:
        try:
            from app.integrations.milestones_kafka import stop_milestones_producer
            await stop_milestones_producer()
            logger.info("Data Platform Kafka producer stopped")
        except Exception as e:
            logger.exception(f"Error stopping Data Platform Kafka producer: {e}")

    if settings.start_iam_kafka_consumer:
        try:
            from app.integrations.kafka.data_platform_consumer import shutdown_data_platform_consumer
            await shutdown_data_platform_consumer()
            logger.info("Data Platform Kafka consumer stopped")
        except Exception as e:
            logger.exception(f"Error stopping Data Platform Kafka consumer: {e}")

    try:
        await close_mongo_client()
        logger.info("MongoDB connection closed")
    except Exception:
        pass

# -------------------------------------------------
# FastAPI app
# -------------------------------------------------
app = FastAPI(
    title="Clinical Trials CRM Communication Engine",
    lifespan=lifespan,
    # Disable automatic trailing-slash redirects.
    # Azure App Service terminates SSL before the app sees the request, so
    # FastAPI would build the 307 Location URL as http:// — which the browser
    # blocks as Mixed Content.  With redirect_slashes=False, FastAPI matches
    # both /path and /path/ without redirecting.
    redirect_slashes=False,
)

# -------------------------------------------------
# Application exception handlers
# -------------------------------------------------
# AppError subclasses (raised by services/repositories) map to structured
# JSON responses via a single handler. Routes that raise HTTPException
# directly continue to work unchanged.
from app.errors import register_error_handlers
register_error_handlers(app)

# -------------------------------------------------
# Proxy / HTTPS middleware
# -------------------------------------------------
# Azure App Service terminates TLS at its load-balancer and forwards requests
# to this container as plain HTTP, setting X-Forwarded-Proto: https.
# Without telling Starlette/FastAPI to trust that header, any automatic
# redirect (e.g. trailing-slash) would use "http://" in the Location URL,
# causing Mixed Content errors in the browser.
#
# ProxyHeadersMiddleware rewrites scope["scheme"] to "https" when it sees
# X-Forwarded-Proto: https, so every URL FastAPI builds is https://.
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware as UvProxyHeaders

# Trust the Azure-injected forwarded headers so FastAPI sees the real scheme.
app.add_middleware(UvProxyHeaders, trusted_hosts="*")

# -------------------------------------------------
# Session cookie (Starlette) — backs the hub-and-spoke SSO flow.
# Stores PKCE verifier, OAuth state, and the authenticated `user` dict in a
# signed HTTP-only cookie. Signing key is local to this spoke and is NOT the
# hub's JWT secret. See app/modules/sso/.
# -------------------------------------------------
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings

if settings.session_secret_key:
    # Cookie policy depends on env. In production the SPA and backend live on
    # different sites (azurestaticapps.net vs azurewebsites.net) — same-site
    # "lax" cookies would NOT be sent on those cross-site requests, so SSO
    # would silently break. Use "none" + Secure in prod so the cookie travels
    # cross-site over HTTPS. Local stays on "lax" + insecure so dev over
    # plain http://localhost works.
    _is_prod = (settings.environment or "").lower() == "production"
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        max_age=86400,  # 24 hours
        same_site="none" if _is_prod else "lax",
        https_only=_is_prod,
    )
else:
    logger.warning(
        "SESSION_SECRET_KEY not set — SSO session middleware NOT mounted; "
        "/api/auth/login (GET) will return 500 until this is configured. "
        "Safe to leave empty when only using POST /api/auth/login (local password flow)."
    )

# -------------------------------------------------
# SSO dev bypass guard — refuse to boot if bypass is enabled in production.
# In any non-production env where bypass IS on, log a loud banner so the
# state is impossible to miss in logs.
# -------------------------------------------------
if settings.dev_auth_bypass:
    if (settings.environment or "").lower() == "production":
        raise RuntimeError(
            "DEV_AUTH_BYPASS=true with ENVIRONMENT=production — refusing to start. "
            "Disable DEV_AUTH_BYPASS or set ENVIRONMENT to local/staging."
        )
    logger.warning(
        "DEV AUTH BYPASS ACTIVE (environment=%s) — /api/auth/login will inject "
        "a fake session user (user_id=%s, email=%s). DO NOT SHIP THIS FLAG ON.",
        settings.environment,
        settings.dev_auth_user_id,
        settings.dev_auth_user_email,
    )

# -------------------------------------------------
# CORS
# -------------------------------------------------

origins = (
    settings.cors_origins.split(",")
    if settings.cors_origins
    else []
)
origins = [o.strip() for o in origins if o and o.strip()]
if not origins:
    # Local-dev fallback to prevent browser CORS blocks when CORS_ORIGINS is unset.
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

# Always allow the IAM hub origin so future webhook-style callbacks from the
# hub (and Swagger/dev tooling) work even when CORS_ORIGINS is set narrowly.
for hub_origin in (
    settings.iam_hub_base_url,
    "https://punk-reunite-sage.ngrok-free.dev",
    "https://hub-app.dizzaroo.com",
):
    if hub_origin and hub_origin not in origins:
        origins.append(hub_origin)

cors_allow_origin_regex = (
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?|"
    r"https://[a-zA-Z0-9-]+\.ngrok-free\.(dev|app)|"
    r"https://[a-zA-Z0-9-]+\.ngrok\.io"
)

class CorsSafeUnhandledExceptionMiddleware(BaseHTTPMiddleware):
    """Return JSON 500 responses with CORS headers for unexpected crashes."""

    def __init__(self, app, *, allowed_origins: list[str], allowed_origin_regex: str) -> None:
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)
        self.allowed_origin_regex = re.compile(allowed_origin_regex)

    def _origin_allowed(self, origin: str) -> bool:
        return origin in self.allowed_origins or bool(self.allowed_origin_regex.fullmatch(origin))

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
            detail = "Internal server error"
            if (settings.environment or "").lower() in {"local", "development", "dev", "test"}:
                detail = str(exc) or detail
            response = JSONResponse(status_code=500, content={"detail": detail})
            origin = request.headers.get("origin")
            if origin and self._origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "*"
                response.headers["Access-Control-Allow-Headers"] = "*"
                response.headers["Access-Control-Expose-Headers"] = "X-Response-Time-ms"
                response.headers.add_vary_header("Origin")
            return response

# -------------------------------------------------
# Response compression
# -------------------------------------------------
# GZip JSON payloads (dashboards, monitoring aggregates) larger than 1KB.
# Free 30-70% bandwidth on typical API responses; no client work required.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# -------------------------------------------------
# Per-request timing + Prometheus metrics
# -------------------------------------------------
# Adds X-Response-Time-ms to every response, records latency histogram, and
# logs any request slower than SLOW_REQUEST_MS (default 500ms). Metrics are
# scraped from /metrics when prometheus_client is installed.
install_timing_middleware(app)
mount_metrics_endpoint(app)

# -------------------------------------------------
# ETag / If-None-Match
# -------------------------------------------------
# Hash-based ETag on every successful GET response. Re-requests that send
# `If-None-Match: <prev-etag>` short-circuit to 304 — no body re-sent.
# Pairs with the frontend TanStack Query layer for studies/sites/templates
# style endpoints where the same payload is fetched repeatedly.
install_etag_middleware(app)

# Keep browser clients from seeing backend 500s as misleading CORS failures.
# This is added after the other HTTP middlewares so it wraps their errors too.
app.add_middleware(
    CorsSafeUnhandledExceptionMiddleware,
    allowed_origins=origins if origins != [""] else [],
    allowed_origin_regex=cors_allow_origin_regex,
)

# Lift the assistant provenance header into a ContextVar so audit writers can
# stamp bot-originated actions. Added after the HTTP middlewares above =>
# outside them => the ContextVar is set before any downstream middleware spawns
# the endpoint task (correct propagation).
from app.audit_context import AuditProvenanceMiddleware
app.add_middleware(AuditProvenanceMiddleware)

# CORS — added LAST so it is the OUTERMOST middleware: preflight OPTIONS
# requests short-circuit before hitting the middlewares above, and every
# response (including 500s raised inside inner middlewares) carries CORS
# headers. CORSMiddleware is pure ASGI (no task spawn), so it does not
# interfere with AuditProvenanceMiddleware's ContextVar propagation.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != [""] else [],
    # Dev convenience:
    #   - localhost / 127.0.0.1 on any port
    #   - any *.ngrok-free.dev / .ngrok-free.app / .ngrok.io subdomain
    #     (so developers can share their local stack via ngrok without
    #      restarting the backend with a new CORS_ORIGINS env var every
    #      time the tunnel hostname rotates)
    allow_origin_regex=cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Response-Time-ms"],
)

# -------------------------------------------------
# Routes
# -------------------------------------------------
# Module routers (formerly aggregated under app/api/v1/api.py).
# SSO must mount before auth_profiles so /api/auth/* resolves to the SSO
# module (login/callback/logout/me).
app.include_router(sso_router, prefix="/api", tags=["Auth (SSO)"])
app.include_router(auth_profiles_router, prefix="/api", tags=["Profiles"])
app.include_router(communications_router, prefix="/api", tags=["Communications"])
app.include_router(ai_router, prefix="/api", tags=["AI"])
app.include_router(assistant_router, prefix="/api", tags=["Assistant"])
app.include_router(clinical_workflow_router, prefix="/api", tags=["Clinical Workflow"])
app.include_router(agreements_router, prefix="/api", tags=["Legal"])
app.include_router(operations_router, prefix="/api", tags=["Operations"])
app.include_router(review_comments_router, prefix="/api", tags=["Review Comments"])
app.include_router(facilities_router, prefix="/api", tags=["Facilities (External)"])
# Workflow platform — the router already carries prefix="/api/workflows", so it is
# mounted WITHOUT an extra prefix (avoids /api/api). Final paths: /api/workflows/...
app.include_router(workflows_router, tags=["Workflows"])

app.include_router(site_packages_router, prefix="/api", tags=["site-packages"])
# Monitoring module already declares its own /api/monitor prefix.
app.include_router(monitor_router)
app.include_router(sites_router, prefix="/api", tags=["sites"])
app.include_router(feasibility_router, prefix="/api", tags=["feasibility-attachments"])

# -------------------------------------------------
# ISF (Investigator Site File) Module Routes
# Integrated from ISF-Complete; replaces old SiteDocuments Document module
# -------------------------------------------------
try:
    from app.modules.isf.routers import (
        isf_documents,
        isf_workflow,
        isf_reference,
        isf_browser,
        gemini as isf_gemini,
        validation as isf_validation,
        tmf_routing,
    )
    app.include_router(isf_documents.router, prefix="/api/isf-documents", tags=["ISF Documents"])
    app.include_router(isf_workflow.router, prefix="/api/isf-workflow", tags=["ISF Workflow"])
    app.include_router(isf_reference.router, prefix="/api/isf", tags=["ISF Reference"])
    app.include_router(isf_browser.router, prefix="/api/isf", tags=["ISF Browser"])
    app.include_router(isf_gemini.router, prefix="/api/gemini", tags=["ISF Gemini AI"])
    app.include_router(isf_validation.router, prefix="/api/validation", tags=["ISF Validation"])
    app.include_router(tmf_routing.router, prefix="/api", tags=["TMF Routing"])
    logger.info("✅ ISF module routers registered successfully")
except Exception as _isf_err:
    logger.exception(f"❌ Failed to register ISF module routers: {_isf_err}")

# -------------------------------------------------
# Site budgeting module (models registered for SQLAlchemy metadata)
# -------------------------------------------------
try:
    # Must not use `import app.modules...`: that rebinds name `app` to the package and breaks FastAPI `app`.
    importlib.import_module("app.modules.site_budgeting.db_models")
    from app.modules.site_budgeting.routes.budgeting import router as site_budgeting_router

    app.include_router(site_budgeting_router, prefix="/api/budgeting")
    logger.info("✅ Site budgeting routes registered at /api/budgeting")

    from app.modules.site_budgeting.site_creation.router import router as site_creation_router
    app.include_router(site_creation_router, prefix="/api/budgeting/site")
    logger.info("✅ Site creation routes registered at /api/budgeting/site")

    from app.modules.site_budgeting.routes.planned_enrollment import router as planned_enrollment_router
    app.include_router(planned_enrollment_router, prefix="/api/budgeting")
    logger.info("✅ Planned enrollment + rollup routes registered at /api/budgeting")
except Exception as _sb_err:
    logger.exception(f"❌ Failed to register site budgeting module: {_sb_err}")

# -------------------------------------------------
# Study Dashboard module (read-only SDTM views)
# -------------------------------------------------
try:
    from app.modules.study_dashboard.routes.dashboard import router as study_dashboard_router
    app.include_router(study_dashboard_router, prefix="/api")
    logger.info("✅ Study dashboard routes registered at /api/study-dashboard")
except Exception as _sd_err:
    logger.exception(f"❌ Failed to register study dashboard module: {_sd_err}")

# -------------------------------------------------
# Web Vitals beacon
# -------------------------------------------------
# Front-end posts Core Web Vitals (LCP, INP, CLS, FCP, TTFB) here on
# pagehide / visibilitychange. We log structured JSON so any log aggregator
# (Azure Monitor, Loki) can chart real-user p75s without an extra service.
_webvitals_logger = logging.getLogger("app.webvitals")


class WebVitalsPayload(BaseModel):
    name: str = Field(..., description="LCP|INP|CLS|FCP|TTFB|...", max_length=16)
    value: float
    rating: str | None = Field(default=None, max_length=16)
    id: str | None = Field(default=None, max_length=64)
    navigationType: str | None = Field(default=None, max_length=32)
    path: str | None = Field(default=None, max_length=256)


@app.post("/api/metrics/web-vitals", include_in_schema=False)
async def web_vitals_beacon(payload: WebVitalsPayload, request: Request):
    # Minimal sink: log a single structured line. Cheap to grep, cheap to
    # ship into a dashboard later. Never throws — beacons must never 500.
    try:
        _webvitals_logger.info(
            "webvital name=%s value=%.2f rating=%s path=%s nav=%s ua=%s",
            sfmt(payload.name),
            payload.value,
            sfmt(payload.rating or "-"),
            sfmt(payload.path or "-"),
            sfmt(payload.navigationType or "-"),
            sfmt(request.headers.get("user-agent", "-")[:120]),
        )
    except Exception:
        pass
    return {"ok": True}


# -------------------------------------------------
# Health check
# -------------------------------------------------
@app.get("/")
async def health_check_root():
    """Simple health check at root that doesn't block on database connections."""
    return {"status": "UP", "service": "backend"}


@app.get("/health")
async def health_check():
    """
    Azure App Service health probe endpoint.
    Must respond quickly without touching the database.
    """
    return {"status": "UP", "service": "backend"}


@app.get("/healthcheck")
async def health_check_alias():
    """Legacy health check alias."""
    return {"status": "UP", "service": "backend"}
