"""
Azure Blob Storage upload and SAS URL generation.
Uses connection string and container from config; uploads buffer and returns blob URL.
SAS tokens grant time-limited read access to private blobs without exposing credentials.
"""
import logging
import os
from typing import Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

from ..core.config import settings
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)

# Lazy init to avoid import error if package not installed
_blob_service_client = None


def _get_connection_string() -> str:
    return getattr(settings, "AZURE_STORAGE_CONNECTION_STRING", "") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")


def _get_container_name() -> str:
    return getattr(settings, "AZURE_STORAGE_CONTAINER", None) or os.environ.get("AZURE_STORAGE_CONTAINER", "")


def _get_client():
    global _blob_service_client
    if _blob_service_client is not None:
        return _blob_service_client
    conn = _get_connection_string()
    if not conn or "placeholder" in conn.lower() or "your_azure" in conn.lower():
        logger.warning("Azure storage not configured, uploads will return mock URL")
        return None
    try:
        from azure.storage.blob import BlobServiceClient
        client = BlobServiceClient.from_connection_string(conn)
        _blob_service_client = client
        return client
    except ImportError:
        logger.warning("azure-storage-blob not installed; pip install azure-storage-blob")
        return None
    except Exception as e:
        logger.warning("Azure BlobServiceClient init failed: %s", e)
        return None


def _parse_connection_string(conn_str: str) -> dict:
    """Parse Azure connection string into a dict of key=value pairs."""
    parts = {}
    for part in conn_str.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            parts[k.strip()] = v.strip()
    return parts


def generate_sas_url(blob_name: str, expiry_hours: int = 1) -> Optional[str]:
    """
    Generate a time-limited SAS (Shared Access Signature) read URL for a blob.

    - Works for private containers (no public access needed)
    - Valid for `expiry_hours` hours (default: 1 hour)
    - Returns None if Azure is not configured or SAS generation fails
    """
    conn = _get_connection_string()
    if not conn or "placeholder" in conn.lower():
        logger.warning("generate_sas_url: Azure not configured, returning None")
        return None

    container_name = _get_container_name()
    if not container_name:
        logger.warning("generate_sas_url: AZURE_STORAGE_CONTAINER not set")
        return None

    try:
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions

        parts = _parse_connection_string(conn)
        account_name = parts.get("AccountName", "")
        account_key = parts.get("AccountKey", "")

        if not account_name or not account_key:
            logger.warning("generate_sas_url: Could not parse AccountName/AccountKey from connection string")
            return None

        # Blob names in stored URLs are often URL-encoded (e.g. `%20` for spaces).
        # Azure SAS signing must use the *actual* blob name (decoded), otherwise the
        # generated signature won't match and downloads will 403.
        blob_name_decoded = unquote(blob_name)

        expiry = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name_decoded,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )

        # URL must contain an encoded path segment for special characters.
        blob_name_encoded = quote(blob_name_decoded, safe="/")
        sas_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name_encoded}?{sas_token}"
        logger.info("SAS URL generated for blob: %s (expires in %dh)", sfmt(blob_name_decoded), expiry_hours)
        return sas_url

    except Exception as e:
        logger.exception("generate_sas_url failed for blob '%s': %s", blob_name, e)
        return None


def upload_to_azure(buffer: bytes, file_name: str, mime_type: Optional[str] = None) -> str:
    """
    Upload file buffer to Azure Blob Storage. Returns blob URL (or mock URL if not configured).
    Matches Node.js uploadToAzure(buffer, fileName, mimeType).
    """
    import time
    # Always use the configured container; no hardcoded fallback
    container_name = getattr(settings, "AZURE_STORAGE_CONTAINER", None) or os.environ.get("AZURE_STORAGE_CONTAINER", "")
    client = _get_client()
    if not client:
        return f"https://mock-storage.local/{int(time.time() * 1000)}-{file_name}"
    try:
        from azure.storage.blob import ContentSettings
        container_client = client.get_container_client(container_name)
        try:
            container_client.create_container()
        except Exception:
            # Container already exists, continue
            pass
        blob_name = f"{int(time.time() * 1000)}-{file_name}"
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            buffer,
            overwrite=True,
            content_settings=ContentSettings(content_type=mime_type or "application/octet-stream")
        )
        url = blob_client.url
        logger.info("File uploaded to Azure: %s", sfmt(blob_name))
        return url
    except Exception as e:
        logger.exception("Azure Blob upload failed: %s", e)
        logger.warning("Using mock URL due to upload failure")
        return f"https://mock-storage.local/{int(time.time() * 1000)}-{file_name}"
