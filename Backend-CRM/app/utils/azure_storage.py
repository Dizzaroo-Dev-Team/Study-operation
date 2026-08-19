"""
Azure Blob Storage utility for template and document file uploads.
"""
import os
import re
import uuid
from pathlib import Path
from typing import Optional, BinaryIO

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

import logging

logger = logging.getLogger(__name__)


class AzureBlobStorage:
    """Azure Blob Storage client for file uploads."""

    def __init__(self, connection_string: str, container_name: str):
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_service_client: Optional[BlobServiceClient] = None
        self._initialize_client()

    def _initialize_client(self):
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            logger.info(
                "Azure Blob Storage client initialized for container: %s",
                self.container_name,
            )
        except Exception as e:
            logger.exception("Failed to initialize Azure Blob Storage client: %s", e)
            raise

    async def ensure_container_exists(self):
        """Create the container if it doesn't already exist."""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            try:
                container_client.get_container_properties()
            except AzureError as e:
                if "ContainerNotFound" in str(e):
                    container_client.create_container()
                    logger.info("Container '%s' created", self.container_name)
                else:
                    raise
        except AzureError as e:
            logger.exception("Failed to ensure container '%s': %s", self.container_name, e)
            raise

    async def upload_file(
        self,
        file_content,
        blob_name: str,
        content_type: Optional[str] = None,
        overwrite: bool = True,
    ) -> str:
        """Upload a file and return its blob URL."""
        try:
            await self.ensure_container_exists()

            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name,
            )

            kwargs = {"overwrite": overwrite}
            if content_type:
                from azure.storage.blob import ContentSettings

                kwargs["content_settings"] = ContentSettings(
                    content_type=content_type
                )

            # Handle both BinaryIO and bytes
            if isinstance(file_content, bytes):
                from io import BytesIO
                file_content = BytesIO(file_content)

            blob_client.upload_blob(file_content, **kwargs)
            blob_url = blob_client.url
            logger.info("Uploaded to Azure Blob Storage: %s", blob_name)
            return blob_url
        except AzureError as e:
            logger.exception("Failed to upload '%s': %s", blob_name, e)
            raise

    async def download_file(self, blob_name: str) -> Optional[bytes]:
        """Download a blob and return its content as bytes."""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name,
            )
            blob_data = blob_client.download_blob()
            return blob_data.readall()
        except AzureError as e:
            logger.exception("Failed to download '%s': %s", blob_name, e)
            return None

    async def delete_file(self, blob_name: str) -> bool:
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name,
            )
            blob_client.delete_blob()
            logger.info("Deleted from Azure Blob Storage: %s", blob_name)
            return True
        except AzureError as e:
            logger.exception("Failed to delete '%s': %s", blob_name, e)
            return False

    async def file_exists(self, blob_name: str) -> bool:
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name,
            )
            blob_client.get_blob_properties()
            return True
        except AzureError:
            return False

    async def get_file_url(self, blob_name: str) -> str:
        """Get the URL of a blob."""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name,
            )
            return blob_client.url
        except AzureError as e:
            logger.exception("Failed to get URL for '%s': %s", blob_name, e)
            raise


def _sanitize(name: str) -> str:
    """Remove characters problematic in Azure blob names and collapse whitespace."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_') or 'unknown'


def build_document_blob_name(
    study_name: str,
    site_name: str,
    agreement_title: str,
    version_number: int,
) -> str:
    """
    Build Azure blob path for an agreement document.

    Format: agreements/{study}_{site}_{title}/v{version}.docx
    Example: agreements/MK-6482_Site_01_CDA_Agreement/v1.docx
    """
    safe_study = _sanitize(study_name)
    safe_site = _sanitize(site_name)
    safe_title = _sanitize(agreement_title)
    folder = f"{safe_study}_{safe_site}_{safe_title}"
    return f"agreements/{folder}/v{version_number}.docx"


def build_review_save_blob_name(
    agreement_id: str,
    timestamp: str,
    unique_id: str,
) -> str:
    """
    Build Azure blob path for a saved review document.
    
    Format: review-documents/review_{agreement_id}_{timestamp}_{unique_id}.docx
    Example: review-documents/review_ab030b35-2150-4ce0-8342-6e8dc9f105af_20260318_143022_a1b2c3d4.docx
    """
    return f"review-documents/review_{agreement_id}_{timestamp}_{unique_id}.docx"


def build_review_blob_name(
    study_name: str,
    site_name: str,
    agreement_title: str,
    review_number: int = 1,
) -> str:
    """
    Build Azure blob path for a review document copy.

    Format: agreement_reviews/{study}_{site}_{title}/review_{n}.docx
    Example: agreement_reviews/MK-6482_Site_01_CDA/review_1.docx
    """
    safe_study = _sanitize(study_name)
    safe_site = _sanitize(site_name)
    safe_title = _sanitize(agreement_title)
    folder = f"{safe_study}_{safe_site}_{safe_title}"
    return f"agreement_reviews/{folder}/review_{review_number}.docx"


def build_signed_agreement_blob_name(
    study_name: str,
    site_name: str,
    agreement_title: str,
    agreement_id: str,
    signed_at_utc: Optional[str] = None,
) -> str:
    """
    Build Azure blob path for a signed agreement PDF.

    Format: signed_agreements/{study}_{site}_{title}/agreement_{id}_signed_{ts}.pdf
    Example: signed_agreements/MK-6482_Site_01_CDA/agreement_abcd_signed_20260318_074455.pdf
    """
    safe_study = _sanitize(study_name)
    safe_site = _sanitize(site_name)
    safe_title = _sanitize(agreement_title)
    folder = f"{safe_study}_{safe_site}_{safe_title}"
    ts = _sanitize(signed_at_utc or "")
    if not ts:
        ts = "unknown_time"
    safe_agreement_id = _sanitize(str(agreement_id))
    return f"signed_agreements/{folder}/agreement_{safe_agreement_id}_signed_{ts}.pdf"


def build_template_blob_name(
    study_name: str,
    site_name: str,
    template_type: str,
    template_name: str,
) -> str:
    """
    Build the Azure blob path for a template file.

    Format: templates/{study_name}_{site_name}_{template_type}_{template_name}.docx
    Example: templates/ASLAN001-009_Site_01_OTHER_azure.docx
    """
    safe_study = _sanitize(study_name)
    safe_site = _sanitize(site_name)
    safe_type = _sanitize(template_type)
    safe_name = _sanitize(Path(template_name).stem)
    return f"templates/{safe_study}_{safe_site}_{safe_type}_{safe_name}.docx"


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_template_storage: Optional[AzureBlobStorage] = None


def get_template_storage() -> Optional[AzureBlobStorage]:
    return _template_storage


def initialize_template_storage(connection_string: str, container_name: str):
    global _template_storage
    _template_storage = AzureBlobStorage(connection_string, container_name)
    logger.info(
        "Template storage initialized (container=%s)", container_name
    )


# Alias for document storage (same container, different prefix).
def get_document_storage() -> Optional[AzureBlobStorage]:
    return _template_storage
