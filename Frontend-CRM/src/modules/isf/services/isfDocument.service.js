import { config } from '../config/config';
import axios from 'axios';
import authService from './auth.service';

// config.API_URL (= VITE_API_BASE) already ends with /api — do NOT add /api again
const API_URL = `${config.API_URL}/isf-documents`;
const DOCUMENTS_API_URL = `${config.API_URL}/isf-documents`;

/**
 * Normalize document from API (snake_case) to camelCase shape expected by workflow and ISFIntakeStageForm.
 * Idempotent: if data is already camelCase, returns it with _id ensured.
 */
function normalizeDocumentFromApi(data) {
    if (!data || typeof data !== 'object') return data;
    const d = data;
    const hasSnake = 'document_type' in d || 'tmf_reference' in d || 'custom_metadata' in d || 'file_url' in d;
    if (!hasSnake) {
        return { ...data, _id: data._id ?? data.id ?? data.documentId };
    }
    return {
        ...data,
        _id: d._id ?? d.id ?? d.document_id,
        documentId: d.documentId ?? d.document_id,
        title: d.title,
        documentTitle: d.documentTitle ?? d.title,
        description: d.description,
        documentType: d.documentType ?? d.document_type,
        tmfReference: d.tmfReference ?? d.tmf_reference,
        version: d.version,
        study: d.study,
        country: d.country,
        site: d.site,
        fileUrl: d.fileUrl ?? d.file_url,
        fileSize: d.fileSize ?? d.file_size,
        mimeType: d.mimeType ?? d.mime_type,
        fileHash: d.fileHash ?? d.file_hash,
        pageCount: d.pageCount ?? d.page_count,
        legibilityClear: d.legibilityClear ?? d.legibility_clear,
        ingestionType: d.ingestionType ?? d.ingestion_type,
        language: d.language,
        documentDate: d.documentDate ?? d.document_date,
        creationDate: d.creationDate ?? d.creation_date,
        modificationDate: d.modificationDate ?? d.modification_date,
        approvalDate: d.approvalDate ?? d.approval_date,
        expirationDate: d.expirationDate ?? d.expiration_date,
        author: d.author,
        uploadedBy: d.uploadedBy ?? d.uploaded_by,
        createdBy: d.createdBy ?? d.created_by,
        status: d.status,
        qualityControlStatus: d.quality_control_status ?? d.qualityControlStatus,
        completenessStatus: d.completeness_status ?? d.completenessStatus,
        archivalStatus: d.archival_status ?? d.archivalStatus,
        workflowSummary: d.workflowSummary ?? d.workflow_summary,
        auditTrail: d.auditTrail ?? d.audit_trail,
        customMetadata: d.customMetadata ?? d.custom_metadata,
        zone: d.zone,
        section: d.section,
        artifact: d.artifact,
        subArtifact: d.subArtifact ?? d.sub_artifact,
        virusStatus: d.virusStatus ?? d.virus_status ?? d.customMetadata?.validation?.virusScan?.status ?? d.custom_metadata?.validation?.virusScan?.status,
        duplicateStatus: d.duplicateStatus ?? d.duplicate_status,
        previousVersions: d.previousVersions ?? d.previous_versions,
    };
}

// Ensure we always use a valid backend user id for TMF uploads
// Ensure we always use a valid backend user id for TMF uploads
const ensureBackendUserId = async () => {
    try {
        // Try to get current user from auth service first
        const currentUser = authService.getCurrentUser();
        if (currentUser && (currentUser._id || currentUser.id)) {
            const userId = currentUser._id || currentUser.id;
            console.log('Using authenticated user for upload:', userId);
            return userId;
        }

        // Get auth token if available
        const token = authService.getToken() || localStorage.getItem('auth_token') || localStorage.getItem('auth_token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        // Prefer an existing real user from the backend
        const usersResponse = await axios.get(`${config.API_URL}/users`, {
            params: { page: 1, limit: 10 },
            headers
        });

        if (usersResponse.data?.data && Array.isArray(usersResponse.data.data) && usersResponse.data.data.length > 0) {
            const firstUser = usersResponse.data.data[0];
            console.log('Using backend user for upload:', firstUser._id, firstUser.email);
            return firstUser._id || firstUser.id;
        }

        // If no users in response, try alternative response format
        if (usersResponse.data && Array.isArray(usersResponse.data) && usersResponse.data.length > 0) {
            const firstUser = usersResponse.data[0];
            console.log('Using backend user (alt format) for upload:', firstUser._id || firstUser.id);
            return firstUser._id || firstUser.id;
        }

        // Fallback: use the CRM user's ID from localStorage
        // Honour hub-mode (sharedAuthService) before falling back to legacy localStorage.
        const crmUser = (() => { try { return authService.getCurrentUser?.() || JSON.parse(localStorage.getItem('auth_user') || '{}'); } catch { return {}; } })();
        const crmUserId = crmUser?.user_id || crmUser?.id || '';
        console.warn('No users found from backend — using CRM session user ID:', crmUserId || '(none)');
        return crmUserId;
    } catch (error) {
        console.error('Error resolving backend user id for TMF upload:', error);
        // Fallback: use the CRM user's ID from localStorage
        // Honour hub-mode (sharedAuthService) before falling back to legacy localStorage.
        const crmUser = (() => { try { return authService.getCurrentUser?.() || JSON.parse(localStorage.getItem('auth_user') || '{}'); } catch { return {}; } })();
        const crmUserId = crmUser?.user_id || crmUser?.id || '';
        console.warn('Falling back to CRM session user ID:', crmUserId || '(none)');
        return crmUserId;
    }
};

const isfDocumentService = {
    create: async (formData) => {
        try {
            // Always resolve a valid backend user id for TMF uploads
            const userId = await ensureBackendUserId();

            // Create a new FormData object for the request
            const requestFormData = new FormData();

            // Add the file if it exists
            const file = formData.get('file');
            if (file) {
                requestFormData.append('file', file);
            }

            // Get current user for upload tracking
            const currentUser = authService.getCurrentUser();
            const uploaderId = currentUser?.id || currentUser?._id || userId;
            const uploaderEmail = currentUser?.email || '';

            // Create metadata object with all required fields from the Document model
            const documentTitle = formData.get('artifactName') || formData.get('title') || '';
            const studyId = formData.get('study') || formData.get('studyId') || '';

            const metadata = {
                documentTitle, // Required by backend
                version: formData.get('version'),
                zoneNumber: formData.get('zoneNumber'),
                zoneName: formData.get('zoneName'),
                zoneDescription: formData.get('zoneDescription') || '',
                sectionNumber: formData.get('sectionNumber'),
                sectionName: formData.get('sectionName'),
                sectionDescription: formData.get('sectionDescription') || '',
                artifactNumber: formData.get('artifactNumber'),
                artifactName: formData.get('artifactName'),
                artifactDescription: formData.get('artifactDescription') || '',
                subArtifactName: formData.get('subArtifactName') || '',
                subArtifactDescription: formData.get('subArtifactDescription') || '',
                mandatory: formData.get('mandatory') === 'true' || formData.get('mandatory') === true,
                status: formData.get('status') || 'DRAFT',
                uploadDate: formData.get('uploadDate') || new Date().toISOString(),
                fileName: formData.get('fileName'),
                fileSize: parseInt(formData.get('fileSize')),
                fileFormat: formData.get('fileFormat'),
                documentId: formData.get('documentId') || `doc_${Date.now()}`,
                title: documentTitle,
                description: formData.get('description') || '',
                documentType: formData.get('documentType') || 'OTHER',
                tmfReference: formData.get('tmfReference') || '',
                study: studyId, // Ensure study is recorded
                country: formData.get('country') || '',
                site: formData.get('site') || '',
                fileUrl: formData.get('fileUrl') || '',
                mimeType: formData.get('fileFormat'),
                pageCount: formData.get('pageCount') ? Number(formData.get('pageCount')) : undefined,
                documentDate: formData.get('documentDate') || new Date().toISOString(),
                author: formData.get('author') || uploaderEmail,
                legibilityClear: null, // Default to null for new uploads
                uploadedBy: formData.get('uploadedBy') || uploaderId || uploaderEmail, // Record uploader
                createdBy: uploaderId || uploaderEmail, // Record creator
                lastModifiedBy: uploaderId || uploaderEmail // Record modifier
            };

            // Add metadata as a JSON string
            requestFormData.append('metadata', JSON.stringify(metadata));

            console.log('Uploading TMF document to URL:', `${API_URL}/${userId}`);

            // Get auth token if available
            const token = authService.getToken() || localStorage.getItem('auth_token') || localStorage.getItem('auth_token');
            const headers = {
                'Content-Type': 'multipart/form-data'
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            // Use the TMF documents API for file uploads (supports multipart)
            const response = await axios.post(`${API_URL}/${userId}`, requestFormData, {
                headers
            });
            return response.data;
        } catch (error) {
            console.error("Error in isfDocumentService.create:", error);
            console.error("Error response:", error.response?.data);
            throw error;
        }
    },

    getAllDocuments: async (options = {}) => {
        try {
            // Build query parameters
            const params = new URLSearchParams();
            if (options.isfViewer) {
                params.append('isfViewer', 'true');
            }
            if (options.study) {
                params.append('study', options.study);
            }
            if (options.status) {
                params.append('status', options.status);
            }
            if (options.limit) {
                params.append('limit', options.limit);
            }
            if (options.page) {
                params.append('page', options.page);
            }

            // Use documents endpoint (not TMF endpoint) to get populated documents with zone, section, artifact, subArtifact
            // The backend will populate these references when tmfViewer=true
            const url = params.toString() ? `${DOCUMENTS_API_URL}?${params.toString()}` : DOCUMENTS_API_URL;
            console.log(`[isfDocumentService.getAllDocuments] Calling API: ${url}`);
            const response = await axios.get(url);

            // Handle the paginated response format
            let documents = [];
            if (response.data && response.data.data && Array.isArray(response.data.data)) {
                documents = response.data.data; // Return the documents array
            } else if (Array.isArray(response.data)) {
                documents = response.data; // Direct array response
            } else {
                console.warn('Unexpected response format:', response.data);
                return [];
            }

            // Normalize each document (snake_case -> camelCase, ensure _id and tmfReference) so hierarchy and table display work
            const normalized = documents.map((d) => normalizeDocumentFromApi(d));

            // Log sample document to verify population
            if (normalized.length > 0 && options.tmfViewer) {
                const sampleDoc = normalized[0];
                console.log(`[isfDocumentService.getAllDocuments] Fetched ${normalized.length} documents. Sample document TMF metadata:`, {
                    title: sampleDoc.title || sampleDoc.documentTitle,
                    zone: sampleDoc.zone ? {
                        _id: sampleDoc.zone._id,
                        zoneNumber: sampleDoc.zone.zoneNumber,
                        zoneName: sampleDoc.zone.zoneName,
                        type: typeof sampleDoc.zone
                    } : null,
                    section: sampleDoc.section ? {
                        _id: sampleDoc.section._id,
                        sectionNumber: sampleDoc.section.sectionNumber,
                        sectionName: sampleDoc.section.sectionName,
                        type: typeof sampleDoc.section
                    } : null,
                    artifact: sampleDoc.artifact ? {
                        _id: sampleDoc.artifact._id,
                        artifactNumber: sampleDoc.artifact.artifactNumber,
                        artifactName: sampleDoc.artifact.artifactName,
                        type: typeof sampleDoc.artifact
                    } : null,
                    subArtifact: sampleDoc.subArtifact ? {
                        _id: sampleDoc.subArtifact._id,
                        subArtifactName: sampleDoc.subArtifact.subArtifactName,
                        type: typeof sampleDoc.subArtifact
                    } : null,
                });
            }

            return normalized;
        } catch (error) {
            console.error("Error in isfDocumentService.getAllDocuments:", error);
            throw error;
        }
    },

    updateTMFMetadata: async (documentId, metadata) => {
        try {
            const response = await axios.patch(`${DOCUMENTS_API_URL}/${documentId}/tmf-metadata`, metadata);
            return response.data;
        } catch (error) {
            console.error("Error in isfDocumentService.updateTMFMetadata:", error);
            throw error;
        }
    },

    getDocument: async (id) => {
        if (!id) {
            throw new Error('Missing document identifier');
        }

        const encodedId = encodeURIComponent(id);
        const isMongoId = /^[0-9a-fA-F]{24}$/u.test(id);
        let lastError = null;

        const tryFetch = async (url) => {
            const response = await axios.get(url);
            const raw = response.data?.data || response.data;
            const data = normalizeDocumentFromApi(raw);
            if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
                console.log(`[isfDocumentService.getDocument] Fetched from ${url}:`, {
                    hasData: !!data,
                    hasZone: !!data?.zone,
                    hasSection: !!data?.section,
                    hasArtifact: !!data?.artifact,
                    hasSubArtifact: !!data?.subArtifact,
                    zoneType: typeof data?.zone,
                    sectionType: typeof data?.section,
                    artifactType: typeof data?.artifact,
                    subArtifactType: typeof data?.subArtifact
                });
            }
            return data;
        };

        // Always try TMF endpoint first (it always populates zone/section/artifact/subArtifact)
        if (isMongoId) {
            try {
                const tmfData = await tryFetch(`${API_URL}/${encodedId}`);
                console.log('[isfDocumentService.getDocument] TMF endpoint response:', {
                    hasData: !!tmfData,
                    hasZone: !!tmfData?.zone,
                    hasSection: !!tmfData?.section,
                    hasArtifact: !!tmfData?.artifact,
                    hasSubArtifact: !!tmfData?.subArtifact
                });
                // Return TMF data even if metadata is missing (it's still the most reliable endpoint)
                if (tmfData) {
                    return tmfData;
                }
            } catch (error) {
                console.warn("TMF endpoint fetch failed, trying documents endpoint:", error?.response?.status);
                lastError = error;
            }
        }

        // Fallback to documents endpoint
        if (isMongoId) {
            try {
                const docData = await tryFetch(`${DOCUMENTS_API_URL}/${encodedId}`);
                console.log('[isfDocumentService.getDocument] Documents endpoint response:', {
                    hasData: !!docData,
                    hasZone: !!docData?.zone,
                    hasSection: !!docData?.section,
                    hasArtifact: !!docData?.artifact,
                    hasSubArtifact: !!docData?.subArtifact
                });
                return docData;
            } catch (error) {
                lastError = error;
                console.warn("Documents endpoint fetch failed:", error?.response?.status);
            }
        }

        // Last resort: try TMF endpoint again
        try {
            return await tryFetch(`${API_URL}/${encodedId}`);
        } catch (error) {
            console.error("Error in isfDocumentService.getDocument:", error);
            throw lastError || error;
        }
    },

    // Get all comments for a document (TMF route)
    getComments: async (documentId) => {
        try {
            const response = await axios.get(`${API_URL}/${documentId}/comments`);
            return response.data;
        } catch (error) {
            console.error("Error in isfDocumentService.getComments:", error);
            throw error;
        }
    },

    // Add a comment to a document (TMF route)
    addComment: async (documentId, content, userId) => {
        try {
            const response = await axios.post(`${API_URL}/${documentId}/comments`, {
                content,
                userId
            });
            return response.data;
        } catch (error) {
            console.error("Error in isfDocumentService.addComment:", error);
            throw error;
        }
    },

    // Add a reply to a comment
    addReply: async (documentId, commentId, content, userId) => {
        try {
            const response = await axios.post(`${DOCUMENTS_API_URL}/${documentId}/comments/${commentId}/replies`, {
                content,
                userId
            });
            return response.data;
        } catch (error) {
            console.error("Error in isfDocumentService.addReply:", error);
            throw error;
        }
    },

    async uploadDocument(file, metadata = {}) {
        try {
            // Get current user ID from auth service
            const currentUser = authService.getCurrentUser();
            let userId = currentUser?.id || currentUser?._id;

            // If no valid user ID, ensure backend user exists
            if (!userId || userId === '1' || userId === 'default-user') {
                userId = await ensureBackendUserId();
                // console.log('Using user ID:', userId); // removed for production
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('user_id', userId);
            formData.append('title', metadata.title || file.name.replace(/\.[^/.]+$/, ''));
            formData.append('description', metadata.description || '');
            formData.append('document_type', metadata.documentType || 'OTHER');
            formData.append('tmf_reference', metadata.tmfReference || '');
            formData.append('document_date', metadata.documentDate || new Date().toISOString().split('T')[0]);
            // Always send study/site/country as explicit form fields so the backend
            // can read them directly without having to parse the JSON metadata blob.
            formData.append('study', metadata.study || '');
            formData.append('site', metadata.site || '');
            formData.append('country', metadata.country || '');

            // CRITICAL FIX: Append the full metadata as a JSON string so the FastAPI backend
            // can parse TMF hierarchy fields (zoneNumber, zoneName, sectionNumber, sectionName,
            // artifactNumber, artifactName, subArtifactName, etc.) from raw_meta.
            // Without this, raw_meta was always empty ({}) and TMF zone/section/artifact
            // could never be resolved from the user-provided metadata.
            formData.append('metadata', JSON.stringify(metadata));

            console.log('Uploading to URL:', `${API_URL}/upload`);
            console.log('Metadata being sent:', metadata);
            console.log('TMF fields in metadata:', {
                zoneNumber: metadata.zoneNumber,
                zoneName: metadata.zoneName,
                sectionNumber: metadata.sectionNumber,
                sectionName: metadata.sectionName,
                artifactNumber: metadata.artifactNumber,
                artifactName: metadata.artifactName,
                subArtifactName: metadata.subArtifactName,
            });

            // Use the upload API endpoint for file uploads
            const response = await axios.post(`${API_URL}/upload`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                onUploadProgress: (progressEvent) => {
                    const percentCompleted = Math.round(
                        (progressEvent.loaded * 100) / progressEvent.total
                    );
                    // Reserved for optional progress UI
                },
            });

            const payload = response.data || {};
            return {
                success: true,
                document: payload.document,
                data: payload.document,
                validation: payload.validation,
                message: payload.message,
            };
        } catch (error) {
            console.error("Error in uploadDocument:", error);
            console.error("Error response:", error.response?.data);
            const errorPayload = error.response?.data || {};
            return {
                success: false,
                error: errorPayload.error || 'Failed to upload document',
                message: errorPayload.message || errorPayload.error || 'Failed to upload document',
                status: error.response?.status,
                validation: errorPayload.validation,
                existingDocumentId: errorPayload.existingDocumentId,
                details: errorPayload
            };
        }
    },

    // Update document with new file and metadata
    async updateDocument(file, metadata = {}) {
        try {
            const currentUser = authService.getCurrentUser();
            let userId = currentUser?.id || currentUser?._id;

            // If no valid user ID, ensure backend user exists
            if (!userId || userId === '1' || userId === 'default-user') {
                userId = await ensureBackendUserId();
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('metadata', JSON.stringify(metadata));

            console.log('Updating document with:', {
                fileName: file?.name,
                fileSize: file?.size,
                mimeType: file?.type,
                metadata
            });

            // Use the TMF documents update API endpoint
            const response = await axios.post(`${API_URL}/update/${userId}`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });

            const payload = response.data || {};
            return {
                success: true,
                document: payload.document,
                data: payload.document,
                validation: payload.validation,
                message: payload.message,
            };
        } catch (error) {
            console.error("Error in updateDocument:", error);
            console.error("Error response:", error.response?.data);
            const errorPayload = error.response?.data || {};
            return {
                success: false,
                error: errorPayload.error || 'Failed to update document',
                message: errorPayload.message || errorPayload.error || 'Failed to update document',
                status: error.response?.status,
                validation: errorPayload.validation,
                existingDocumentId: errorPayload.existingDocumentId,
                details: errorPayload
            };
        }
    },

    async getPresignedUrl(documentId) {
        if (!documentId) throw new Error('Missing documentId');
        // Handle email attachment IDs gracefully
        if (documentId.startsWith('email_')) {
            throw new Error('Email attachments are not available for direct download. Please process the attachment first.');
        }
        const response = await axios.get(`${DOCUMENTS_API_URL}/${documentId}/presign`);
        return response.data?.url;
    },

    // Get audit trail for a document
    getAuditTrail: async (documentId) => {
        if (!documentId) {
            throw new Error('Missing document identifier');
        }
        // Handle email attachment IDs gracefully
        if (documentId.startsWith('email_')) {
            console.log(`Email attachment ${documentId} does not have audit trail in document collection`);
            return [];
        }
        try {
            const response = await axios.get(`${DOCUMENTS_API_URL}/${documentId}/audit-logs`);
            // Always return an array, even if empty
            const auditTrail = response.data?.data || [];
            console.log(`Fetched audit trail for document ${documentId}:`, auditTrail.length, 'entries');
            return auditTrail;
        } catch (error) {
            console.error("Error in isfDocumentService.getAuditTrail:", error);
            // If 404, document doesn't exist - return empty array
            if (error.response?.status === 404) {
                console.warn(`Document ${documentId} not found, returning empty audit trail`);
                return [];
            }
            // For other errors, throw to let React Query handle retry
            throw error;
        }
    }
};

export default isfDocumentService;