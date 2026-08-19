import axios from 'axios';

// VITE_API_BASE already ends with /api — do NOT add /api again
const _rawBase = import.meta.env.VITE_API_BASE || '';
const _isLocalBase = _rawBase.includes('localhost') || _rawBase.includes('127.0.0.1');
const _safeBase = (!_isLocalBase && _rawBase.startsWith('http://')) ? _rawBase.replace('http://', 'https://') : _rawBase;
const API_URL = `${_safeBase}/isf-documents`;

function getToken() {
  return localStorage.getItem('auth_token');
}

const isfClinicalTrialsService = {
  // Basic Document Operations
  async getDocuments(params = {}) {
    try {
      const { page, limit, sort, filters } = params;


      const searchParams = new URLSearchParams();

      if (page) {
        searchParams.append('page', page);
      }

      if (limit) {
        searchParams.append('limit', limit);
      }

      if (sort?.key) {
        const direction = sort.direction || 'asc';
        searchParams.append('sort', `${sort.key}:${direction}`);
      }

      if (filters) {
        if (filters.study && filters.study !== 'all') {
          searchParams.append('study', filters.study);
        }
        if (filters.site && filters.site !== 'all') {
          searchParams.append('site', filters.site);
        }
      }
      
      const url = searchParams.toString()
        ? `${API_URL}?${searchParams.toString()}`
        : API_URL;


      console.log("API Callinf", url);
      const response = await axios.get(url);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async getDocument(documentId) {
    try {
      const response = await axios.get(`${API_URL}/${documentId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async uploadDocument(file, metadata) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('metadata', JSON.stringify(metadata));

      console.log("JHellnodnof");  
      
      const response = await axios.post(`${API_URL}/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  // Document Review Workflow
  async addReviewer(documentId, reviewer) {
    try {
      const response = await axios.post(`${API_URL}/isf-documents/${documentId}/reviewers`, reviewer);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async updateReview(documentId, reviewerId, reviewData) {
    try {
      const response = await axios.put(
        `${API_URL}/isf-documents/${documentId}/reviewers/${reviewerId}`,
        reviewData
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async getReviewers(documentId) {
    try {
      const response = await axios.get(`${API_URL}/isf-documents/${documentId}/reviewers`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async updateDocumentStatus(documentId, status, metadata = {}) {
    try {
      const response = await axios.put(`${API_URL}/isf-documents/${documentId}/status`, {
        status,
        metadata
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async sendForReview(documentId) {
    try {
      const response = await axios.post(`${API_URL}/isf-documents/${documentId}/send-for-review`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  async updateDocument(documentId, data) {
    return axios.put(`${API_URL}/isf-documents/${documentId}`, data)
      .then(res => res.data)
      .catch(err => { throw err.response?.data || err; });
  },

  submitDocumentApproval: async (documentId, approvalData) => {
    try {
      const response = await fetch(`${API_URL}/isf-documents/${documentId}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(approvalData)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to submit approval');
      }

      return await response.json();
    } catch (error) {
      throw this.handleError(error);
    }
  },

  getDocumentApprovals: async (documentId) => {
    try {
      const response = await fetch(`${API_URL}/isf-documents/${documentId}/approvals`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to fetch approvals');
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching approvals:', error);
      throw error;
    }
  },

  // Document approval
  async approveDocument(documentId, comments) {
    const response = await axios.post(`${API_URL}/isf-documents/${documentId}/approve`, { comments });
    return response.data;
  },

  // Document rejection
  async rejectDocument(documentId, comments) {
    const response = await axios.post(`${API_URL}/isf-documents/${documentId}/reject`, { comments });
    return response.data;
  },

  // Document deletion
  async deleteDocument(documentId) {
    try {
      const response = await axios.delete(`${API_URL}/${documentId}`);
      // Backend returns 204 (No Content) on success, so response.data may be empty
      return { success: true, data: response.data || null };
    } catch (error) {
      console.error('Delete document error:', error);
      throw this.handleError(error);
    }
  },


  // Document archiving
  async archiveDocument(documentId, reason) {
    const response = await axios.post(`${API_URL}/isf-documents/${documentId}/archive`, { reason });
    return response.data;
  },

  // Bulk archive documents
  async bulkArchiveDocuments(documentIds, reason) {
    const response = await axios.post(`${API_URL}/isf-documents/bulk-archive`, { documentIds, reason });
    return response.data;
  },

  // Document audit trail
  async getDocumentAuditTrail(documentId) {
    try {
      const response = await axios.get(`${API_URL}/isf-documents/${documentId}/audit-trail`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  },

  // Update reviewer (alias for updateReview)
  async updateReviewer(documentId, reviewerId, reviewData) {
    return this.updateReview(documentId, reviewerId, reviewData);
  },

  /**
   * Fetch emails with document attachments for a given study.
   * The CRM doesn't have a dedicated email endpoint, so this returns
   * the existing ISF documents as email-attachment objects so the
   * ISFDocumentList email-attachment tab stays functional.
   *
   * @param {string|null} studyId  - study filter (null = all studies)
   * @param {number}      limit    - max records to return
   */
  async getStudyEmails(studyId, limit = 50) {
    try {
      const params = new URLSearchParams();
      if (studyId) params.append('study', studyId);
      if (limit)   params.append('limit', String(limit));
      const url = params.toString() ? `${API_URL}?${params.toString()}` : API_URL;
      const token = getToken();
      const response = await axios.get(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      // Normalise into the shape ISFDocumentList expects for email attachments
      const docs = response.data?.data ?? (Array.isArray(response.data) ? response.data : []);
      return {
        success: true,
        data: docs.map(d => ({
          ...d,
          _id: d._id ?? d.id ?? d.document_id,
          title: d.title ?? d.documentTitle,
          studyId: d.study ?? studyId,
        })),
      };
    } catch (error) {
      console.error('getStudyEmails error:', error);
      return { success: false, data: [] };
    }
  },

  /**
   * Generate a time-limited SAS URL for an Azure Blob.
   *
   * Usage (matching Shashank's pattern):
   *   const blobName = doc.fileUrl.split('/').pop();
   *   const { sasUrl } = await isfClinicalTrialsService.getSasToken(blobName);
   *   window.open(sasUrl, '_blank');
   *
   * @param {string} blobName  - The blob file name (last segment of the stored file URL)
   * @returns {Promise<{ sasUrl: string }>}
   */
  async getSasToken(blobName) {
    if (!blobName) throw new Error('blobName is required');
    // Strip any existing query string (e.g. if a full URL was passed by mistake)
    const cleanBlobName = blobName.split('?')[0].split('/').pop();
    try {
      const response = await axios.get(`${_safeBase}/isf-documents/sas-url`, {
        params: { blobName: cleanBlobName },
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      return response.data; // { sasUrl: "https://...?sv=...&sig=..." }
    } catch (error) {
      throw this.handleError(error);
    }
  },

  handleError(error) {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      return new Error(error.response.data.message || 'An error occurred');
    } else if (error.request) {
      // The request was made but no response was received
      return new Error('No response from server');
    } else {
      // Something happened in setting up the request that triggered an Error
      return new Error(error.message || 'An error occurred');
    }
  }
};

export default isfClinicalTrialsService;