import api from './api';

const unwrapWorkflow = (response) => {
  const payload = response?.data?.data ?? response?.data ?? {};
  if (payload.workflow || payload.auditTrail) {
    return payload;
  }
  return { workflow: payload };
};

class DocumentWorkflowService {
  async getState(documentId) {
    const response = await api.get(`/documents/${documentId}/workflow`);
    // New API returns { success: true, data: workflow }
    if (response?.data?.success && response?.data?.data) {
      return { workflow: response.data.data };
    }
    // Fallback to old format
    return unwrapWorkflow(response);
  }

  async initialize(documentId) {
    const response = await api.post(`/documents/${documentId}/workflow/initialize`);
    return unwrapWorkflow(response);
  }

  async updateIntake(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/intake`, payload);
    return unwrapWorkflow(response);
  }

  async updateQcValidation(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/qc-validation`, payload);
    return unwrapWorkflow(response);
  }

  async updateReviewPreparation(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/review-preparation`, payload);
    return unwrapWorkflow(response);
  }

  async advance(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/advance`, payload);
    return unwrapWorkflow(response);
  }

  async updateReviewStage(documentId, stageKey, updates) {
    const response = await api.patch(`/documents/${documentId}/workflow/review/${stageKey}`, updates);
    return unwrapWorkflow(response);
  }

  async escalateReviewStage(documentId, stageKey, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/review/${stageKey}/escalate`, payload);
    return unwrapWorkflow(response);
  }

  async reassignReviewStage(documentId, stageKey, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/review/${stageKey}/reassign`, payload);
    return unwrapWorkflow(response);
  }

  async updateApprovalStage(documentId, stageKey, updates) {
    const response = await api.patch(`/documents/${documentId}/workflow/approval/${stageKey}`, updates);
    return unwrapWorkflow(response);
  }

  async escalateApprovalStage(documentId, stageKey, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/approval/${stageKey}/escalate`, payload);
    return unwrapWorkflow(response);
  }

  async reassignApprovalStage(documentId, stageKey, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/approval/${stageKey}/reassign`, payload);
    return unwrapWorkflow(response);
  }

  async updateReviewAndApproval(documentId, payload) {
    const response = await api.patch(`/documents/${documentId}/workflow/review-approval`, payload);
    return unwrapWorkflow(response);
  }

  async updateActivation(documentId, updates) {
    const response = await api.patch(`/documents/${documentId}/workflow/activation`, updates);
    return unwrapWorkflow(response);
  }

  async updateMonitoring(documentId, updates) {
    const response = await api.patch(`/documents/${documentId}/workflow/monitoring`, updates);
    return unwrapWorkflow(response);
  }

  async startRevision(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/revision`, payload);
    return unwrapWorkflow(response);
  }

  async updateRevision(documentId, updates) {
    const response = await api.patch(`/documents/${documentId}/workflow/revision`, updates);
    return unwrapWorkflow(response);
  }

  async archive(documentId, payload) {
    const response = await api.post(`/documents/${documentId}/workflow/archive`, payload);
    return unwrapWorkflow(response);
  }

  async recalculateMetrics(documentId) {
    const response = await api.post(`/documents/${documentId}/workflow/recalculate`);
    const payload = response?.data?.data ?? response?.data ?? {};
    return payload.metrics ?? payload;
  }

  // ==================== REJECTION HANDLING ====================

  /**
   * Reject a document at a specific stage
   * @param {string} documentId - Document ID
   * @param {Object} rejectionData - { stage, reason, category, returnToStage, actionRequired, dueDate }
   */
  async rejectDocument(documentId, rejectionData) {
    const response = await api.post(`/documents/${documentId}/workflow/reject`, rejectionData);
    return {
      success: response?.data?.success,
      message: response?.data?.message,
      workflow: response?.data?.data?.workflow,
      rejectionHistory: response?.data?.data?.rejectionHistory,
    };
  }

  /**
   * Resolve a rejection at a specific stage
   * @param {string} documentId - Document ID
   * @param {Object} resolutionData - { stage, notes }
   */
  async resolveRejection(documentId, resolutionData) {
    const response = await api.post(`/documents/${documentId}/workflow/resolve-rejection`, resolutionData);
    return {
      success: response?.data?.success,
      message: response?.data?.message,
      workflow: response?.data?.data?.workflow,
      rejectionHistory: response?.data?.data?.rejectionHistory,
    };
  }

  /**
   * Get rejection history for a document
   * @param {string} documentId - Document ID
   */
  async getRejectionHistory(documentId) {
    const response = await api.get(`/documents/${documentId}/workflow/rejection-history`);
    return {
      success: response?.data?.success,
      currentRejections: response?.data?.data?.currentRejections,
      history: response?.data?.data?.history,
      categories: response?.data?.data?.categories,
    };
  }

  /**
   * Replace document and reset workflow to QC Validation
   * @param {string} documentId - Document ID
   * @param {File} file - File to upload
   */
  async replaceDocument(documentId, file, options = { commit: true }) {
    const formData = new FormData();
    formData.append('file', file);
    // Append commit flag so backend can run in preview mode when needed
    formData.append('commit', options.commit ? 'true' : 'false');

    // If provided, include classification metadata (from preview) so backend can apply it on commit
    if (options.metadata) {
      try {
        formData.append('classificationPayload', JSON.stringify(options.metadata));
      } catch (e) {
        // ignore serialization errors
      }
    }

    console.log("fosdfghfdsa", formData);

    const response = await api.post(`/documents/${documentId}/workflow/replace-document`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return unwrapWorkflow(response);
  }

  /**
   * Reset workflow to DRAFT status and send document back to workflow
   * @param {string} documentId - Document ID
   * @param {string} reason - Optional reason for reset
   */
  async resetToDraft(documentId, reason) {
    const response = await api.post(`/documents/${documentId}/workflow/reset-to-draft`, { reason });
    return unwrapWorkflow(response);
  }
}

export default new DocumentWorkflowService();
