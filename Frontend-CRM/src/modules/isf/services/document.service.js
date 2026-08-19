import { config } from '../config/config';
import axios from 'axios';
import authService from './auth.service';

// config.API_URL (= VITE_API_BASE) already ends with /api — do NOT add /api again
const API_URL = `${config.API_URL}/tmf/documents`;
const DOCUMENTS_API_URL = `${config.API_URL}/isf-documents`;

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

        throw new Error('No users found in backend. Please ensure at least one user exists in the system.');
    } catch (error) {
        console.error('Error resolving backend user id for TMF upload:', error);
        console.error('Response data:', error.response?.data);

        // Re-throw with more context
        throw new Error(`Failed to resolve backend user: ${error.message}. Please ensure the backend is accessible and has users.`);
    }
};

const documentService = {
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
            console.error("Error in documentService.create:", error);
            console.error("Error response:", error.response?.data);
            throw error;
        }
    },

    getAllDocuments: async (options = {}) => {
        try {
            // Build query parameters
            const params = new URLSearchParams();
            if (options.tmfViewer) {
                params.append('tmfViewer', 'true');
            }
            if (options.study) {
                params.append('study', options.study);
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
            console.log(`[documentService.getAllDocuments] Calling API: ${url}`);
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

            // Log sample document to verify population
            if (documents.length > 0 && options.tmfViewer) {
                const sampleDoc = documents[0];
                console.log(`[documentService.getAllDocuments] Fetched ${documents.length} documents. Sample document TMF metadata:`, {
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

            return documents;
        } catch (error) {
            console.error("Error in documentService.getAllDocuments:", error);
            throw error;
        }
    },

    updateTMFMetadata: async (documentId, metadata) => {
        try {
            const response = await axios.patch(`${DOCUMENTS_API_URL}/${documentId}/tmf-metadata`, metadata);
            return response.data;
        } catch (error) {
            console.error("Error in documentService.updateTMFMetadata:", error);
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
            const data = response.data?.data || response.data;
            // Debug logging
            if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
                console.log(`[documentService.getDocument] Fetched from ${url}:`, {
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
                console.log('[documentService.getDocument] TMF endpoint response:', {
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
                console.log('[documentService.getDocument] Documents endpoint response:', {
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
            console.error("Error in documentService.getDocument:", error);
            throw lastError || error;
        }
    },

    // Get all comments for a document (TMF route)
    getComments: async (documentId) => {
        try {
            const response = await axios.get(`${API_URL}/${documentId}/comments`);
            return response.data;
        } catch (error) {
            console.error("Error in documentService.getComments:", error);
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
            console.error("Error in documentService.addComment:", error);
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
            console.error("Error in documentService.addReply:", error);
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
            formData.append('metadata', JSON.stringify(metadata));

            console.log('Uploading to URL:', `${API_URL}/${userId}`);
            console.log('Metadata:', metadata);

            // Use the TMF documents API for file uploads (supports multipart)
            const response = await axios.post(`${API_URL}/${userId}`, formData, {
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
        const response = await axios.get(`${config.API_URL}/tmf/documents/${documentId}/presign`);
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
            console.error("Error in documentService.getAuditTrail:", error);
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

export default documentService;
