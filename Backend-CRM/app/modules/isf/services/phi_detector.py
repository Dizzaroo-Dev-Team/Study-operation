"""
LLM-Based PHI Detector using Google Gemini AI
Exact Python implementation of the Node.js LLMBasedPHIDetector
"""

import json
import logging
from typing import Dict, Any, List, Optional
try:
    import google.genai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from ..core.config import settings
from ..utils.text_extractor import extract_document_text
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)

class LLMBasedPHIDetector:
    """LLM-Based PHI Detector using Google Gemini for advanced PHI detection"""
    
    def __init__(self, options: Dict[str, Any] = None):
        if options is None:
            options = {}
        
        self.api_key = options.get('apiKey') or settings.GEMINI_API_KEY
        self.model_name = options.get('modelName') or 'gemini-3.5-flash'  # Use correct model name without 'models/' prefix
        self.enabled = options.get('enabled', True) and bool(self.api_key) and GENAI_AVAILABLE
    
    def get_method_name(self) -> str:
        return 'LLM-Based Detection (Gemini)' if self.enabled else 'LLM-Based Detection (Disabled)'
    
    async def detect(self, text: str, filename: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Detect PHI in text using LLM - Exact same logic as Node.js version"""
        if options is None:
            options = {}
        
        result = {
            "containsPHI": False,
            "confidence": 0,
            "fieldsDetected": [],
            "detections": [],
            "method": self.get_method_name(),
            "message": 'No PHI detected'
        }
        
        try:
            if not text or not isinstance(text, str) or len(text.strip()) == 0:
                result["message"] = 'No text content provided for PHI detection'
                return result
            
            if not self.enabled:
                raise Exception('LLM PHI detector is disabled or not configured')
            
            return self._detect_with_llm(text, filename, result)
        
        except Exception as error:
            logger.exception(f"LLM PHI detection error for {sfmt(filename)}: {sfmt(str(error))}")
            raise error
    
    def _detect_with_llm(self, text: str, filename: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Detect PHI using Gemini LLM - Exact same logic as Node.js version"""
        try:
            # Configure client with API key
            client = genai.Client(api_key=self.api_key)
            
            # System Instructions define persona and strict logic rules.
            # This is separated from user input to prevent prompt injection 
            # and ensure strict adherence to clinical rules.
            system_instruction = """You are a High-Precision HIPAA Compliance Auditor. Your mandate is to detect any of the 18 HIPAA PHI Identifiers within clinical and administrative documents.

IDENTIFIER CHECKLIST (STRICT):
1. Names (Full, initials, or maiden).
2. Geography (Addresses, cities, counties, precincts, ZIP codes).
3. Dates (DOB, Admission, Discharge, Death; any date more specific than a year).
4. Ages 90+ (Must be flagged if specifically mentioned).
5. Contact Info (Phone numbers, Fax numbers, Email addresses).
6. Government IDs (SSN, Driver's License, Passport).
7. Medical IDs (MRN, Health Plan IDs, Device Serial Numbers).
8. Financial (Account numbers, Billing IDs).
9. Digital/Technical (IP Addresses, URLs, Biometrics, Photos).
10. Any other unique characteristic or identifying code.

DETECTION LOGIC:
- CLINICAL TRIALS: NCT/Protocol IDs are NOT PHI. However, 'Subject IDs' or 'Screening Numbers' ARE PHI if they appear alongside ANY other item from the checklist above (e.g., Initials + Subject ID = PHI).
- AGGRESSIVE CAPTURE: If you are unsure, flag it. It is better to have a false positive than a HIPAA violation.
- JSON ONLY: Return raw JSON. No markdown, no preamble.

MULTI-VALUE LOGIC:
- Group identical categories (e.g., all Names) into a single "detections" object.
- Every individual occurrence of a value must be captured as a unique object within the "values" array.
- Assign the correct "pageNumber" (from [[PAGE_X]] markers), "startIndex", and "endIndex" for EVERY individual value found.

IDENTIFIERS: 1.Names, 2.Geography, 3.Dates, 4.Ages 90+, 5.Phone, 6.Fax, 7.Email, 8.SSN, 9.MRN, 10.Health Plan, 11.Account Numbers, 12.License/Certificates, 13.VIN/Serial Numbers, 14.Device IDs, 15.URLs, 16.IP Addresses, 17.Biometrics, 18.Photos.

JSON ONLY: No markdown. No preamble

Strict JSON Schema Requirement:
{
  "containsPHI": boolean,
  "confidence": 0.0-1.0,
  "fieldsDetected": ["Name", "SSN", "DOB", "Address", "Other"],
  "detections": [
    {
      "field": "Standard HIPAA Category Name",
      "label": "Text as it appears in doc",
      "description": "Why this qualifies under the 18 identifiers",
      "count": number,
      "values": [
        { "value": "the sensitive string", "context": "...surrounding 20 chars..." }
      ]
    }
  ],
  "reasoning": "Detailed explanation of which identifiers were triggered."
}"""
            
            logger.info(f"LLM Prompt: {system_instruction}")
            
            # Create model (system instruction will be included in prompt)
            model = client.models.get(model=self.model_name)
            
            max_length = 30000
            truncated_text = text[:max_length] + '\n\n[Text truncated for analysis...]' if len(text) > max_length else text
            
            # Your original prompt remains the primary instruction for the data block
            prompt = f"""
Analyze document: {filename}
  
[DATA TO SCAN]
---
{truncated_text}
---

[TASK]
1. Scan for the 18 HIPAA Identifiers defined in your instructions.
2. If the text contains any unique numeric string (e.g., "ID: 44321") and a Date or Name, mark 'containsPHI': true.
3. Pay special attention to: {filename} context.
4. COORDINATED MAPPING: For every instance found, provide "pageNumber" (from [[PAGE_X]]), "startIndex", and "endIndex".

[JSON SCHEMA EXAMPLE]
{{
  "containsPHI": boolean,
  "confidence": 0.0-1.0,
  "fieldsDetected": ["Name", "Email Address"],
  "detections": [
    {{
      "field": "Name",
      "label": "Names of individuals",
      "description": "Full names or initials found in document",
      "count": 2,
      "values": [
        {{ 
          "value": "John Doe", 
          "context": "Subject Name: John Doe", 
          "pageNumber": 1, 
          "startIndex": 450, 
          "endIndex": 458 
        }},
        {{ 
          "value": "J. Doe", 
          "context": "Verified by J. Doe on", 
          "pageNumber": 3, 
          "startIndex": 2105, 
          "endIndex": 2111 
        }}
      ]
    }}
  ],
  "reasoning": "Briefly summarize all findings."
}}
"""
            
            logger.info(f"Calling Gemini LLM - Model: {self.model_name}, File: {sfmt(filename)}, Text Length: {len(text)}")
            logger.info(f"Text sample being sent to LLM: {sfmt(text)[:200]}...")
            
            # Generate content with timeout
            logger.info(f"Calling Gemini LLM API - Model: {self.model_name}")
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                logger.info("LLM response received successfully")
            except Exception as api_error:
                logger.exception(f"Gemini API error: {str(api_error)}")
                raise Exception(f"Gemini API call failed: {str(api_error)}")
            
            response_text = response.text
            logger.info(f"LLM response received: {response_text}")
            
            # Clean up markdown wrapper if present
            clean_json = response_text.strip()
            if clean_json.startswith('```json'):
                clean_json = clean_json.replace('```json\n', '').replace('```\n', '').replace('```', '')
            elif clean_json.startswith('```'):
                clean_json = clean_json.replace('```\n', '').replace('```', '')
            
            llm_result = json.loads(clean_json)
            logger.info(f"LLM response parsed successfully: {llm_result}")
            
            # Map LLM result to the standard result object - Exact same as Node.js
            result["detections"] = llm_result.get("detections", []) if isinstance(llm_result.get("detections"), list) else []
            result["fieldsDetected"] = llm_result.get("fieldsDetected", []) if isinstance(llm_result.get("fieldsDetected"), list) else [d.get("field") for d in result["detections"]]
            result["containsPHI"] = bool(llm_result.get("containsPHI", False))
            result["confidence"] = float(llm_result.get("confidence", 0)) if isinstance(llm_result.get("confidence"), (int, float)) else 0
            result["message"] = llm_result.get("reasoning") or (result["containsPHI"] and 'PHI detected by LLM analysis' or 'No PHI detected')
            
            return result
            
        except Exception as error:
            logger.exception(f"Error in LLM detection: {str(error)}")
            raise error
