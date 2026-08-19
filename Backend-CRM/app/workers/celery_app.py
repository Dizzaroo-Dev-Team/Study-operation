import ssl
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# -------------------------------------------------
# Celery app
# -------------------------------------------------
celery_app = Celery(
    "crm_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# -------------------------------------------------
# Detect if Redis uses SSL (rediss:// = SSL, redis:// = no SSL)
# -------------------------------------------------
broker_uses_ssl = settings.celery_broker_url.startswith("rediss://")
backend_uses_ssl = (
    settings.celery_result_backend and 
    settings.celery_result_backend.startswith("rediss://")
)

# -------------------------------------------------
# Celery configuration
# -------------------------------------------------
celery_config = {
    # ------------------------------
    # Serialization / Time
    # ------------------------------
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,

    # ------------------------------
    # Reliability (IMPORTANT)
    # ------------------------------
    "task_ignore_result": False,
    "task_store_errors_even_if_ignored": True,
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,

    # ------------------------------
    # Retry defaults
    # ------------------------------
    "task_default_retry_delay": 10,
    "task_max_retries": 3,
    
    # ------------------------------
    # Connection timeouts (prevent hanging)
    # ------------------------------
    "broker_connection_timeout": 5,
    "broker_connection_retry": True,
    "broker_connection_retry_on_startup": True,
    "broker_connection_max_retries": 3,
}

# Only add SSL config if using SSL Redis
if broker_uses_ssl:
    celery_config["broker_use_ssl"] = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }

if backend_uses_ssl:
    celery_config["redis_backend_use_ssl"] = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }

celery_app.conf.update(celery_config)

# -------------------------------------------------
# Periodic sweeps (celery beat) — Workflow Platform V2.
# Timers fire and pending jobs execute within ~30s of becoming due. The kernel
# never reads a clock; these sweeps inject TimerFired / JobCompleted events.
# -------------------------------------------------
celery_app.conf.beat_schedule = {
    **(getattr(celery_app.conf, "beat_schedule", None) or {}),
    "workflow-run-due-timers": {
        "task": "app.workers.tasks.workflow_run_due_timers",
        "schedule": 30.0,
    },
    "workflow-run-pending-jobs": {
        "task": "app.workers.tasks.workflow_run_pending_jobs",
        "schedule": 30.0,
    },
    "workflow-run-pending-waits": {
        "task": "app.workers.tasks.workflow_run_pending_waits",
        "schedule": 30.0,
    },
    # Orbit derived memory — nightly distillation of the raw turn buffer into
    # capped, PHI-stripped memory items (off the request path). 03:00 UTC. Rides
    # the same embedded --beat as the workflow sweeps; must not be split into a
    # second beat process (would double-run) — see main.py's START_CELERY note.
    "assistant-memory-distill": {
        "task": "app.workers.tasks.assistant_memory_distill",
        "schedule": crontab(hour=3, minute=0),
    },
}

# -------------------------------------------------
# Debug logs (keep for now)
# -------------------------------------------------
print("🔥 CELERY BROKER =", celery_app.conf.broker_url)
print("🔥 CELERY RESULT BACKEND =", celery_app.conf.result_backend)

# -------------------------------------------------
# Register tasks
# -------------------------------------------------
from app.workers import tasks
