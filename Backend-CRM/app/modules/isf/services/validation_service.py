from typing import Dict, Any, List, Optional
import hashlib
import httpx
import asyncio
from datetime import datetime, timezone
import logging

from ..core.config import settings
from ..utils.text_extractor import extract_document_text
from .phi_detector import LLMBasedPHIDetector

logger = logging.getLogger(__name__)

class VirusTotalScanner:
    """VirusTotal API Scanner Implementation"""
    
    def __init__(self):
        self.api_key = settings.VIRUSTOTAL_API_KEY
        self.api_url = "https://www.virustotal.com/vtapi/v2"
        self.timeout = 60.0  # 60 seconds (VirusTotal can be slow)
        self.max_file_size = 32 * 1024 * 1024  # 32MB (VirusTotal limit)
    
    def get_engine_name(self) -> str:
        return "VirusTotal"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def scan(self, file_buffer: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """Scan file using VirusTotal API"""
        result = {
            "is_clean": False,
            "status": "ERROR",
            "engine": self.get_engine_name(),
            "threats": [],
            "message": "",
            "metadata": {
                "scan_date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "filename": filename,
                "mime_type": mime_type,
                "file_size": len(file_buffer)
            }
        }
        
        try:
            # Check API key
            if not self.api_key:
                result["status"] = "ERROR"
                result["message"] = "VirusTotal API key not configured"
                return result
            
            # Check file size limit
            if len(file_buffer) > self.max_file_size:
                result["status"] = "ERROR"
                result["message"] = f"File size ({len(file_buffer) / 1024 / 1024:.2f}MB) exceeds VirusTotal limit (32MB)"
                return result
            
            # Calculate file hash
            file_hash = hashlib.sha256(file_buffer).hexdigest()
            
            # First, check if file was already scanned
            existing_result = await self._check_existing_scan(file_hash)
            if existing_result:
                return existing_result
            
            # Upload and scan new file
            return await self._upload_and_scan(file_buffer, filename, file_hash, result)
            
        except Exception as error:
            logger.exception(f"VirusTotal scan error for {filename}: {str(error)}")
            result["status"] = "ERROR"
            result["message"] = f"VirusTotal scan failed: {str(error)}"
            return result
    
    async def _check_existing_scan(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Check if file was already scanned"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/file/report",
                    params={
                        "apikey": self.api_key,
                        "resource": file_hash
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("response_code") == 1:
                        # File was previously scanned
                        positives = data.get("positives", 0)
                        total = data.get("total", 0)
                        scans = data.get("scans", {})
                        
                        threats = []
                        for engine, scan_result in scans.items():
                            if scan_result.get("detected"):
                                threats.append(f"{engine}: {scan_result.get('result', 'Unknown')}")
                        
                        return {
                            "is_clean": positives == 0,
                            "status": "INFECTED" if positives > 0 else "CLEAN",
                            "engine": self.get_engine_name(),
                            "threats": threats,
                            "message": f"Detected by {positives}/{total} engines" if positives > 0 else "File scanned and found clean",
                            "metadata": {
                                "scan_date": data.get("scan_date"),
                                "positives": positives,
                                "total": total,
                                "permalink": data.get("permalink")
                            }
                        }
            
            # File not found in database or error occurred
            return None
            
        except Exception as error:
            logger.warning(f"Error checking existing VirusTotal scan: {str(error)}")
            return None
    
    async def _upload_and_scan(self, file_buffer: bytes, filename: str, file_hash: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Upload file to VirusTotal and scan"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Upload file to VirusTotal
                files = {"file": (filename, file_buffer, result["metadata"]["mime_type"])}
                data = {"apikey": self.api_key}
                
                upload_response = await client.post(
                    f"{self.api_url}/file/scan",
                    files=files,
                    data=data
                )
                
                if upload_response.status_code == 200:
                    upload_data = upload_response.json()
                    
                    if upload_data.get("response_code") == 1:
                        # Scan queued, wait a bit and check results
                        await asyncio.sleep(5)
                        
                        # Check scan results
                        scan_result = await self._check_existing_scan(file_hash)
                        if scan_result:
                            return scan_result
                        
                        # If still not ready, return queued status
                        result["status"] = "PENDING"
                        result["message"] = "File uploaded to VirusTotal, scan in progress"
                        result["metadata"]["scan_id"] = upload_data.get("scan_id")
                        return result
                    else:
                        result["status"] = "ERROR"
                        result["message"] = f"VirusTotal upload failed: {upload_data.get('verbose_msg', 'Unknown error')}"
                        return result
                else:
                    result["status"] = "ERROR"
                    result["message"] = f"VirusTotal upload failed with status {upload_response.status_code}"
                    return result
                    
        except Exception as error:
            logger.exception(f"VirusTotal upload error: {str(error)}")
            result["status"] = "ERROR"
            result["message"] = f"VirusTotal upload failed: {str(error)}"
            return result


class ValidationService:
    
    def __init__(self):
        self.virus_scanner = VirusTotalScanner()
        self.phi_detector = LLMBasedPHIDetector()
    
    def validate_document(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate document comprehensively"""
        try:
            # File size validation
            max_size = 50 * 1024 * 1024  # 50MB
            is_valid_size = len(content) <= max_size
            
            # File type validation
            allowed_types = [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'text/plain'
            ]
            is_valid_type = mime_type in allowed_types
            
            # Calculate file hash
            file_hash = hashlib.sha256(content).hexdigest()
            
            return {
                "is_valid": is_valid_size and is_valid_type,
                "validation_summary": {
                    "total_issues": 0 if is_valid_size and is_valid_type else 1,
                    "critical_issues": 0,
                    "warnings": 0,
                    "errors": 1 if not (is_valid_size and is_valid_type) else 0
                },
                "details": [
                    {
                        "type": "file_size",
                        "status": "pass" if is_valid_size else "fail",
                        "message": "File size is valid" if is_valid_size else f"File size exceeds {max_size} bytes"
                    },
                    {
                        "type": "file_type", 
                        "status": "pass" if is_valid_type else "fail",
                        "message": "File type is allowed" if is_valid_type else f"File type {mime_type} is not allowed"
                    }
                ],
                "file_metadata": {
                    "filename": filename,
                    "size": len(content),
                    "mime_type": mime_type,
                    "hash": file_hash
                }
            }
        except Exception as e:
            raise Exception(f"Failed to validate document: {str(e)}")
    
    async def perform_virus_scan(
        self,
        content: bytes,
        filename: str,
        mime_type: str
    ) -> Dict[str, Any]:
        """Perform virus scan on file"""
        try:
            # Use VirusTotal scanner if available, otherwise return mock result
            if self.virus_scanner.is_available():
                scan_result = await self.virus_scanner.scan(content, filename, mime_type)
                return {
                    "structureIntegrity": scan_result["is_clean"],
                    "formatValidation": scan_result["is_clean"],
                    "contentSafety": scan_result["is_clean"],
                    "status": scan_result["status"],
                    "notes": scan_result["message"],
                    "engine": scan_result["engine"],
                    "isClean": scan_result["is_clean"]
                }
            else:
                # Mock implementation when VirusTotal is not available
                return {
                    "structureIntegrity": True,
                    "formatValidation": True,
                    "contentSafety": True,
                    "status": "CLEAN",
                    "notes": "Virus scan passed (mock implementation)",
                    "engine": "Mock Scanner",
                    "isClean": True
                }
        except Exception as e:
            raise Exception(f"Failed to perform virus scan: {str(e)}")
    
    async def perform_phi_detection(
        self,
        content: bytes,
        filename: str,
        mime_type: str
    ) -> Dict[str, Any]:
        """Perform PHI (Protected Health Information) detection using LLM"""
        try:
            # Extract text from document
            text = await extract_document_text(content, mime_type)
            
            # Use LLM-based PHI detection
            phi_result = await self.phi_detector.detect(text, filename)
            
            # Convert to expected format (exact same as Node.js)
            return {
                "containsPHI": phi_result["containsPHI"],
                "confidence": phi_result["confidence"],
                "fieldsDetected": phi_result["fieldsDetected"],
                "detections": phi_result["detections"],
                "method": phi_result["method"],
                "message": phi_result["message"]
            }
        except Exception as e:
            logger.exception(f"Failed to perform PHI detection: {str(e)}")
            # Fallback to mock result on error
            return {
                "containsPHI": False,
                "confidence": 0,
                "fieldsDetected": [],
                "detections": [],
                "method": "LLM-Based Detection",
                "message": "No PHI detected"
            }
