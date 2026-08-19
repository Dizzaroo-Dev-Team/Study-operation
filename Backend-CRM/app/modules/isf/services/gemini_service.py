import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

try:
    import google.generativeai as genai
    from google.generativeai import GenerativeModel
    GENAI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai_old
        from google.generativeai import GenerativeModel
        GENAI_AVAILABLE = True
        import warnings
        warnings.warn("google.generativeai is deprecated. Please switch to google.genai package.")
    except ImportError:
        GENAI_AVAILABLE = False

from ..core.config import settings
from ..utils.document_extractor import extract_document_text
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)

class GeminiService:
    
    def __init__(self):
        self.tmf_schema_cache = None
        self.tmf_schema_path = Path(__file__).parent.parent / "constants" / "Version_3.3.1_TMF_Reference_Model_11-Aug-2023.xlsx"
        
        if settings.GEMINI_API_KEY and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                # Use same model preferences as Node.js
                preferred_models = [
                    settings.GOOGLE_GEMINI_MODEL or 'gemini-3.5-flash',
                    'gemini-flash-latest',
                    'gemini-3.1-flash-lite',
                ]
                
                for model_id in preferred_models:
                    try:
                        self.model = genai.GenerativeModel(model_id)
                        logger.info(f"Gemini model initialized successfully: {model_id}")
                        break
                    except Exception as e:
                        logger.warn(f"Failed to init model {model_id}: {e}")
                        continue
                
                if not hasattr(self, 'model'):
                    raise Exception("Failed to initialize any Gemini model")
                    
            except Exception as e:
                logger.exception(f"Failed to initialize Gemini: {e}")
                self.model = None
        else:
            self.model = None
    
    def format_title_from_filename(self, filename: str) -> str:
        """Format title from filename (Node.js equivalent)"""
        if not filename:
            return 'Untitled Document'
        try:
            # Remove extension
            name = re.sub(r'\.[^/.]+$', "", filename)
            # Replace underscores and hyphens with spaces
            name = re.sub(r'[_-]', ' ', name)
            # Title case
            return ' '.join(word.capitalize() for word in name.split() if word)
        except Exception:
            return filename or 'Untitled Document'
    
    def extract_keywords_from_content(self, text: str) -> List[str]:
        """Extract keywords from content (Node.js equivalent)"""
        if not isinstance(text, str):
            return []
        
        keywords = []
        
        # Medical and clinical trial keywords (same as Node.js)
        medical_keywords = [
            'protocol', 'consent', 'informed', 'clinical', 'trial', 'study', 'investigator',
            'brochure', 'regulatory', 'safety', 'adverse', 'event', 'serious', 'ae', 'sae',
            'fda', 'ema', 'irb', 'iec', 'ethics', 'committee', 'approval', 'submission',
            'drug', 'medication', 'treatment', 'therapy', 'patient', 'subject', 'participant',
            'randomization', 'blinding', 'placebo', 'control', 'intervention', 'arm',
            'endpoint', 'primary', 'secondary', 'outcome', 'measure', 'assessment',
            'laboratory', 'lab', 'test', 'result', 'analysis', 'statistical', 'statistics',
            'monitoring', 'monitor', 'cra', 'site', 'facility', 'hospital', 'clinic',
            'sponsor', 'cro', 'contract', 'agreement', 'quality', 'assurance', 'qa',
            'audit', 'inspection', 'compliance', 'gcp', 'ich', 'guideline', 'standard'
        ]
        
        # Check for medical keywords
        for keyword in medical_keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', text, re.IGNORECASE):
                keywords.append(keyword.lower())
        
        # Extract document-specific patterns
        patterns = {
            'protocol': r'protocol\s+(?:version|v|number|#)?\s*[:\-]?\s*([^\n\r]+)',
            'consent': r'(?:informed\s+)?consent\s+(?:form|document|version)?\s*[:\-]?\s*([^\n\r]+)',
            'brochure': r'(?:investigator\s+)?brochure\s*[:\-]?\s*([^\n\r]+)',
            'safety': r'safety\s+(?:report|document|assessment|analysis)\s*[:\-]?\s*([^\n\r]+)',
            'regulatory': r'regulatory\s+(?:submission|document|approval|authority)\s*[:\-]?\s*([^\n\r]+)'
        }
        
        for pattern_type, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                keywords.append(pattern_type)
                for match in matches:
                    extracted = match.strip()
                    if len(extracted) > 3:
                        keywords.append(extracted.lower())
        
        return list(set(keywords))
    
    def infer_document_type_from_content(self, text: str, filename: str) -> str:
        """Infer document type from content and filename (Node.js equivalent)"""
        if not isinstance(text, str):
            text = ''
        if not isinstance(filename, str):
            filename = ''
        
        lower_text = text.lower()
        lower_filename = filename.lower()
        
        # Same logic as Node.js
        if 'protocol' in lower_text or 'protocol' in lower_filename:
            return 'PROTOCOL'
        if 'consent' in lower_text or 'consent' in lower_filename:
            return 'INFORMED_CONSENT'
        if 'brochure' in lower_text or 'brochure' in lower_filename:
            return 'INVESTIGATOR_BROCHURE'
        if 'safety' in lower_text or 'safety' in lower_filename:
            return 'SAFETY_REPORT'
        if 'regulatory' in lower_text or 'regulatory' in lower_filename:
            return 'REGULATORY_DOCUMENT'
        if 'clinical' in lower_text and 'report' in lower_text:
            return 'CLINICAL_REPORT'
        if 'quality' in lower_text or 'qa' in lower_text:
            return 'QUALITY_DOCUMENT'
        if 'training' in lower_text or 'training' in lower_filename:
            return 'TRAINING_DOCUMENT'
        
        return 'OTHER'
    
    async def get_tmf_schema(self) -> str:
        """Load TMF schema from Excel file (Node.js equivalent)"""
        if self.tmf_schema_cache:
            return self.tmf_schema_cache
        
        try:
            if not self.tmf_schema_path.exists():
                logger.warn(f"TMF Schema Excel file not found: {self.tmf_schema_path}")
                return 'TMF Schema not available. Use standard TMF Reference Model zones (1-11).'
            
            import pandas as pd
            
            # Read Excel file
            df = pd.read_excel(self.tmf_schema_path, sheet_name=0, header=None)
            
            schema_items = []
            # Process rows similar to Node.js logic
            for i, row in df.iterrows():
                if len(row) < 6:
                    continue
                
                # Check if it looks like a data row (similar to Node.js logic)
                zone_val = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ''
                if zone_val and zone_val.replace('.', '').isdigit():
                    artifact_val = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ''
                    if '.' in artifact_val:
                        schema_items.append({
                            'zone': f"Zone {zone_val}: {str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''}",
                            'section': f"{str(row.iloc[2]) if pd.notna(row.iloc[2]) else ''}: {str(row.iloc[3]) if pd.notna(row.iloc[3]) else ''}",
                            'artifact': f"{artifact_val}: {str(row.iloc[5]) if pd.notna(row.iloc[5]) else ''}",
                            'subartifact': f"{str(row.iloc[6]) if pd.notna(row.iloc[6]) else ''}: {str(row.iloc[7]) if pd.notna(row.iloc[7]) else ''}",
                            'definition': str(row.iloc[8])[:100] if pd.notna(row.iloc[8]) else ''
                        })
            
            # Convert to string format similar to Node.js
            schema_string = '\n'.join([
                f"| {item['zone']} | {item['section']} | {item['artifact']} | {item['subartifact']} | {item['definition']} |"
                for item in schema_items
            ])
            
            self.tmf_schema_cache = schema_string[:100000]  # Safety cap
            return self.tmf_schema_cache
            
        except Exception as e:
            logger.exception(f"Failed to load TMF Schema: {e}")
            return 'Unable to load TMF Schema. Please use standard TMF zones.'
    
    def preprocess_content(self, text: str, filename: str) -> Dict[str, Any]:
        """Preprocess content (Node.js equivalent)"""
        if not isinstance(text, str):
            text = str(text or '')
        if not isinstance(filename, str):
            filename = str(filename or '')
        
        # Clean text
        cleaned_text = re.sub(r'\s+', ' ', text.strip())
        
        return {
            'text': cleaned_text,
            'language': 'en',
            'qualityScore': 0.8,
            'clinicalDensity': 25,
            'edgeCases': [],
            'originalLength': len(text),
            'cleanedLength': len(cleaned_text)
        }
    
    def parse_ai_response(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AI response (Node.js equivalent)"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                raise Exception('No JSON found in response')
            
            json_response = json.loads(json_match.group(0))
            
            # Map AI response to expected structure (same as Node.js)
            classification = {
                'confidence': 0,
                'suggestedZone': {'id': '00', 'number': '00', 'name': 'Unknown'},
                'suggestedSection': {'id': '00', 'number': '00', 'name': 'Unknown'},
                'suggestedArtifact': {'id': '00', 'number': '00', 'name': 'Unknown'},
                'suggestedSubartifact': '',
                'documentType': 'OTHER',
                'extractedMetadata': {},
                'classificationReasoning': ''
            }
            
            if 'classification' in json_response:
                classification['confidence'] = json_response['classification'].get('confidenceScore', 0)
                
                # Parse Zone
                zone_str = json_response['classification'].get('zone', '')
                zone_match = re.search(r'Zone\s+(\d+):\s+(.+)', zone_str) or re.search(r'Zone\s+(\d+)\s+(.+)', zone_str)
                if zone_match:
                    classification['suggestedZone'] = {
                        'id': zone_match.group(1).lstrip('0'),
                        'number': zone_match.group(1),
                        'name': zone_match.group(2).strip()
                    }
                
                # Parse Section
                section_str = json_response['classification'].get('section', '')
                classification['suggestedSection'] = section_str.split(':')[0].strip()
                
                # Parse Artifact
                artifact_str = json_response['classification'].get('artifact', '')
                classification['suggestedArtifact'] = artifact_str.split(':')[0].strip()
                
                classification['suggestedSubartifact'] = json_response['classification'].get('subartifact', '')
                
                # Infer document type
                classification['documentType'] = self.infer_document_type_from_artifact(
                    classification['suggestedArtifact'], 
                    classification['suggestedZone'].get('name', '')
                )
            
            if 'metadata' in json_response:
                metadata_response = json_response['metadata']
                
                # Handle title
                title = metadata_response.get('documentTitle') or metadata_response.get('title')
                if not title or title.strip() == '' or title.upper() == 'N/A':
                    title = metadata.get('title', '')
                if not title or title.strip() == '' or title.upper() == 'N/A' or title == 'Unknown':
                    title = self.format_title_from_filename(metadata.get('fileName', ''))
                
                classification['extractedMetadata'] = {
                    'title': title,
                    'description': f"Protocol: {metadata_response.get('protocolId', 'N/A')}, Site: {metadata_response.get('siteId', 'N/A')}",
                    'author': metadata_response.get('investigatorName') or metadata.get('author', ''),
                    'documentDate': metadata_response.get('documentDate') or metadata.get('date', ''),
                    'version': metadata.get('version', '1.0'),
                    'keywords': metadata_response.get('keywords', []),
                    'contentSummary': json_response.get('reasoning', ''),
                    'language': metadata_response.get('language', 'en'),
                    'pageCount': metadata.get('pageCount', 0),
                    'wordCount': metadata.get('wordCount', 0),
                    # Extended metadata
                    'protocolId': metadata_response.get('protocolId'),
                    'siteId': metadata_response.get('siteId'),
                    'investigatorName': metadata_response.get('investigatorName'),
                    'country': metadata_response.get('country')
                }
            
            classification['classificationReasoning'] = json_response.get('reasoning', '')
            
            # Ensure confidence is valid
            try:
                classification['confidence'] = max(0, min(1, float(classification['confidence'])))
            except (ValueError, TypeError):
                classification['confidence'] = 0
            
            # Add default validations (same as Node.js)
            classification['contentAnalysis'] = {
                'keyTopics': [],
                'documentPurpose': classification['suggestedArtifact'],
                'targetAudience': 'StartUp',
                'regulatoryRelevance': 'High',
                'clinicalTerminologyCount': 0,
                'nonClinicalTerminologyCount': 0,
                'contentQuality': 'medium',
                'edgeCaseFlags': []
            }
            
            classification['validationFlags'] = {
                'isClinicalContent': classification['confidence'] > 0.5,
                'hasRegulatoryTerms': True,
                'isCompleteDocument': True,
                'isReadable': True,
                'isRelevantToTMF': True,
                'edgeCases': [],
                'contentQuality': 0.8,
                'clinicalDensity': 10
            }
            
            classification['qcValidation'] = self.get_default_qc_validation()
            
            return classification
            
        except Exception as e:
            logger.exception(f"Error parsing AI response: {e}")
            # Return fallback classification
            return {
                'confidence': 0.1,
                'suggestedZone': {'id': '11', 'number': '11', 'name': 'Statistics'},
                'suggestedSection': '11.01.01',
                'suggestedArtifact': 'Document',
                'suggestedSubartifact': 'Document',
                'documentType': 'OTHER',
                'extractedMetadata': {
                    'title': metadata.get('title', 'Unknown Document'),
                    'description': 'Fallback classification due to parsing error',
                    'author': metadata.get('author', ''),
                    'documentDate': '',
                    'version': '1.0',
                    'keywords': [],
                    'contentSummary': 'Document could not be properly classified',
                    'language': 'en',
                    'pageCount': 1,
                    'wordCount': 0
                },
                'classificationReasoning': f"Fallback classification due to AI response parsing error: {str(e)}",
                'contentAnalysis': {
                    'keyTopics': [],
                    'documentPurpose': 'Unknown',
                    'targetAudience': 'Unknown',
                    'regulatoryRelevance': 'Unknown',
                    'clinicalTerminologyCount': 0,
                    'nonClinicalTerminologyCount': 0,
                    'contentQuality': 'low',
                    'edgeCaseFlags': ['parsing_error']
                },
                'qualityScore': 0.1,
                'completenessScore': 0.1,
                'validationFlags': {
                    'isClinicalContent': False,
                    'hasRegulatoryTerms': False,
                    'isCompleteDocument': False,
                    'isReadable': False,
                    'isRelevantToTMF': False,
                    'edgeCases': ['parsing_error'],
                    'contentQuality': 0.1,
                    'clinicalDensity': 0
                },
                'qcValidation': self.get_default_qc_validation()
            }
    
    def infer_document_type_from_artifact(self, artifact: str, zone_name: str) -> str:
        """Infer document type from artifact and zone (Node.js equivalent)"""
        artifact_lower = artifact.lower()
        zone_lower = zone_name.lower()
        
        # Same mapping logic as Node.js
        if 'protocol' in artifact_lower:
            return 'PROTOCOL'
        if 'consent' in artifact_lower:
            return 'INFORMED_CONSENT'
        if 'brochure' in artifact_lower:
            return 'INVESTIGATOR_BROCHURE'
        if 'regulatory' in zone_lower:
            return 'REGULATORY_DOCUMENT'
        if 'safety' in artifact_lower:
            return 'SAFETY_REPORT'
        if 'quality' in zone_lower:
            return 'QUALITY_DOCUMENT'
        if 'training' in zone_lower:
            return 'TRAINING_DOCUMENT'
        if 'data' in artifact_lower:
            return 'CLINICAL_REPORT'
        if 'statistics' in zone_lower:
            return 'CLINICAL_REPORT'
        
        return 'OTHER'
    
    def get_default_qc_validation(self) -> Dict[str, Any]:
        """Get default QC validation (Node.js equivalent)"""
        return {
            'hasRequiredFields': True,
            'fieldCompleteness': 0.8,
            'dataConsistency': 0.9,
            'formatCompliance': 0.85,
            'overallScore': 0.85,
            'recommendations': [],
            'warnings': []
        }
    
    async def classify_document_with_content(
        self, 
        content: bytes, 
        filename: str, 
        mime_type: str
    ) -> Dict[str, Any]:
        """Classify document using Gemini AI with content analysis (Node.js equivalent)"""
        if not self.model:
            raise Exception("Gemini service not configured")
        
        try:
            logger.info(f"Classifying document with content analysis: {sfmt(filename)}")
            
            # Extract document content
            extracted_text = await extract_document_text(content, mime_type)
            metadata = {
                'title': self.format_title_from_filename(filename),
                'author': '',
                'version': '1.0',
                'date': '',
                'keywords': [],
                'documentType': 'UNKNOWN',
                'pageCount': 0,
                'wordCount': len(extracted_text.split()) if extracted_text else 0,
                'fileName': filename
            }
            
            # Preprocess content
            processed_content = self.preprocess_content(extracted_text, filename)
            
            # Load TMF Schema
            tmf_schema = await self.get_tmf_schema()
            
            # Construct prompt (same as Node.js)
            prompt = f"""Role: You are an expert Clinical Records Specialist and TMF Reference Model Validator. Your task is to analyze text content of a provided clinical trial document, classify it according to Trial Master File Reference Model (TMF RM), and extract all relevant metadata.

Objective: Map the input document to the correct Zone, Section, and Artifact within the TMF Reference Model hierarchy. You must also identify the specific Sub-Artifact (if applicable) and extract metadata defined by [METADATA_SCHEMA].

Input Context:

TMF Reference Model Schema: 
{tmf_schema}

Document Text: 
{processed_content['text']}

Instructions:

Content Analysis:

Scan the document for keywords, headers, and form titles (e.g., "1572", "CV", "Monitoring Visit Report", "Ethics Committee Approval").

Analyze the semantic context. Differentiate between similar documents (e.g., a "Protocol Amendment" vs. a "Protocol Clarification Letter").

Constraint: Pay close attention to distinguishing between Sponsor/CRO-generated documents and Site-generated documents.

Classification (TMF Mapping):

Assign the Zone (e.g., Zone 05: Site Management).

Assign the Section (e.g., 05.02: Site Initiation).

Assign the Artifact (e.g., 05.02.04: Site Initiation Visit Report).

Assign the Recommended Subartifacts

Confidence Score: Provide a confidence score (0.0 - 1.0) for this classification. If confidence is below 0.7, flag for human review.

Metadata Extraction:

Protocol ID: Extract the Study/Protocol Number (e.g., "DS-XXXX-001").

Site ID: Extract the Site Number (if applicable).

Investigator Name: Extract the Principal Investigator's name (if applicable).

Document Date: Extract the effective date of the document (YYYY-MM-DD).

Approval Date: Extract the approval date of the document (YYYY-MM-DD).

Country: Identify the country associated with the document.

Language: Detect the primary language.

Reasoning:

Briefly explain why this classification was chosen (e.g., "Document contains header 'Statement of Investigator' and references Form FDA 1572").

Return ONLY JSON in this format:
{{
  "classification": {{
    "zone": "Zone XX: Name",
    "section": "XX.XX",
    "artifact": "XX.XX.XX",
    "subartifact": "Name",
    "confidenceScore": <0.0-1.0>
  }},
  "metadata": {{
    "protocolId": "<extracted identifier>",
    "siteId": "<extracted identifier>",
    "investigatorName": "<extracted name>",
    "documentDate": "<YYYY-MM-DD>",
    "approvalDate": "<YYYY-MM-DD>",
    "country": "<extracted country>",
    "language": "<detected language>"
  }},
  "reasoning": "<explanation>"
}}"""
            
            # Generate content with Gemini
            result = self.model.generate_content(prompt)
            response = result.candidates[0].content.parts[0].text if result.candidates else ""
            
            # Parse AI response
            classification = self.parse_ai_response(response, metadata)
            
            logger.info(f"Document classified successfully: {sfmt(filename)}, confidence: {classification['confidence']}")
            
            return {
                'success': True,
                'classification': classification,
                'extractedContent': {
                    'text': extracted_text,
                    'metadata': metadata,
                    'processedContent': processed_content
                }
            }
            
        except Exception as e:
            logger.exception(f"Error in content-based classification: {e}")
            # Return fallback classification
            return {
                'success': True,
                'classification': {
                    'confidence': 0.1,
                    'suggestedZone': {'id': '11', 'number': '11', 'name': 'Statistics'},
                    'suggestedSection': '11.01.01',
                    'suggestedArtifact': 'Document',
                    'suggestedSubartifact': 'Document',
                    'documentType': 'OTHER',
                    'extractedMetadata': {
                        'title': filename or 'Unknown Document',
                        'description': 'Fallback classification due to processing error',
                        'author': '',
                        'documentDate': '',
                        'version': '1.0',
                        'keywords': [],
                        'contentSummary': 'Document could not be processed due to error',
                        'language': 'en',
                        'pageCount': 1,
                        'wordCount': 0
                    },
                    'classificationReasoning': f"Fallback classification due to processing error: {str(e)}",
                    'contentAnalysis': {
                        'keyTopics': [],
                        'documentPurpose': 'Unknown',
                        'targetAudience': 'Unknown',
                        'regulatoryRelevance': 'Unknown',
                        'clinicalTerminologyCount': 0,
                        'nonClinicalTerminologyCount': 0,
                        'contentQuality': 'low',
                        'edgeCaseFlags': ['processing_error']
                    },
                    'qualityScore': 0.1,
                    'completenessScore': 0.1,
                    'validationFlags': {
                        'isClinicalContent': False,
                        'hasRegulatoryTerms': False,
                        'isCompleteDocument': False,
                        'isReadable': False,
                        'isRelevantToTMF': False,
                        'edgeCases': ['processing_error'],
                        'contentQuality': 0.1,
                        'clinicalDensity': 0
                    },
                    'qcValidation': self.get_default_qc_validation()
                },
                'extractedContent': {
                    'text': str(extracted_text or ''),
                    'metadata': {
                        'title': filename or 'Unknown Document',
                        'author': '',
                        'date': '',
                        'version': '1.0',
                        'keywords': [],
                        'pageCount': 1,
                        'wordCount': 0
                    },
                    'processedContent': {
                        'text': str(extracted_text or ''),
                        'language': 'en',
                        'qualityScore': 0.1,
                        'clinicalDensity': 0,
                        'edgeCases': ['processing_error'],
                        'originalLength': 0,
                        'cleanedLength': 0
                    }
                }
            }
    
    async def classify_document(
        self, 
        content: bytes, 
        filename: str, 
        mime_type: str,
        document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Classify document using Gemini AI (main entry point)"""
        if not self.model:
            raise Exception("Gemini service not configured")
        
        try:
            # Use the enhanced classification method
            result = await self.classify_document_with_content(content, filename, mime_type)
            
            if result.get('success'):
                return result['classification']
            else:
                raise Exception("Classification failed")
                
        except Exception as e:
            logger.exception(f"Failed to classify document: {e}")
            raise Exception(f"Failed to classify document: {str(e)}")
    
    async def extract_metadata(
        self, 
        content: bytes, 
        filename: str, 
        mime_type: str
    ) -> Dict[str, Any]:
        """Extract metadata from document using Gemini AI"""
        if not self.model:
            raise Exception("Gemini service not configured")
        
        try:
            # Extract text first
            extracted_text = await extract_document_text(content, mime_type)
            
            # Use a simpler prompt for metadata extraction
            prompt = f"""Extract metadata from the following document content. Return ONLY JSON in this format:

{{
  "title": "<document title>",
  "author": "<author name>",
  "creation_date": "<YYYY-MM-DD>",
  "page_count": <number>,
  "language": "<detected language>",
  "keywords": ["keyword1", "keyword2"],
  "summary": "<brief summary>",
  "entities": ["entity1", "entity2"],
  "document_structure": {{
    "sections": ["section1", "section2"],
    "headers": ["header1", "header2"]
  }}
}}

Document content:
{extracted_text[:10000]}"""
            
            # genai.GenerativeModel.generate_content is SYNC — `await`ing it
            # raised TypeError at runtime every time this metadata-extraction
            # path ran. Offload to the default thread executor instead so the
            # async caller does not block the event loop on a 5-30s Gemini call.
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.model.generate_content(prompt)
            )
            response = result.text
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    metadata = json.loads(json_match.group(0))
                    # Ensure required fields
                    return {
                        'title': metadata.get('title', self.format_title_from_filename(filename)),
                        'author': metadata.get('author', 'Unknown'),
                        'creation_date': metadata.get('creation_date'),
                        'page_count': metadata.get('page_count'),
                        'language': metadata.get('language', 'en'),
                        'keywords': metadata.get('keywords', []),
                        'summary': metadata.get('summary', ''),
                        'entities': metadata.get('entities', []),
                        'document_structure': metadata.get('document_structure', {})
                    }
                except json.JSONDecodeError:
                    pass
            
            # Fallback metadata
            return {
                'title': self.format_title_from_filename(filename),
                'author': 'Unknown',
                'creation_date': None,
                'page_count': None,
                'language': 'en',
                'keywords': [],
                'summary': '',
                'entities': [],
                'document_structure': {}
            }
            
        except Exception as e:
            logger.exception(f"Failed to extract metadata: {e}")
            raise Exception(f"Failed to extract metadata: {str(e)}")
