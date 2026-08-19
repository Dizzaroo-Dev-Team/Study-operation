import api from './api';

class EmailAttachmentService {
  /**
   * Process email attachments for a study
   * @param {string} studyId - Study identifier
   * @returns {Promise<Object>} Processing result
   */
  async processEmailAttachments(studyId) {
    try {
      const response = await api.post(`/mock-email/process/${studyId}`);
      return response.data;
    } catch (error) {
      console.error('Process email attachments error:', error);
      throw new Error(error.response?.data?.error || 'Failed to process email attachments');
    }
  }

  /**
   * Get email attachments for a study
   * @param {string} studyId - Study identifier
   * @param {Object} options - Query options
   * @returns {Promise<Object>} Email attachments
   */
  async getEmailAttachments(studyId, options = {}) {
    try {
      const { status, limit = 50, offset = 0 } = options;
      const params = new URLSearchParams();
      
      if (status) params.append('status', status);
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());

      // Use the new integration endpoint for combined data
      const response = await api.get(`/gmail-email-integration/attachments/${studyId}?${params.toString()}`);
      return response.data;
    } catch (error) {
      console.error('Get email attachments error:', error);
      throw new Error(error.response?.data?.error || 'Failed to get email attachments');
    }
  }

  /**
   * Classify email attachment using AI
   * @param {string} attachmentId - Attachment ID
   * @returns {Promise<Object>} Classification result
   */
  async classifyEmailAttachment(attachmentId) {
    try {
      const response = await api.post(`/mock-email/classify/${attachmentId}`);
      return response.data;
    } catch (error) {
      console.error('Classify email attachment error:', error);
      throw new Error(error.response?.data?.error || 'Failed to classify email attachment');
    }
  }

  /**
   * Classify Gmail attachment using AI (for PDFs)
   * @param {string} attachmentId - Attachment ID
   * @param {string} studyId - Study identifier
   * @returns {Promise<Object>} AI classification result
   */
  async classifyGmailAttachmentWithAI(attachmentId, studyId) {
    try {
      const response = await api.post(`/gmail-email-integration/process/${studyId}/${attachmentId}`);
      return response.data;
    } catch (error) {
      console.error('Classify Gmail attachment with AI error:', error);
      throw new Error(error.response?.data?.error || 'Failed to classify Gmail attachment with AI');
    }
  }

  /**
   * Bulk classify Gmail attachments with AI
   * @param {string} studyId - Study identifier
   * @param {Array<string>} attachmentIds - Array of attachment IDs
   * @param {boolean} forceAI - Force AI classification for all files
   * @returns {Promise<Object>} Bulk classification results
   */
  async bulkClassifyGmailAttachments(studyId, attachmentIds, forceAI = false) {
    try {
      const response = await api.post(`/gmail-email-integration/bulk-classify/${studyId}`, {
        attachmentIds,
        forceAI
      });
      return response.data;
    } catch (error) {
      console.error('Bulk classify Gmail attachments error:', error);
      throw new Error(error.response?.data?.error || 'Failed to bulk classify Gmail attachments');
    }
  }

  /**
   * Approve email attachment and convert to document
   * @param {string} attachmentId - Attachment ID
   * @param {Object} approvalData - Approval data
   * @returns {Promise<Object>} Created document
   */
  async approveEmailAttachment(attachmentId, approvalData) {
    try {
      const response = await api.post(`/mock-email/approve/${attachmentId}`, approvalData);
      return response.data;
    } catch (error) {
      console.error('Approve email attachment error:', error);
      throw new Error(error.response?.data?.error || 'Failed to approve email attachment');
    }
  }

  /**
   * Reject email attachment
   * @param {string} attachmentId - Attachment ID
   * @param {Object} rejectionData - Rejection data
   * @returns {Promise<Object>} Rejection result
   */
  async rejectEmailAttachment(attachmentId, rejectionData = {}) {
    try {
      const response = await api.post(`/mock-email/reject/${attachmentId}`, rejectionData);
      return response.data;
    } catch (error) {
      console.error('Reject email attachment error:', error);
      throw new Error(error.response?.data?.error || 'Failed to reject email attachment');
    }
  }

  /**
   * Bulk classify email attachments
   * @param {string} studyId - Study identifier
   * @param {Array<string>} attachmentIds - Array of attachment IDs
   * @returns {Promise<Object>} Bulk classification results
   */
  async bulkClassifyEmailAttachments(studyId, attachmentIds) {
    try {
      const response = await api.post(`/mock-email/bulk-classify/${studyId}`, {
        attachmentIds
      });
      return response.data;
    } catch (error) {
      console.error('Bulk classify email attachments error:', error);
      throw new Error(error.response?.data?.error || 'Failed to bulk classify email attachments');
    }
  }

  /**
   * Get email attachment statistics
   * @param {string} studyId - Study identifier
   * @returns {Promise<Object>} Statistics
   */
  async getEmailAttachmentStats(studyId) {
    try {
      const response = await api.get(`/mock-email/stats/${studyId}`);
      return response.data;
    } catch (error) {
      console.error('Get email attachment stats error:', error);
      throw new Error(error.response?.data?.error || 'Failed to get email attachment statistics');
    }
  }

  /**
   * Get combined email attachment statistics (real Gmail + mock)
   * @param {string} studyId - Study identifier
   * @returns {Promise<Object>} Combined statistics
   */
  async getCombinedEmailAttachmentStats(studyId) {
    try {
      const response = await api.get(`/gmail-email-integration/stats/${studyId}`);
      return response.data;
    } catch (error) {
      console.error('Get combined email attachment stats error:', error);
      throw new Error(error.response?.data?.error || 'Failed to get combined email attachment statistics');
    }
  }

  /**
   * Sync Gmail emails to Email Attachment system
   * @param {string} studyId - Study identifier
   * @param {Object} options - Sync options
   * @returns {Promise<Object>} Sync result
   */
  async syncGmailToEmailAttachments(studyId, options = {}) {
    try {
      const response = await api.post(`/gmail-email-integration/sync/${studyId}`, options);
      return response.data;
    } catch (error) {
      console.error('Sync Gmail to Email Attachments error:', error);
      throw new Error(error.response?.data?.error || 'Failed to sync Gmail to Email Attachments');
    }
  }

  /**
   * Validate a Gmail email attachment using the backend validation pipeline
   * @param {string} messageId - Gmail message ID
   * @param {string} attachmentId - Gmail attachment ID
   * @returns {Promise<Object>} Validation result
   */
  async validateGmailAttachment(messageId, attachmentId, studyId = null) {
    try {
      const response = await api.post(`/gmail-email-integration/validate`, {
        messageId,
        attachmentId,
        studyId // Include studyId to save validation status
      });
      return response.data;
    } catch (error) {
      console.error('Validate Gmail attachment error:', error);
      throw new Error(error.response?.data?.error || 'Failed to validate Gmail attachment');
    }
  }

  /**
   * Process and classify a real Gmail attachment
   * @param {string} attachmentId - Attachment ID
   * @param {string} studyId - Study identifier
   * @returns {Promise<Object>} Processing result
   */
  async processRealGmailAttachment(attachmentId, studyId) {
    try {
      const response = await api.post(`/gmail-email-integration/process/${studyId}/${attachmentId}`);
      return response.data;
    } catch (error) {
      console.error('Process real Gmail attachment error:', error);
      throw new Error(error.response?.data?.error || 'Failed to process real Gmail attachment');
    }
  }

  /**
   * Download email attachment file
   * @param {string} fileUrl - File URL
   * @returns {Promise<Blob>} File blob
   */
  async downloadAttachment(fileUrl) {
    try {
      // If it's a relative URL, prepend the API base URL
      let fullUrl = fileUrl;
      if (fileUrl && fileUrl.startsWith('/')) {
        fullUrl = `${process.env.REACT_APP_API_URL || ''}${fileUrl}`;
      }
      
      const response = await api.get(fullUrl, {
        responseType: 'blob'
      });
      return response.data;
    } catch (error) {
      console.error('Download attachment error:', error);
      throw new Error('Failed to download attachment');
    }
  }

  /**
   * Preview email attachment
   * @param {string} fileUrl - File URL
   * @returns {Promise<string>} Preview URL
   */
  async previewAttachment(fileUrl) {
    try {
      // If it's a relative URL, prepend the API base URL
      if (fileUrl && fileUrl.startsWith('/')) {
        return `${process.env.REACT_APP_API_URL || ''}${fileUrl}`;
      }
      return fileUrl;
    } catch (error) {
      console.error('Preview attachment error:', error);
      throw new Error('Failed to preview attachment');
    }
  }
}

export default new EmailAttachmentService();
