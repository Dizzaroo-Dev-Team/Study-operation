from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field, AliasChoices
from typing import Optional


class Settings(BaseSettings):
    model_config = ConfigDict(
        extra="ignore",  # Ignore extra environment variables
        case_sensitive=False,  # IMPORTANT for Azure env vars
        populate_by_name=True,  # allow field-name access even when an alias is set
        env_file=".env",
        env_file_encoding="utf-8",
    )
    # -------------------------------------------------
    # REQUIRED DATABASES
    # -------------------------------------------------
    database_url: str
    mongodb_uri: str
    
    # External MongoDB for feasibility questionnaires (read-only)
    feasibility_mongo_uri: Optional[str] = None

    # External MongoDB for SoA (Schedule of Activities) documents — the
    # llm-compare Atlas cluster used by site-budgeting SoA import.
    soa_mongo_uri: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Data Platform HTTP API — source for facilities (/api/facilities list +
    # site-creation lookups). Replaced the former direct Azure Postgres access
    # (FACILITIES_DB_DSN), removed once the API migration was verified.
    # ─────────────────────────────────────────────────────────────────────────
    data_platform_base_url: Optional[str] = None
    # Sent as the X-App-Id header the Data Platform requires on every call.
    data_platform_facilities_app_id: str = "study_operations"
    facilities_api_timeout_seconds: float = 10.0

    # ─────────────────────────────────────────────────────────────────────────
    # IAM hub SSO.
    # `iam_auth_mode` controls which kinds of bearer tokens get_current_user
    # accepts:
    #   "local" — only the legacy HS256 JWTs minted by /auth/login
    #   "hub"   — only hub-issued tokens (verified via /api/auth/verify)
    #   "both"  — try local first, fall back to hub (default during migration)
    # ─────────────────────────────────────────────────────────────────────────
    iam_auth_mode: str = "both"
    iam_hub_base_url: Optional[str] = None
    iam_hub_verify_path: str = "/api/auth/verify"
    iam_auth_cache_ttl_seconds: int = 60

    # ─────────────────────────────────────────────────────────────────────────
    # Workflow platform — role enforcement is PERMANENT and unconditional: a user
    # may only act on steps they are assigned to (role/user/context match in
    # WorkflowEngine.user_can_act) and may only SEE instances they participate in
    # (service.user_can_access_instance). There is NO "open mode" flag and no way
    # to relax this from config. The UNIFIED template-driven workflow platform is
    # likewise always on — it is the product. (The former WORKFLOW_ENFORCE_ROLES /
    # WORKFLOW_UNIFIED / WORKFLOW_DRIVES_CDA / WORKFLOW_DRIVES_CTA flags were
    # removed; the legacy per-type bridges they gated are gone.)
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # Workflow platform — DEV background sweeper. In production the Celery beat
    # schedule runs the timer + job sweeps (every 30s). Dev stacks usually run no
    # beat, so without this a job/timer only advances while a V2 panel is open and
    # polling /run-sweeps. When TRUE, the app lifespan starts an in-process loop
    # that runs the SAME sweeps periodically, so a workflow advances in the
    # background even with no UI open. MUST stay FALSE in prod (the beat owns it —
    # running both would double-sweep). (env: WORKFLOW_DEV_SWEEP)
    # ─────────────────────────────────────────────────────────────────────────
    workflow_dev_sweep: bool = False
    workflow_dev_sweep_interval_seconds: int = 5

    # ─────────────────────────────────────────────────────────────────────────
    # Hub-and-Spoke SSO (OAuth2 + PKCE). This backend is a spoke that delegates
    # login to the hub. See app/modules/sso/ for the flow implementation.
    # ─────────────────────────────────────────────────────────────────────────
    hub_oauth_api_url: Optional[str] = None
    hub_frontend_url: Optional[str] = None
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    # Starlette SessionMiddleware signing key (distinct from JWT `secret_key`).
    session_secret_key: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # SSO dev bypass — local-only escape hatch so devs can boot the spoke
    # without standing up the hub. Guarded TWICE: must be explicitly enabled
    # AND `environment` must be "local". main.py refuses to start if bypass
    # is enabled while environment=="production".
    # ─────────────────────────────────────────────────────────────────────────
    environment: str = "local"  # local | staging | production
    dev_auth_bypass: bool = False
    dev_auth_user_id: str = "dev-user"
    dev_auth_user_email: str = "dev@local"
    dev_auth_user_name: str = "Dev User"
    dev_auth_user_role: str = "admin"

    # ─────────────────────────────────────────────────────────────────────────
    # Communications hardening — the former COMMS_* feature flags were removed
    # once their behavior was proven and made permanent. Now the only behavior:
    #   • study-membership access enforcement (PUBLIC conv/thread visible only to
    #     study members — the LEAK-1 fix)
    #   • write-guards on mutating routes (auth + object access)
    #   • privacy recompute (is_confidential/is_restricted honored; reversible)
    #   • safe thread-combine (compensating-transaction rebuild)
    #   • reliable dispatch (direct .delay()) + two-phase send (NEEDS_REVIEW)
    #   • resilient Redis listener (bounded reconnect) + pooled Celery engine
    #   • best-effort audit writes
    #   • inbound-sender allowlisting (enforce only when an allowlist exists;
    #     allowlist built from actual correspondents — see workers/tasks.py)
    # The orphan-attachment reconciler and stuck-QUEUED sweeper remain dry-run by
    # default and only act on an explicit dry_run=False invocation.
    # ─────────────────────────────────────────────────────────────────────────

    # This app's IAM application key in the hub. Used by the SSO entitlement
    # check (auth.py) and app-scoped resource lookups (sites, site budgeting).
    # Not Kafka-related.
    iam_application_id: Optional[str] = None
    # Default password given to IAM-mirrored users on creation (legacy
    # /auth/login flow). Unset => random per boot => legacy login disabled
    # for mirrored users; they sign in via SSO / hub tokens. Consumed by
    # app/integrations/kafka/events/user_event.py.
    iam_mirror_default_password: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Site-milestone Kafka PRODUCER (Study Operations → Data Platform).
    # When `start_milestones_producer` is true the FastAPI lifespan opens an
    # aiokafka producer against the self-hosted Kafka broker and the site-status
    # activation workflow publishes `site_milestone.*` events to the shared
    # `sites.milestones.events` topic. See the Data Platform integration guide.
    # This is the shared Data Platform Kafka connection; a future inbound IAM
    # consumer is intended to reuse it (the old standalone IAM Kafka consumer and
    # its separate Hub-IAM connection have been removed).
    # ─────────────────────────────────────────────────────────────────────────
    start_milestones_producer: bool = False
    # Self-hosted Kafka broker list (CSV host:port). Maps to the KAFKA_BROKERS
    # env var; the legacy MILESTONES_KAFKA_BROKERS name is accepted as an alias.
    # Replaces the former EVENTHUB_NAMESPACE / EVENTHUB_CONNECTION_STR pair —
    # the connection is now PLAINTEXT (no SASL/SSL).
    kafka_brokers: Optional[str] = Field(
        None, validation_alias=AliasChoices("kafka_brokers", "milestones_kafka_brokers")
    )
    # Producer topic + client id. Accept the Data Platform contract names
    # (MILESTONE_KAFKA_TOPIC / KAFKA_PRODUCER_CLIENT_ID from D:/kafka/README.md)
    # as well as the legacy MILESTONES_* names for backward compatibility.
    milestones_kafka_topic: str = Field(
        "sites.milestones.events",
        validation_alias=AliasChoices("milestone_kafka_topic", "milestones_kafka_topic"),
    )
    milestones_kafka_client_id: str = Field(
        "study-operations-milestones",
        validation_alias=AliasChoices("kafka_producer_client_id", "milestones_kafka_client_id"),
    )
    milestones_source_app: str = "study_operations"
    milestones_target_app: str = "data_platform"

    # ─────────────────────────────────────────────────────────────────────────
    # ISF document Kafka PRODUCER (Study Operations → Data Platform).
    # Shares the same Kafka connection as the milestone producer above; only
    # the topic differs. When `start_documents_producer` is true the producer is
    # opened at startup and "Enable TMF Routing" publishes the full ISF document
    # payload (from Mongo) to the `platform.documents` topic instead of emailing.
    # ─────────────────────────────────────────────────────────────────────────
    start_documents_producer: bool = False
    documents_kafka_topic: str = "platform.documents"

    # ─────────────────────────────────────────────────────────────────────────
    # Inbound IAM Kafka CONSUMER (Data Platform → local IAM mirror).
    # Reuses the SAME self-hosted Kafka connection as the milestone producer
    # above (`kafka_brokers`). When `start_iam_kafka_consumer` is true the
    # FastAPI lifespan opens an aiokafka consumer that mirrors the IAM
    # entity-sync topics into Mongo `local_*` collections (+ the Postgres
    # `users` row). Startup is non-blocking: connection failures are logged and
    # the app keeps running. See app/integrations/kafka/data_platform_consumer.py.
    # ─────────────────────────────────────────────────────────────────────────
    # Our lifecycle gate (not part of the Data Platform contract).
    start_iam_kafka_consumer: bool = False
    # Connection identity — exact Data Platform contract names (README.md).
    dataplatform_kafka_group_id: str = "study-operations-iam-sync"
    kafka_consumer_client_id: str = "study-operations-iam-consumer"
    kafka_start_from_beginning: bool = False
    # Routing / app targeting. `data_platform_app_id` scopes app-scoped events;
    # `kafka_required_source` (when set) drops envelopes whose `source` tag does
    # not match. Both empty => no filtering (accept everything on the topic).
    data_platform_app_id: Optional[str] = None
    kafka_required_source: Optional[str] = None
    # IAM entity-sync topics. Defaults match the live Data Platform stream; the
    # *_KAFKA_TOPIC env vars override per environment. (Old `abac.*` names removed.)
    users_kafka_topic: str = "iam.users.events"
    hub_user_attributes_kafka_topic: str = "iam.hub_user_attributes.events"
    app_user_attributes_kafka_topic: str = "iam.app_user_attributes.events"
    app_attribute_definitions_kafka_topic: str = "iam.app_attribute_definition.events"
    policies_kafka_topic: str = "iam.policies.events"
    resources_kafka_topic: str = "iam.resources.events"
    # Policy-evaluation subject keys (reserved for the policy handler).
    subject_role_key: Optional[str] = None
    subject_access_key: Optional[str] = None

    # -------------------------------------------------
    # CELERY / REDIS (PRODUCTION)
    # -------------------------------------------------
    # Celery MUST have a broker in production
    celery_broker_url: str

    # Result backend is REQUIRED for reliability
    celery_result_backend: Optional[str] = None

    # App-level Redis (WebSockets / pub-sub / cache)
    redis_url: Optional[str] = None

    # -------------------------------------------------
    # SECURITY
    # -------------------------------------------------
    # REQUIRED in production — generate with: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "your-secret-key-change-in-production"

    # -------------------------------------------------
    # OPTIONAL / DEFAULTS
    # -------------------------------------------------
    mongodb_database: str = "crm_db"

    mock_provider_token: Optional[str] = None

    # AI
    gemini_api_key: Optional[str] = None
    # Gemini model id used for WORKFLOW GENERATION + clarify (generate.py). Flip this
    # to compare models without code changes, e.g. WORKFLOW_GENERATION_MODEL=gemini-flash-latest
    # in .env. Only the workflow generate/clarify path reads it; other AI features keep
    # the AIClient default. (env: WORKFLOW_GENERATION_MODEL)
    workflow_generation_model: str = "gemini-3.5-flash"

    # Agentic assistant (app/modules/assistant). Model id for the tool-calling
    # agent. Confirmed available on the deployed key (preflight P2); overridable
    # via ASSISTANT_MODEL in .env (the 2.5 and older generations are retired).
    assistant_model: str = "gemini-3.5-flash"

    # Directory of feature docs (docs/features/*.md) the assistant inlines for
    # "how do I…" help answers. In Docker the repo docs are mounted at
    # /repo-docs (see docker-compose backend volumes). On host runs the loader
    # falls back to the repo-root docs/features path. (env: ASSISTANT_DOCS_DIR)
    assistant_docs_dir: Optional[str] = None

    # -------------------------------------------------
    # Orbit derived memory (app/modules/assistant/memory)
    # -------------------------------------------------
    # Hard per-user cap on DERIVED memory items — bounds DB growth and keeps the
    # single-read load fast. Over-cap writes evict the least-salient/oldest.
    assistant_memory_cap: int = 40
    # Rolling retention (days) for the RAW turn buffer the nightly distiller
    # reads. Buffer rows older than this are pruned — it is not a permanent
    # transcript store. (env: ASSISTANT_TURN_RETENTION_DAYS)
    assistant_turn_retention_days: int = 14
    # Only distil users who produced at least this many turns in the window, so
    # the nightly job skips idle users cheaply. (env: ASSISTANT_MEMORY_MIN_TURNS)
    assistant_memory_min_turns: int = 4

    # -------------------------------------------------
    # Orbit live evals (app/modules/assistant/live_eval) — Kind B scoring of
    # every real turn AFTER its answer is produced. DEFAULT OFF.
    # -------------------------------------------------
    # Master switch. Off => no recording, no scoring, zero overhead.
    # (env: ENABLE_LIVE_EVALS)
    enable_live_evals: bool = False
    # LLM-judge switch. Off => deterministic-only scoring: NOTHING leaves the
    # box. Turning this ON sends PHI-SCRUBBED answer/evidence text to the
    # Gemini judge and REQUIRES explicit human sign-off — see
    # agent_evals/README.md. Never default this to true. (env: ENABLE_LIVE_JUDGE)
    enable_live_judge: bool = False
    # Fraction of turns to score, for cost control (1.0 = every turn).
    # (env: LIVE_EVAL_SAMPLE_RATE)
    live_eval_sample_rate: float = 1.0
    # Judge model for live grounding scoring. (env: LIVE_EVAL_JUDGE_MODEL)
    # gemini-2.5-pro was retired by Google (404 NOT_FOUND) — 3.5-flash is the
    # newest generation model the API serves.
    live_eval_judge_model: str = "gemini-3.5-flash"

    upload_dir: str = "uploads"

    google_search_api_key: Optional[str] = None
    google_search_engine_id: Optional[str] = None

    # SMTP (optional, not Mailgun inbound)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    
    # Feasibility form default recipient email
    feasibility_default_email: Optional[str] = None

    # -------------------------------------------------
    # MAILGUN (INBOUND SECURITY)
    # -------------------------------------------------
    mailgun_signing_key: Optional[str] = None

    # -------------------------------------------------
    # Sponsor signatory defaults for agreements
    # (independent of Zoho; used when creating agreements/templates)
    # -------------------------------------------------
    sponsor_signatory_name: Optional[str] = None
    sponsor_signatory_email: Optional[str] = None

    # -------------------------------------------------
    # ONLYOFFICE Document Server
    # -------------------------------------------------
    onlyoffice_url: str = "http://onlyoffice:80"  # Internal Docker network URL
    onlyoffice_public_url: Optional[str] = None  # Public URL for frontend (defaults to onlyoffice_url if not set)
    onlyoffice_jwt_secret: Optional[str] = None  # JWT secret for secure communication
    onlyoffice_jwt_enabled: bool = True  # Enable JWT for security

    # -------------------------------------------------
    # Backend base URL for callbacks (e.g. ONLYOFFICE)
    # -------------------------------------------------
    # Used when external services (OnlyOffice) need to call back into the backend.
    # Default works for local docker-compose (service name "backend").
    # In production (e.g. Azure App Service), set BACKEND_INTERNAL_URL to the public HTTPS URL.
    backend_internal_url: str = "http://backend:8000"
    backend_public_url: Optional[str] = None
    
    # Frontend base URL for generating review links
    frontend_base_url: str = "http://localhost:3000"

    # Internal agreement signing rollout
    enable_internal_signing: bool = True

    # -------------------------------------------------
    # Azure Blob Storage (Templates & Documents)
    # -------------------------------------------------
    azure_storage_connection_string: Optional[str] = None
    azure_templates_container_name: str = "crm-templates"

    # -------------------------------------------------
    # Pydantic config
    # -------------------------------------------------
    cors_origins: Optional[str] = None

    # Site budgeting module (trial-level cost templates; gated rollout)
    enable_site_budgeting: bool = False
    site_budgeting_allowed_user_ids: Optional[str] = None  # comma-separated user_id values; empty = all users when enabled

    # -------------------------------------------------
    # Study Dashboard — per-study read-only SDTM Postgres.
    # Kept as discrete fields so SQLAlchemy URL.create() handles password escaping.
    # -------------------------------------------------
    study_db_01_host: Optional[str] = None
    study_db_01_port: int = 5432
    study_db_01_name: Optional[str] = None
    study_db_01_user: Optional[str] = None
    study_db_01_password: Optional[str] = None

    # Data Platform Study Registry connection strings address Postgres by its
    # Docker-internal hostname (e.g. "postgres"), which only resolves inside
    # the Data Platform's network. When this backend runs elsewhere, set this
    # to the externally reachable "host" or "host:port" to substitute into
    # every registry connection string. Empty = use them as-is.
    study_registry_db_host_override: Optional[str] = None


settings = Settings()


