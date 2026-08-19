"""
ISF Settings adapter for CRM integration.
Maps CRM environment variables to ISF expected settings.
All ISF-specific settings with defaults; CRM settings take priority where they overlap.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class ISFSettings(BaseSettings):
    # ── MongoDB (use the same URI as CRM; ISF uses its own db name) ──────────
    MONGODB_URI: str = "mongodb://localhost:27017"

    # ── Server ────────────────────────────────────────────────────────────────
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── Google Gemini AI ──────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GOOGLE_GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_INLINE_BYTES: int = 4194304  # 4 MB

    # ── File Upload ───────────────────────────────────────────────────────────
    MAX_FILE_SIZE: int = 52428800  # 50 MB
    UPLOAD_DIR: str = "uploads"
    TEMP_DIR: str = "temp"

    # ── Azure Storage ─────────────────────────────────────────────────────────
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "crm-isf-doc"   # Azure names: lowercase + hyphens only
    AZURE_STORAGE_SAS_TOKEN_EXPIRY_HOURS: int = 24
    AZURE_STORAGE_MAX_FILE_SIZE: int = 104857600  # 100 MB

    # NOTE: No SECRET_KEY / ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES here.
    # JWT signing is 100% owned by the CRM (app.auth). ISF does not issue
    # its own tokens — it only validates the token the CRM already issued.

    # ── ClamAV ────────────────────────────────────────────────────────────────
    USE_CLAMAV: bool = False
    # Default is the Linux/Docker binary name; override via env var on Windows.
    CLAMAV_PATH: str = "clamscan"

    # ── VirusTotal ────────────────────────────────────────────────────────────
    VIRUSTOTAL_API_KEY: str = ""

    # ── Email ─────────────────────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # ── Validation ────────────────────────────────────────────────────────────
    ENFORCE_STRICT_CLINICAL_RULES: bool = False
    TREAT_CLINICAL_TRIAL_FIELDS_AS_PHI: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    @property
    def isf_database_name(self) -> str:
        """Return the same database name as the CRM so ISF collections live in crm_db."""
        from app.config import settings as crm_settings
        return crm_settings.mongodb_database  # "crm_db"


# ─── Populate from CRM environment variables ────────────────────────────────
# CRM uses lowercase env vars; ISF expects uppercase.
# We read CRM vars and inject them so ISFSettings picks them up.
import os as _os

_mongodb_uri = (
    _os.environ.get("MONGODB_URI")
    or _os.environ.get("mongodb_uri")
    or "mongodb://localhost:27017"
)
_os.environ.setdefault("MONGODB_URI", _mongodb_uri)

_gemini_key = (
    _os.environ.get("GEMINI_API_KEY")
    or _os.environ.get("gemini_api_key")
    or ""
)
_os.environ.setdefault("GEMINI_API_KEY", _gemini_key)

_upload_dir = (
    _os.environ.get("UPLOAD_DIR")
    or _os.environ.get("upload_dir")
    or "uploads"
)
_os.environ.setdefault("UPLOAD_DIR", _upload_dir)

settings = ISFSettings()
