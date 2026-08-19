import React, { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'

interface WorkflowStep {
  step_name: string
  status: 'not_started' | 'in_progress' | 'completed' | 'locked'
  step_data: Record<string, any>
  completed_at: string | null
  completed_by: string | null
  created_at: string
  updated_at: string
}

interface WorkflowStepsResponse {
  site_id: string
  steps: WorkflowStep[]
}

interface UnderConsiderationWorkflowProps {
  siteId: string
  apiBase?: string
  onUpdate?: () => void
}

const UnderConsiderationWorkflow: React.FC<UnderConsiderationWorkflowProps> = ({
  siteId,
  apiBase = '/api',
  onUpdate,
}) => {
  const { user } = useAuth()
  const { selectedStudyId } = useStudySite()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [steps, setSteps] = useState<WorkflowStep[]>([])
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [localState, setLocalState] = useState<Record<string, any>>({})
  const [questionnaireQuestions, setQuestionnaireQuestions] = useState<any[]>([])
  const [loadingQuestions, setLoadingQuestions] = useState(false)
  const [feasibilityResponses, setFeasibilityResponses] = useState<any[]>([])
  const [loadingResponses, setLoadingResponses] = useState(false)
  const [sendingRequest, setSendingRequest] = useState(false)
  const [feasibilityEmail, setFeasibilityEmail] = useState<string>('labeshg@dizzaroo.com')
  const [protocolSynopsis, setProtocolSynopsis] = useState<any>(null)
  const [uploadingProtocolSynopsis, setUploadingProtocolSynopsis] = useState(false)
  const [studySiteId, setStudySiteId] = useState<string | null>(null)
  const [resettingFeasibility, setResettingFeasibility] = useState(false)
  const [cdaAgreementStatus, setCdaAgreementStatus] = useState<{
    exists: boolean
    executed: boolean
    agreementId: string | null
  } | null>(null)
  const [checkingCdaAgreement, setCheckingCdaAgreement] = useState(false)

  // Check for CDA Agreement when CDA step is expanded or when cdaRequired changes.
  // `silent` skips the spinner state so background polling doesn't flash the button.
  const checkCdaAgreement = async (silent: boolean = false) => {
    if (!siteId || !selectedStudyId) return

    if (!silent) setCheckingCdaAgreement(true)
    try {
      // Get all agreements for this Study + Site
      const response = await api.get(
        `${apiBase}/sites/${siteId}/agreements`,
        {
          params: { study_id: selectedStudyId },
        }
      )
      const agreements = response.data || []
      
      console.log('Checking CDA Agreements:', { siteId, agreementCount: agreements.length })
      
      // Find CDA agreement by checking template type
      let cdaAgreement = null
      let executedAgreement = null // Fallback: track any executed agreement
      
      for (const agreement of agreements) {
        const statusUpper = String(agreement.status || '').toUpperCase()
        const isExecuted = statusUpper === 'EXECUTED'
        
        console.log('Checking agreement:', { 
          id: agreement.id, 
          title: agreement.title, 
          status: agreement.status, 
          statusUpper,
          isExecuted,
          hasDocuments: !!agreement.documents?.length 
        })
        
        // Track executed agreements as fallback
        if (isExecuted && !executedAgreement) {
          executedAgreement = agreement
        }
        
        if (agreement.documents && agreement.documents.length > 0) {
          const firstDoc = agreement.documents[0]
          if (firstDoc.created_from_template_id && selectedStudyId) {
            // Fetch template to check type
            try {
              const templateResponse = await api.get(`${apiBase}/studies/${selectedStudyId}/templates/${firstDoc.created_from_template_id}`)
              const template = templateResponse.data
              console.log('Template found:', { id: template.id, name: template.template_name, type: template.template_type })
              
              // Check if template type is CDA
              if (template.template_type === 'CDA' || template.template_type?.toUpperCase() === 'CDA') {
                cdaAgreement = agreement
                console.log('Found CDA Agreement:', { id: agreement.id, status: agreement.status })
                break
              }
            } catch (templateErr: any) {
              console.warn('Could not fetch template:', templateErr)
              // Fallback: check title if template fetch fails
              if (agreement.title.toLowerCase().includes('cda') || 
                  agreement.title.toLowerCase().includes('confidentiality')) {
                cdaAgreement = agreement
                console.log('Found CDA Agreement (by title fallback):', { id: agreement.id, status: agreement.status })
                break
              }
            }
          } else {
            // No template_id or no studyId, fallback to title check
            if (agreement.title.toLowerCase().includes('cda') || 
                agreement.title.toLowerCase().includes('confidentiality')) {
              cdaAgreement = agreement
              console.log('Found CDA Agreement (by title, no template_id):', { id: agreement.id, status: agreement.status })
              break
            }
          }
        }
      }
      
      // Fallback: If no CDA agreement found by template/title but there's an executed agreement,
      // and CDA is required, assume it's the CDA (since there should only be one CDA per site)
      if (!cdaAgreement && executedAgreement) {
        console.log('Using executed agreement as CDA fallback:', { id: executedAgreement.id, status: executedAgreement.status })
        cdaAgreement = executedAgreement
      }
      
      if (cdaAgreement) {
        // Check status (case-insensitive)
        const statusUpper = String(cdaAgreement.status || '').toUpperCase()
        const isExecuted = statusUpper === 'EXECUTED'
        
        console.log('CDA Agreement status check:', { 
          agreementId: cdaAgreement.id, 
          status: cdaAgreement.status, 
          statusUpper, 
          isExecuted 
        })
        
        setCdaAgreementStatus({
          exists: true,
          executed: isExecuted,
          agreementId: cdaAgreement.id
        })
      } else {
        console.log('No CDA Agreement found')
        setCdaAgreementStatus({
          exists: false,
          executed: false,
          agreementId: null
        })
      }
    } catch (err: any) {
      console.error('Error checking CDA Agreement:', err)
      setCdaAgreementStatus({
        exists: false,
        executed: false,
        agreementId: null
      })
    } finally {
      if (!silent) setCheckingCdaAgreement(false)
    }
  }

  useEffect(() => {
    if (siteId && selectedStudyId) {
      // Reset state when study changes to avoid stale data
      setSteps([])
      setExpandedStep(null)
      setLocalState({})
      loadSteps()
    }
  }, [siteId, selectedStudyId])

  useEffect(() => {
    if (selectedStudyId && expandedStep === 'feasibility') {
      loadQuestionnaire()
      loadFeasibilityResponses()
      loadProtocolSynopsis()
    }
  }, [selectedStudyId, expandedStep, siteId])

  const loadProtocolSynopsis = async () => {
    if (!siteId || !selectedStudyId) return
    
    try {
      // Get study_site_id
      const lookupResponse = await api.get(`${apiBase}/study-sites/lookup`, {
        params: { site_id: siteId, study_id: selectedStudyId }
      })
      const studySiteIdValue = lookupResponse.data.study_site_id
      setStudySiteId(studySiteIdValue)
      
      // Load attachment
      const response = await api.get(`${apiBase}/feasibility-attachments/${studySiteIdValue}`)
      setProtocolSynopsis(response.data)
    } catch (err: any) {
      if (err.response?.status !== 404) {
        console.error('Failed to load Protocol Synopsis:', err)
      }
      setProtocolSynopsis(null)
    }
  }

  const handleUploadProtocolSynopsis = async (file: File) => {
    if (!studySiteId) {
      setError('Study site ID not available')
      return
    }
    
    setUploadingProtocolSynopsis(true)
    setError(null)
    
    try {
      const formData = new FormData()
      formData.append('file', file)
      
      await api.post(`${apiBase}/feasibility-attachments/${studySiteId}`, formData)
      
      await loadProtocolSynopsis()
    } catch (err: any) {
      console.error('Upload error:', err)
      const errorDetail = err.response?.data?.detail || err.message || 'Failed to upload Protocol Synopsis'
      setError(errorDetail)
      console.error('Error detail:', errorDetail)
    } finally {
      setUploadingProtocolSynopsis(false)
    }
  }

  const handleDeleteProtocolSynopsis = async () => {
    if (!studySiteId) return
    
    if (!window.confirm('Are you sure you want to delete the Protocol Synopsis? This action cannot be undone if the feasibility form has already been sent.')) {
      return
    }
    
    try {
      await api.delete(`${apiBase}/feasibility-attachments/${studySiteId}`)
      setProtocolSynopsis(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete Protocol Synopsis')
    }
  }

  const handleDownloadProtocolSynopsis = () => {
    if (!studySiteId) return
    const downloadUrl = `${apiBase}/feasibility-attachments/${studySiteId}/download`
    window.open(downloadUrl, '_blank')
  }

  // Poll for responses only when step is expanded AND no responses exist yet
  useEffect(() => {
    // Only poll if step is expanded and we have no responses
    if (selectedStudyId && expandedStep === 'feasibility' && feasibilityResponses.length === 0) {
      // Set up polling to check for new responses every 5 seconds
      // Stop polling once responses are received (effect will re-run when feasibilityResponses.length changes)
      const pollInterval = setInterval(() => {
        loadFeasibilityResponses()
      }, 5000) // Poll every 5 seconds
      
      return () => clearInterval(pollInterval)
    }
    // If responses exist, no polling needed
  }, [selectedStudyId, expandedStep, siteId, feasibilityResponses.length])

  // Derive the CDA step's primitive status fields so the polling effect below
  // only re-subscribes when these actually change — not on every `steps` replacement
  // (the poll itself replaces `steps`, which would otherwise tear down/rebuild the
  // interval every cycle and cause the UI to constantly refresh).
  const cdaStepData = steps.find(s => s.step_name === 'cda_execution')?.step_data
  const cdaStatus = cdaStepData?.cda_status || null
  const cdaRequired =
    cdaStepData?.cda_required === true ||
    String(cdaStepData?.cda_required).toLowerCase() === 'true'

  // Poll for CDA status updates when CDA step is expanded and not yet signed externally
  useEffect(() => {
    if (selectedStudyId && expandedStep === 'cda_execution' && siteId) {
      // Check CDA Agreement status when step is expanded (silent — no spinner flash)
      if (cdaRequired) {
        checkCdaAgreement(true)
      }

      // Only poll if CDA is required and not yet fully signed.
      // Refreshes are silent so the background poll doesn't flash the
      // "Processing..." / "Checking..." button states every 5 seconds.
      if (cdaRequired && cdaStatus !== 'SIGNED' && cdaStatus !== 'CDA_COMPLETED') {
        const pollInterval = setInterval(() => {
          loadSteps(false, true) // silent reload of workflow steps
          checkCdaAgreement(true) // silent refresh of CDA Agreement status
        }, 5000) // Poll every 5 seconds

        return () => clearInterval(pollInterval)
      }
    }
  }, [selectedStudyId, expandedStep, siteId, cdaRequired, cdaStatus])

  const loadQuestionnaire = async () => {
    // Use the currently selected study from the StudySite context.
    // This is the external study_id string (e.g. "New study", "DG-04 Ver 2")
    if (!selectedStudyId) return
    setLoadingQuestions(true)
    try {
      const response = await api.get<{ project_id: string; questions: any[] }>(
        `${apiBase}/feasibility-questionnaire/${selectedStudyId}`
      )
      setQuestionnaireQuestions(response.data.questions || [])
    } catch (err: any) {
      console.error('Failed to load questionnaire:', err)
      setQuestionnaireQuestions([])
    } finally {
      setLoadingQuestions(false)
    }
  }

  const handleAddCustomQuestion = async () => {
    if (!selectedStudyId) {
      setError('Study ID not available')
      return
    }
    
    const questionText = prompt('Enter question text:')
    if (!questionText) return
    
    const section = prompt('Enter section (optional):') || null
    const responseType = prompt('Enter response type (text/number/yes_no, default: text):') || 'text'
    
    try {
      await api.post(`${apiBase}/feasibility-questionnaire/custom-questions`, {
        study_id: selectedStudyId, // Backend now accepts study_id string or UUID
        question_text: questionText,
        section: section,
        expected_response_type: responseType,
        display_order: questionnaireQuestions.length
      })
      await loadQuestionnaire()
    } catch (err: any) {
      // Extract error message properly - handle Pydantic validation errors
      let errorMessage = 'Failed to add custom question'
      if (err.response?.data) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail
        } else if (Array.isArray(err.response.data.detail)) {
          // Pydantic validation errors are arrays
          errorMessage = err.response.data.detail.map((e: any) => 
            typeof e === 'string' ? e : (e.msg || e.message || JSON.stringify(e))
          ).join(', ')
        } else if (err.response.data.detail && typeof err.response.data.detail === 'object') {
          errorMessage = err.response.data.detail.msg || err.response.data.detail.message || JSON.stringify(err.response.data.detail)
        }
      } else if (err.message) {
        errorMessage = err.message
      }
      setError(errorMessage)
    }
  }

  const handleDeleteCustomQuestion = async (questionId: string) => {
    if (!confirm('Delete this custom question?')) return
    try {
      await api.delete(`${apiBase}/feasibility-questionnaire/custom-questions/${questionId}`)
      await loadQuestionnaire()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete question')
    }
  }

  const loadFeasibilityResponses = async () => {
    if (!siteId || !selectedStudyId) return
    
    setLoadingResponses(true)
    try {
      // Get study_site_id
      const lookupResponse = await api.get(`${apiBase}/study-sites/lookup`, {
        params: { site_id: siteId, study_id: selectedStudyId }
      })
      const studySiteId = lookupResponse.data.study_site_id
      
      // Load responses
      const responsesResponse = await api.get(`${apiBase}/feasibility-responses/${studySiteId}`)
      setFeasibilityResponses(responsesResponse.data || [])
    } catch (err: any) {
      console.error('Failed to load feasibility responses:', err)
      setFeasibilityResponses([])
    } finally {
      setLoadingResponses(false)
    }
  }

  const handleSendFeasibilityRequest = async () => {
    if (!siteId || !selectedStudyId) {
      setError('Site ID or Study ID not available')
      return
    }
    
    if (!feasibilityEmail || !feasibilityEmail.trim()) {
      setError('Please enter a valid email address')
      return
    }
    
    setSendingRequest(true)
    setError(null)
    
    try {
      // Get study_site_id
      const lookupResponse = await api.get(`${apiBase}/study-sites/lookup`, {
        params: { site_id: siteId, study_id: selectedStudyId }
      })
      const studySiteIdValue = lookupResponse.data.study_site_id
      setStudySiteId(studySiteIdValue)
      
      // Send feasibility request
      await api.post(`${apiBase}/feasibility-requests`, {
        study_site_id: studySiteIdValue,
        email: feasibilityEmail.trim(),
        expires_in_days: 30
      })
      
      // Update step data
      const step = getStep('feasibility')
      const currentStepData = step?.step_data || {}
      await updateStep('feasibility', 'in_progress', {
        ...currentStepData,
        questionnaire_sent: true,
        questionnaire_sent_at: new Date().toISOString(),
        questionnaire_sent_by: user?.user_id || user?.email || 'unknown',
      })
      
      // Reload responses
      await loadFeasibilityResponses()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send feasibility request')
    } finally {
      setSendingRequest(false)
    }
  }


  const loadSteps = async (autoExpandNext: boolean = false, silent: boolean = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      // Include study_id for study-specific workflow steps
      const params = selectedStudyId ? { study_id: selectedStudyId } : {}
      const response = await api.get<WorkflowStepsResponse>(
        `${apiBase}/sites/${siteId}/workflow/steps`,
        { params }
      )
      setSteps(response.data.steps)
      
      // Auto-expand logic
      if (autoExpandNext) {
        // When a step is completed, find and expand the next unlocked step
        const firstUnlocked = response.data.steps.find(
          (s) => s.status !== 'completed' && s.status !== 'locked'
        )
        if (firstUnlocked) {
          setExpandedStep(firstUnlocked.step_name)
        }
      } else if (!expandedStep) {
        // Auto-expand first incomplete step if none expanded (initial load)
        const firstIncomplete = response.data.steps.find(
          (s) => s.status !== 'completed' && s.status !== 'locked'
        )
        if (firstIncomplete) {
          setExpandedStep(firstIncomplete.step_name)
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load workflow steps')
      console.error('Failed to load workflow steps:', err)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const updateStep = async (stepName: string, status?: string, stepData?: Record<string, any>) => {
    setLoading(true)
    setError(null)
    try {
      const updatePayload: any = {}
      if (status) updatePayload.status = status
      if (stepData !== undefined) {
        // Merge with existing step data to preserve all fields
        const existingStep = getStep(stepName)
        const existingData = existingStep?.step_data || {}
        updatePayload.step_data = { ...existingData, ...stepData }
      }

      // Include study_id for study-specific workflow steps
      const params = selectedStudyId ? { study_id: selectedStudyId } : {}
      await api.post(
        `${apiBase}/sites/${siteId}/workflow/steps/${stepName}`,
        updatePayload,
        { params }
      )
      // Always reload steps to get latest state from backend
      // Auto-expand next step if current step was completed
      const shouldExpandNext = status === 'completed'
      await loadSteps(shouldExpandNext)
      if (onUpdate) {
        onUpdate()
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to update step'
      setError(errorMsg)
      console.error('Failed to update step:', err)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const uploadDocument = async (
    file: File,
    category: string,
    description?: string,
    stepName?: string,
    stepDataUpdate?: Record<string, any>
  ) => {
    const wasLoading = loading
    setLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('category', category)
      if (description) formData.append('description', description)

      const docResponse = await api.post(`${apiBase}/sites/${siteId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      // Update step data if provided
      if (stepName && stepDataUpdate) {
        // Get current step data before updating
        const currentStep = getStep(stepName)
        const currentStepData = currentStep?.step_data || {}
        
        // Update step with merged data
        const updatePayload = {
          step_data: {
            ...currentStepData,
            ...stepDataUpdate,
            document_id: docResponse.data.id,
          }
        }
        
        // Include study_id for study-specific workflow steps
        const params = selectedStudyId ? { study_id: selectedStudyId } : {}
        await api.post(
          `${apiBase}/sites/${siteId}/workflow/steps/${stepName}`,
          updatePayload,
          { params }
        )
        
        // Reload steps to get updated state
        await loadSteps()
      } else {
        // Reload steps even if no step update needed
        await loadSteps()
      }

      if (onUpdate) {
        onUpdate()
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to upload document'
      setError(errorMsg)
      console.error('Failed to upload document:', err)
      throw err
    } finally {
      setLoading(wasLoading)
    }
  }

  const getStep = (stepName: string): WorkflowStep | undefined => {
    return steps.find((s) => s.step_name === stepName)
  }

  const isStepCompleted = (stepName: string): boolean => {
    const step = getStep(stepName)
    return step?.status === 'completed'
  }

  const isStepLocked = (stepName: string): boolean => {
    const step = getStep(stepName)
    if (step?.status === 'locked') {
      return true
    }
    
    // Check if Site Identification was rejected
    if (stepName !== 'site_identification') {
      const siteIdentStep = getStep('site_identification')
      if (siteIdentStep?.step_data?.decision === 'do_not_proceed') {
        return true
      }
    }
    
    // Note: Feasibility step does NOT lock the workflow based on toggles.
    // The "onsite_visit_required" toggle is informational only.
    // Only Site Identification "do_not_proceed" decision locks the workflow.
    
    return false
  }

  const getLockReason = (stepName: string): string => {
    if (stepName === 'cda_execution') {
      const prevStep = getStep('site_identification')
      if (prevStep?.step_data?.decision === 'do_not_proceed') {
        return 'Site Identification decision was "Do Not Proceed" - workflow is locked'
      }
      return 'Complete Site Identification first'
    } else if (stepName === 'feasibility') {
      return 'Complete CDA Execution first'
    } else if (stepName === 'site_selection_outcome') {
      const feasibilityStep = getStep('feasibility')
      if (!feasibilityStep || feasibilityStep.status !== 'completed') {
        return 'Complete Feasibility first'
      }
      // Feasibility step does NOT lock workflow - toggles are informational only
      return 'Complete Feasibility first'
    }
    return 'Previous step must be completed'
  }

  const handleResetWorkflow = async () => {
    if (!siteId) return
    const confirmed = window.confirm(
      'This will reset all workflow steps for this site and clear their progress. Do you want to continue?'
    )
    if (!confirmed) return

    setLoading(true)
    setError(null)
    try {
      // Include study_id to reset study-specific workflow steps
      const params = selectedStudyId ? { study_id: selectedStudyId } : {}
      await api.delete(`${apiBase}/sites/${siteId}/workflow/steps`, { params })
      await loadSteps(false)
      if (onUpdate) {
        onUpdate()
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to reset workflow steps'
      setError(errorMsg)
      console.error('Failed to reset workflow steps:', err)
    } finally {
      setLoading(false)
    }
  }

  // ===================================================================
  // STEP 1: SITE IDENTIFICATION - TRUE ACTION-BASED WORK AREA
  // ===================================================================
  const renderSiteIdentification = () => {
    const step = getStep('site_identification')
    const isCompleted = isStepCompleted('site_identification')
    const isLocked = isStepLocked('site_identification')
    const isExpanded = expandedStep === 'site_identification'
    const stepData = step?.step_data || {}
    const localData = localState.site_identification || {}
    
    // Use local state for form inputs, sync to backend on save
    const comments = localData.comments ?? stepData.comments ?? ''
    const decision = localData.decision ?? stepData.decision ?? ''

    // Completion now depends only on decision, not on a visibility report upload
    const canComplete = !!decision

    const handleSave = async () => {
      const newStepData = {
        ...stepData,
        comments: comments,
        decision: decision,
      }
      await updateStep('site_identification', 'in_progress', newStepData)
      setLocalState({ ...localState, site_identification: {} })
    }

    const handleComplete = async () => {
      if (!canComplete) {
        setError('Please select a decision before completing')
        return
      }
      
      const newStepData = {
        ...stepData,
        comments: comments,
        decision: decision,
      }
      
      if (decision === 'do_not_proceed') {
        // Lock all subsequent steps permanently
        await updateStep('site_identification', 'completed', {
          ...newStepData,
          workflow_locked: true,
        })
      } else {
        await updateStep('site_identification', 'completed', newStepData)
      }
      
      setLocalState({ ...localState, site_identification: {} })
    }

    const handleReopen = async () => {
      // Change status back to in_progress to allow editing
      const newStepData = {
        ...stepData,
        comments: comments,
        decision: decision,
      }
      await updateStep('site_identification', 'in_progress', newStepData)
      setLocalState({ ...localState, site_identification: {} })
    }

    return (
      <div className="border border-gray-300 rounded-lg mb-4 shadow-sm">
        <div
          className={`p-4 cursor-pointer flex items-center justify-between ${
            isLocked ? 'bg-gray-100 opacity-60' : isCompleted ? 'bg-green-50 hover:bg-green-100' : 'bg-blue-50 hover:bg-blue-100'
          }`}
          onClick={() => !isLocked && setExpandedStep(isExpanded ? null : 'site_identification')}
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                isCompleted
                  ? 'bg-green-600 text-white'
                  : isLocked
                  ? 'bg-gray-400 text-white'
                  : 'bg-blue-600 text-white'
              }`}
            >
              {isCompleted ? '✓' : isLocked ? '🔒' : '1'}
            </div>
            <div>
              <h4 className="font-semibold text-gray-900">Step 1: Site Identification</h4>
                <p className="text-xs text-gray-600">
                  {isCompleted
                    ? `Completed - Decision: ${decision === 'proceed' ? 'Proceed' : 'Do Not Proceed'}`
                    : isLocked
                    ? getLockReason('site_identification')
                    : 'Review site and make a decision'}
                </p>
            </div>
          </div>
          {!isLocked && (
            <svg
              className={`w-5 h-5 text-gray-500 transform transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        {isExpanded && !isLocked && (
          <div className="p-6 bg-white border-t border-gray-200">
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Comments</label>
                <textarea
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  rows={4}
                  value={comments}
                  onChange={(e) => setLocalState({
                    ...localState,
                    site_identification: { ...localData, comments: e.target.value }
                  })}
                  placeholder="Add any comments or notes about this site identification..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Decision <span className="text-red-500">*</span>
                </label>
                <div className="space-y-3">
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="decision"
                      value="proceed"
                      checked={decision === 'proceed'}
                      onChange={(e) => setLocalState({
                        ...localState,
                        site_identification: { ...localData, decision: e.target.value }
                      })}
                      className="mr-3"
                    />
                    <div>
                      <span className="font-medium text-green-700">Proceed</span>
                      <p className="text-xs text-gray-500">Continue with CDA Execution and Feasibility</p>
                    </div>
                  </label>
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="decision"
                      value="do_not_proceed"
                      checked={decision === 'do_not_proceed'}
                      onChange={(e) => setLocalState({
                        ...localState,
                        site_identification: { ...localData, decision: e.target.value }
                      })}
                      className="mr-3"
                    />
                    <div>
                      <span className="font-medium text-red-700">Do Not Proceed</span>
                      <p className="text-xs text-gray-500">Workflow will be permanently locked</p>
                    </div>
                  </label>
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t border-gray-200">
                {!isCompleted && (
                  <>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                      disabled={loading}
                    >
                      Save Progress
                    </button>
                    <button
                      onClick={handleComplete}
                      disabled={!canComplete || loading}
                      className={`px-6 py-2 rounded-lg font-medium ${
                        canComplete
                          ? 'bg-green-600 text-white hover:bg-green-700'
                          : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {loading ? 'Processing...' : 'Complete Step'}
                    </button>
                  </>
                )}
                {isCompleted && (
                  <>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                      disabled={loading}
                    >
                      Save Changes
                    </button>
                    <button
                      onClick={handleReopen}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      disabled={loading}
                    >
                      Re-open for Editing
                    </button>
                    <button
                      onClick={handleComplete}
                      disabled={!canComplete || loading}
                      className={`px-6 py-2 rounded-lg font-medium ${
                        canComplete
                          ? 'bg-green-600 text-white hover:bg-green-700'
                          : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {loading ? 'Processing...' : 'Save & Keep Completed'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {isCompleted && !isExpanded && (
          <div className="p-4 bg-green-50 border-t border-gray-200 text-sm text-gray-700">
            <p><strong>Decision:</strong> {stepData.decision === 'proceed' ? 'Proceed' : 'Do Not Proceed'}</p>
            {stepData.comments && <p className="mt-2"><strong>Comments:</strong> {stepData.comments}</p>}
            {step?.completed_at && (
              <p className="mt-2 text-xs text-gray-500">
                Completed on {new Date(step.completed_at).toLocaleDateString()}
              </p>
            )}
            <p className="mt-2 text-xs text-blue-600 italic">Click to edit this step</p>
          </div>
        )}
      </div>
    )
  }

  // STEP 2: CDA EXECUTION (SIMPLIFIED - Agreement module handles execution)
  const renderCDAExecution = () => {
    const step = getStep('cda_execution')
    const isCompleted = isStepCompleted('cda_execution')
    const isLocked = isStepLocked('cda_execution')
    const isExpanded = expandedStep === 'cda_execution'
    const stepData = step?.step_data || {}
    const localData = localState.cda_execution || {}
    
    const cdaRequired = localData.cda_required ?? stepData.cda_required ?? null
    const cdaComment = localData.cda_comment ?? stepData.cda_comment ?? ''
    
    // Check CDA Agreement status when expanded and CDA is required
    // Note: This check happens at component level via useEffect, not here
    
    // Determine if step can be completed based on new simplified logic
    let canComplete = false
    let completionMessage = ''
    
    if (cdaRequired === false) {
      // If No: Require comment, allow manual completion
      canComplete = !!cdaComment && cdaComment.trim().length > 0
      if (!canComplete) {
        completionMessage = 'Please provide a reason why CDA is not required'
      }
    } else if (cdaRequired === 'not_applicable') {
      // If Not Applicable: Allow manual completion immediately (no comment required)
      canComplete = true
    } else if (cdaRequired === true || String(cdaRequired).toLowerCase() === 'true') {
      // If Yes: Check if CDA Agreement exists and is EXECUTED
      // Backend will handle this check and prevent manual completion if not executed
      // Frontend just shows appropriate message
      if (cdaAgreementStatus?.executed) {
        canComplete = true
      } else if (cdaAgreementStatus?.exists && !cdaAgreementStatus?.executed) {
        canComplete = false
        completionMessage = 'CDA must be executed via Agreement module before completing this step'
      } else {
        // Agreement not found yet or still checking
        canComplete = false
        if (checkingCdaAgreement) {
          completionMessage = 'Checking CDA Agreement status...'
        } else {
          completionMessage = 'CDA must be executed via Agreement module. Please create and execute a CDA Agreement first.'
        }
      }
    }

    const handleCdaRequiredChange = async (value: any) => {
      const newLocalData = { ...localData, cda_required: value }
      // Clear comment if switching to Yes
      if (value === true) {
        newLocalData.cda_comment = ''
      }
      
      setLocalState({
        ...localState,
        cda_execution: newLocalData
      })
      
      // Save to backend immediately
      const newStepData: any = {
        ...stepData,
        cda_required: value,
        cda_status: value === false ? 'NOT_REQUIRED' : value === 'not_applicable' ? 'NOT_APPLICABLE' : null,
      }
      // Clear comment in step data if switching to Yes
      if (value === true) {
        newStepData.cda_comment = ''
      }
      
      await updateStep('cda_execution', 'in_progress', newStepData)
    }

    const handleComplete = async () => {
      if (!canComplete) {
        setError(completionMessage || 'Please complete all required actions before completing this step')
        return
      }

      // Complete CDA step - locks the step after completion
      const newStepData = { ...stepData }
      
      // Update status based on selection
      if (cdaRequired === false) {
        newStepData.cda_status = 'NOT_REQUIRED'
      } else if (cdaRequired === 'not_applicable') {
        newStepData.cda_status = 'NOT_APPLICABLE'
      } else if (cdaRequired === true) {
        // If Yes and CDA Agreement is executed, mark as completed
        if (cdaAgreementStatus?.executed) {
          newStepData.cda_status = 'CDA_COMPLETED'
          newStepData.completed_via_agreement = true
          newStepData.agreement_id = cdaAgreementStatus.agreementId
        }
      }

      await updateStep('cda_execution', 'completed', newStepData)
      setLocalState({ ...localState, cda_execution: {} })
    }

    const handleReopen = async () => {
      // Change status back to in_progress to allow editing
      const newStepData = { ...stepData }
      await updateStep('cda_execution', 'in_progress', newStepData)
      setLocalState({ ...localState, cda_execution: {} })
    }

    // Removed handleSave - no longer needed with simplified UI

    return (
      <div className="border border-gray-300 rounded-lg mb-4 shadow-sm">
        <div
          className={`p-4 cursor-pointer flex items-center justify-between ${
            isLocked ? 'bg-gray-100 opacity-60' : isCompleted ? 'bg-green-50 hover:bg-green-100' : 'bg-blue-50 hover:bg-blue-100'
          }`}
          onClick={() => !isLocked && setExpandedStep(isExpanded ? null : 'cda_execution')}
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                isCompleted
                  ? 'bg-green-600 text-white'
                  : isLocked
                  ? 'bg-gray-400 text-white'
                  : 'bg-blue-600 text-white'
              }`}
            >
              {isCompleted ? '✓' : isLocked ? '🔒' : '2'}
            </div>
            <div>
              <h4 className="font-semibold text-gray-900">Step 2: CDA Execution</h4>
              <p className="text-xs text-gray-600">
                {isCompleted
                  ? `Completed - ${cdaRequired === false ? 'Not Required' : cdaRequired === 'not_applicable' ? 'Not Applicable' : 'CDA Signed'}`
                  : isLocked
                  ? getLockReason('cda_execution')
                  : 'Determine if CDA is required and process accordingly'}
              </p>
            </div>
          </div>
          {!isLocked && (
            <svg
              className={`w-5 h-5 text-gray-500 transform transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        {isExpanded && !isLocked && (
          <div className="p-6 bg-white border-t border-gray-200">
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Is CDA required? <span className="text-red-500">*</span>
                </label>
                <div className="space-y-2">
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="cda_required"
                      checked={cdaRequired === true}
                      onChange={() => handleCdaRequiredChange(true)}
                      className="mr-3"
                    />
                    <span className="font-medium">Yes</span>
                  </label>
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="cda_required"
                      checked={cdaRequired === false}
                      onChange={() => handleCdaRequiredChange(false)}
                      className="mr-3"
                    />
                    <span className="font-medium">No</span>
                  </label>
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="cda_required"
                      checked={cdaRequired === 'not_applicable'}
                      onChange={() => handleCdaRequiredChange('not_applicable')}
                      className="mr-3"
                    />
                    <span className="font-medium">Not Applicable</span>
                  </label>
                </div>
              </div>

              {/* Comment box for No only (Not Applicable doesn't require comment) */}
              {cdaRequired === false && (
                <div className="border-t border-gray-200 pt-6">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Reason CDA not required <span className="text-red-500">*</span>
                  </label>
                  {isCompleted ? (
                    // Read-only view when completed
                    <div className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-800 whitespace-pre-wrap">
                      {cdaComment || <span className="text-gray-400 italic">No comment provided</span>}
                    </div>
                  ) : (
                    // Editable textarea when not completed
                    <textarea
                      value={cdaComment}
                      onChange={(e) => {
                        const newLocalData = { ...localData, cda_comment: e.target.value }
                        setLocalState({
                          ...localState,
                          cda_execution: newLocalData
                        })
                        // Save to backend
                        updateStep('cda_execution', 'in_progress', {
                          ...stepData,
                          cda_comment: e.target.value,
                        })
                      }}
                      placeholder="Please provide a reason why CDA is not required..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
                      rows={3}
                      required
                    />
                  )}
                </div>
              )}

              {/* CDA Required = Yes: Show Agreement status message */}
              {cdaRequired === true && (
                <div className="border-t border-gray-200 pt-6">
                  {error && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                      <p className="text-sm text-red-800">{error}</p>
                    </div>
                  )}
                  
                  {checkingCdaAgreement ? (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                      <p className="text-sm text-blue-800">Checking CDA Agreement status...</p>
                    </div>
                  ) : cdaAgreementStatus?.executed ? (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                      <p className="text-sm font-semibold text-green-900">✓ CDA Agreement Executed</p>
                      <p className="text-xs text-green-700 mt-1">
                        The CDA Agreement has been executed. You can now complete this step.
                      </p>
                    </div>
                  ) : cdaAgreementStatus?.exists && !cdaAgreementStatus?.executed ? (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                      <p className="text-sm font-semibold text-yellow-900">⚠️ CDA Agreement Not Executed</p>
                      <p className="text-xs text-yellow-700 mt-1">
                        A CDA Agreement exists but has not been executed yet. Please execute the CDA Agreement via the Agreement module before completing this step.
                      </p>
                      <button
                        onClick={() => checkCdaAgreement()}
                        disabled={checkingCdaAgreement}
                        className="mt-2 px-3 py-1 bg-yellow-600 text-white rounded text-xs hover:bg-yellow-700 disabled:opacity-50"
                      >
                        {checkingCdaAgreement ? 'Refreshing...' : '🔄 Refresh Status'}
                      </button>
                    </div>
                  ) : (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                      <p className="text-sm font-semibold text-yellow-900">CDA Must Be Executed via Agreement Module</p>
                      <p className="text-xs text-yellow-700 mt-1">
                        Please create and execute a CDA Agreement in the Agreement tab before completing this step.
                      </p>
                      <button
                        onClick={() => checkCdaAgreement()}
                        disabled={checkingCdaAgreement}
                        className="mt-2 px-3 py-1 bg-yellow-600 text-white rounded text-xs hover:bg-yellow-700 disabled:opacity-50"
                      >
                        {checkingCdaAgreement ? 'Checking...' : '🔄 Check Again'}
                      </button>
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-3 pt-4 border-t border-gray-200">
                {!isCompleted && (
                  <button
                    onClick={handleComplete}
                    disabled={!canComplete || loading}
                    className={`px-6 py-2 rounded-lg font-medium ${
                      canComplete
                        ? 'bg-green-600 text-white hover:bg-green-700'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    }`}
                  >
                    {loading ? 'Processing...' : 'Complete Step'}
                  </button>
                )}
                {isCompleted && (
                  <>
                    <button
                      onClick={handleReopen}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      disabled={loading}
                    >
                      Re-open for Editing
                    </button>
                    <button
                      onClick={handleComplete}
                      disabled={!canComplete || loading}
                      className={`px-6 py-2 rounded-lg font-medium ${
                        canComplete
                          ? 'bg-green-600 text-white hover:bg-green-700'
                          : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {loading ? 'Processing...' : 'Save & Keep Completed'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {isCompleted && !isExpanded && (
          <div className="p-4 bg-green-50 border-t border-gray-200 text-sm text-gray-700">
            <p>
              <strong>CDA Required:</strong>{' '}
              {cdaRequired === true ? 'Yes' : cdaRequired === false ? 'No' : 'Not Applicable'}
            </p>
            {/* Show comment when CDA is not required (only for No, not Not Applicable) */}
            {cdaRequired === false && cdaComment && (
              <div className="mt-3 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                <p className="text-xs font-semibold text-gray-700 mb-1">Reason:</p>
                <p className="text-sm text-gray-800 whitespace-pre-wrap">{cdaComment}</p>
              </div>
            )}
            {/* Show CDA Agreement executed status if Yes */}
            {cdaRequired === true && cdaAgreementStatus?.executed && (
              <div className="mt-2">
                <p className="text-green-700 font-semibold">✓ CDA Agreement Executed</p>
              </div>
            )}
            {step?.completed_at && (
              <p className="mt-2 text-xs text-gray-500">
                Completed on {new Date(step.completed_at).toLocaleDateString()}
              </p>
            )}
            {!isLocked && (
              <p className="mt-2 text-xs text-blue-600 italic">Click to edit this step</p>
            )}
            {isLocked && (
              <p className="mt-2 text-xs text-gray-500 italic">This step is locked and cannot be edited</p>
            )}
          </div>
        )}
      </div>
    )
  }

  // STEP 3: FEASIBILITY
  const renderFeasibility = () => {
    const step = getStep('feasibility')
    const isCompleted = isStepCompleted('feasibility')
    const isLocked = isStepLocked('feasibility')
    const isExpanded = expandedStep === 'feasibility'
    const stepData = step?.step_data || {}
    const localData = localState.feasibility || {}
    
    const questionnaireSent = stepData.questionnaire_sent || false
    const onsiteVisitRequired = localData.onsite_visit_required ?? stepData.onsite_visit_required ?? null
    const onsiteReportUploaded = stepData.onsite_report_uploaded || false

    // Completion requirements: toggles resolved, onsite report if required
    const canComplete =
      onsiteVisitRequired !== null &&
      (onsiteVisitRequired === false || onsiteReportUploaded)

    const handleComplete = async () => {
      if (!canComplete) {
        setError('Please ensure questionnaire responses are received and all toggles are resolved')
        return
      }
      
      // Check if feasibility responses exist - if so, response_received should be true
      const hasResponses = feasibilityResponses && feasibilityResponses.length > 0
      
      const newStepData = {
        ...stepData,
        onsite_visit_required: onsiteVisitRequired,
        // Include response_received if responses exist or if it was already set
        response_received: hasResponses || stepData.response_received || false,
        // Include response_received_at if setting response_received to true
        ...(hasResponses && !stepData.response_received_at ? {
          response_received_at: new Date().toISOString()
        } : {}),
      }
      
      await updateStep('feasibility', 'completed', newStepData)
      setLocalState({ ...localState, feasibility: {} })
    }

    const handleReopen = async () => {
      // Change status back to in_progress to allow editing
      const newStepData = {
        ...stepData,
        onsite_visit_required: onsiteVisitRequired,
      }
      await updateStep('feasibility', 'in_progress', newStepData)
      setLocalState({ ...localState, feasibility: {} })
    }

    const handleSave = async () => {
      const newStepData = {
        ...stepData,
        onsite_visit_required: onsiteVisitRequired,
      }
      await updateStep('feasibility', isCompleted ? 'completed' : 'in_progress', newStepData)
      setLocalState({ ...localState, feasibility: {} })
    }

    return (
      <div className="border border-gray-300 rounded-lg mb-4 shadow-sm">
        <div
          className={`p-4 cursor-pointer flex items-center justify-between ${
            isLocked ? 'bg-gray-100 opacity-60' : isCompleted ? 'bg-green-50 hover:bg-green-100' : 'bg-blue-50 hover:bg-blue-100'
          }`}
          onClick={() => !isLocked && setExpandedStep(isExpanded ? null : 'feasibility')}
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                isCompleted
                  ? 'bg-green-600 text-white'
                  : isLocked
                  ? 'bg-gray-400 text-white'
                  : 'bg-blue-600 text-white'
              }`}
            >
              {isCompleted ? '✓' : isLocked ? '🔒' : '3'}
            </div>
            <div>
              <h4 className="font-semibold text-gray-900">Step 3: Feasibility</h4>
              <p className="text-xs text-gray-600">
                {isCompleted
                  ? 'Completed - All feasibility activities resolved'
                  : isLocked
                  ? getLockReason('feasibility')
                  : 'Send questionnaire and manage feasibility activities'}
              </p>
            </div>
          </div>
          {!isLocked && (
            <svg
              className={`w-5 h-5 text-gray-500 transform transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        {isExpanded && !isLocked && (
          <div className="p-6 bg-white border-t border-gray-200">
            <div className="space-y-6">
              {/* Questionnaire Builder */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <label className="block text-sm font-medium text-gray-700">
                    Feasibility Questionnaire Builder
                  </label>
                  <button
                    onClick={handleAddCustomQuestion}
                    className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    disabled={loading || !selectedStudyId}
                  >
                    + Add Question
                  </button>
                </div>
                
                {loadingQuestions ? (
                  <div className="p-4 text-center text-gray-500">Loading questions...</div>
                ) : questionnaireQuestions.length === 0 ? (
                  <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600">
                    No questions found. Add custom questions or ensure external questionnaire is configured.
                  </div>
                ) : (
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    {/* Two-column layout */}
                    <div className="grid grid-cols-2 divide-x divide-gray-200">
                      {/* Left: Questions */}
                      <div className="bg-gray-50">
                        <div className="p-3 bg-gray-100 border-b border-gray-200 font-semibold text-sm text-gray-700">
                          Questions
                        </div>
                        <div className="max-h-96 overflow-y-auto">
                          {(() => {
                            // Group questions by section
                            const grouped: Record<string, any[]> = {}
                            const ungrouped: any[] = []
                            
                            questionnaireQuestions.forEach((q) => {
                              if (q.section) {
                                if (!grouped[q.section]) {
                                  grouped[q.section] = []
                                }
                                grouped[q.section].push(q)
                              } else {
                                ungrouped.push(q)
                              }
                            })
                            
                            return (
                              <div className="divide-y divide-gray-200">
                                {/* Grouped questions */}
                                {Object.entries(grouped).map(([section, questions]) => (
                                  <div key={section}>
                                    <div className="p-2 bg-gray-100 text-xs font-semibold text-gray-600 border-b border-gray-200">
                                      {section}
                                    </div>
                                    {questions.map((q, idx) => (
                                      <div key={idx} className="p-3 hover:bg-gray-100">
                                        <div className="flex items-start justify-between gap-2">
                                          <div className="flex-1">
                                            <p className="text-sm text-gray-900">{q.text}</p>
                                            <div className="flex items-center gap-2 mt-1">
                                              <span className="text-xs text-gray-500">
                                                {q.type === 'text' && '📝 Text'}
                                                {q.type === 'number' && '🔢 Number'}
                                                {q.type === 'yes_no' && '✓ Yes/No'}
                                                {!['text', 'number', 'yes_no'].includes(q.type) && `📋 ${q.type}`}
                                              </span>
                                              {q.source === 'external' && (
                                                <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
                                                  External
                                                </span>
                                              )}
                                              {q.source === 'custom' && (
                                                <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                                                  Custom
                                                </span>
                                              )}
                                            </div>
                                          </div>
                                          {q.source === 'custom' && (
                                            <button
                                              onClick={() => handleDeleteCustomQuestion(q.id || '')}
                                              className="text-red-600 hover:text-red-800 text-xs"
                                              title="Delete custom question"
                                            >
                                              ✕
                                            </button>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                ))}
                                
                                {/* Ungrouped questions */}
                                {ungrouped.map((q, idx) => (
                                  <div key={idx} className="p-3 hover:bg-gray-100">
                                    <div className="flex items-start justify-between gap-2">
                                      <div className="flex-1">
                                        <p className="text-sm text-gray-900">{q.text}</p>
                                        <div className="flex items-center gap-2 mt-1">
                                          <span className="text-xs text-gray-500">
                                            {q.type === 'text' && '📝 Text'}
                                            {q.type === 'number' && '🔢 Number'}
                                            {q.type === 'yes_no' && '✓ Yes/No'}
                                            {!['text', 'number', 'yes_no'].includes(q.type) && `📋 ${q.type}`}
                                          </span>
                                          {q.source === 'external' && (
                                            <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
                                              External
                                            </span>
                                          )}
                                          {q.source === 'custom' && (
                                            <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                                              Custom
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      {q.source === 'custom' && (
                                        <button
                                          onClick={() => handleDeleteCustomQuestion(q.id || '')}
                                          className="text-red-600 hover:text-red-800 text-xs"
                                          title="Delete custom question"
                                        >
                                          ✕
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )
                          })()}
                        </div>
                      </div>
                      
                      {/* Right: Answers (from submitted responses) */}
                      <div className="bg-white">
                        <div className="p-3 bg-gray-100 border-b border-gray-200 font-semibold text-sm text-gray-700 flex items-center justify-between">
                          <span>Responses</span>
                          <button
                            onClick={loadFeasibilityResponses}
                            disabled={loadingResponses}
                            className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 disabled:opacity-50"
                            title="Refresh responses"
                          >
                            {loadingResponses ? 'Refreshing...' : '🔄 Refresh'}
                          </button>
                        </div>
                        <div className="max-h-96 overflow-y-auto p-4">
                          {loadingResponses ? (
                            <div className="text-center text-gray-500 py-4">Loading responses...</div>
                          ) : feasibilityResponses.length === 0 ? (
                            <div className="text-sm text-gray-500 italic">
                              No responses received yet. Send the feasibility form to receive responses.
                              <p className="text-xs mt-2 text-gray-400">
                                Responses will appear automatically when submitted (auto-refreshes every 5 seconds)
                              </p>
                            </div>
                          ) : (
                            <div className="space-y-4">
                              {feasibilityResponses
                                .filter((responseSet) => responseSet.responses && responseSet.responses.length > 0)
                                .map((responseSet, idx) => (
                                <div key={responseSet.request_id || idx} className="border-b border-gray-200 pb-4 last:border-0">
                                  {responseSet.completed_at && (
                                    <div className="text-xs text-gray-500 mb-2">
                                      Submitted: {new Date(responseSet.completed_at).toLocaleString()}
                                      {responseSet.status === 'completed' && (
                                        <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded">Completed</span>
                                      )}
                                    </div>
                                  )}
                                  <div className="space-y-3">
                                    {responseSet.responses.map((resp: any, respIdx: number) => (
                                      <div key={resp.id || respIdx} className="text-sm">
                                        <div className="font-medium text-gray-700 mb-1">{resp.question_text}</div>
                                        <div className="text-gray-900 bg-gray-50 p-2 rounded">{resp.answer}</div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Protocol Synopsis Upload */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Protocol Synopsis
                </label>
                {protocolSynopsis ? (
                  <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{protocolSynopsis.file_name}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {(protocolSynopsis.size / 1024).toFixed(2)} KB
                          {protocolSynopsis.uploaded_at && (
                            <> • Uploaded {new Date(protocolSynopsis.uploaded_at).toLocaleDateString()}</>
                          )}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={handleDownloadProtocolSynopsis}
                          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                          Download
                        </button>
                        {!questionnaireSent && (
                          <button
                            onClick={handleDeleteProtocolSynopsis}
                            className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                    {questionnaireSent && (
                      <p className="text-xs text-yellow-600 mt-2">
                        ⚠️ Cannot delete after feasibility form has been sent
                      </p>
                    )}
                  </div>
                ) : (
                  <div>
                    <input
                      type="file"
                      className="hidden"
                      id="protocol-synopsis-upload"
                      accept=".pdf,.doc,.docx"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) {
                          handleUploadProtocolSynopsis(file)
                        }
                      }}
                      disabled={uploadingProtocolSynopsis || questionnaireSent}
                    />
                    <label
                      htmlFor="protocol-synopsis-upload"
                      className={`inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer ${
                        uploadingProtocolSynopsis || questionnaireSent ? 'opacity-50 cursor-not-allowed' : ''
                      }`}
                    >
                      {uploadingProtocolSynopsis ? 'Uploading...' : 'Upload Protocol Synopsis'}
                    </label>
                    <p className="text-xs text-gray-500 mt-1">
                      Optional: Attach Protocol Synopsis document to be sent with the feasibility form
                    </p>
                  </div>
                )}
              </div>

              {/* Reset Feasibility (Testing) */}
              <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-yellow-900">Testing: Reset All Feasibility Data</p>
                    <p className="text-xs text-yellow-700 mt-1">
                      This will delete all feasibility requests, responses, and reset workflow steps for all studies.
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      if (!window.confirm('Are you sure you want to reset ALL feasibility data? This will delete all requests and responses for all studies.')) {
                        return
                      }
                      setResettingFeasibility(true)
                      setError(null)
                      try {
                        await api.post(`${apiBase}/feasibility/reset-all`)
                        // Reload everything
                        await loadSteps()
                        await loadFeasibilityResponses()
                        await loadProtocolSynopsis()
                        setError(null)
                        alert('All feasibility data has been reset successfully!')
                      } catch (err: any) {
                        setError(err.response?.data?.detail || 'Failed to reset feasibility data')
                      } finally {
                        setResettingFeasibility(false)
                      }
                    }}
                    className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 disabled:opacity-50 text-sm"
                    disabled={resettingFeasibility}
                  >
                    {resettingFeasibility ? 'Resetting...' : '🔄 Reset All Feasibility'}
                  </button>
                </div>
              </div>

              {/* Send Feasibility Form */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Send Feasibility Form
                </label>
                {!questionnaireSent ? (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">
                        Recipient Email Address
                      </label>
                      <input
                        type="email"
                        value={feasibilityEmail}
                        onChange={(e) => setFeasibilityEmail(e.target.value)}
                        placeholder="labeshg@dizzaroo.com"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Default: labeshg@dizzaroo.com (configure via FEASIBILITY_DEFAULT_EMAIL env var)
                      </p>
                    </div>
                    <button
                      onClick={handleSendFeasibilityRequest}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                      disabled={loading || sendingRequest || !selectedStudyId || !siteId || !feasibilityEmail.trim()}
                    >
                      {sendingRequest ? 'Sending...' : 'Send Feasibility'}
                    </button>
                  </div>
                ) : (
                  <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                    <p className="text-sm text-green-700">✓ Feasibility form sent</p>
                    {stepData.questionnaire_sent_at && (
                      <p className="text-xs text-gray-600 mt-1">
                        Sent on {new Date(stepData.questionnaire_sent_at).toLocaleDateString()}
                      </p>
                    )}
                    <p className="text-xs text-gray-500 mt-1">
                      Email sent to: {feasibilityEmail}
                    </p>
                  </div>
                )}
              </div>


              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  On-site Visit Required?
                </label>
                <div className="space-y-2">
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="onsite_visit_required"
                      checked={onsiteVisitRequired === true}
                      onChange={() => setLocalState({
                        ...localState,
                        feasibility: { ...localData, onsite_visit_required: true }
                      })}
                      className="mr-3"
                    />
                    <span className="font-medium">Yes</span>
                  </label>
                  <label className="flex items-center p-3 border-2 border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="onsite_visit_required"
                      checked={onsiteVisitRequired === false}
                      onChange={() => setLocalState({
                        ...localState,
                        feasibility: { ...localData, onsite_visit_required: false }
                      })}
                      className="mr-3"
                    />
                    <span className="font-medium">No</span>
                  </label>
                </div>
              </div>

              {onsiteVisitRequired === true && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Upload On-site Visit Report <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="file"
                    className="hidden"
                    id="onsite-report-upload"
                    accept=".pdf,.doc,.docx"
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (file) {
                        try {
                          await uploadDocument(file, 'onsite_visit_report', 'On-site Visit Report', 'feasibility', {
                            onsite_report_uploaded: true,
                          })
                        } catch (err) {
                          // Error already shown
                        }
                      }
                    }}
                  />
                  <label
                    htmlFor="onsite-report-upload"
                    className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
                  >
                    {onsiteReportUploaded ? 'Replace Report' : 'Upload Report'}
                  </label>
                  {onsiteReportUploaded && (
                    <p className="text-xs text-green-600 mt-2">✓ Report uploaded</p>
                  )}
                </div>
              )}

              <div className="flex gap-3 pt-4 border-t border-gray-200">
                {!isCompleted && (
                  <button
                    onClick={handleComplete}
                    disabled={!canComplete || loading}
                    className={`px-6 py-2 rounded-lg font-medium ${
                      canComplete
                        ? 'bg-green-600 text-white hover:bg-green-700'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    }`}
                  >
                    {loading ? 'Processing...' : 'Complete Step'}
                  </button>
                )}
                {isCompleted && (
                  <>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                      disabled={loading}
                    >
                      Save Changes
                    </button>
                    <button
                      onClick={handleReopen}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      disabled={loading}
                    >
                      Re-open for Editing
                    </button>
                    <button
                      onClick={handleComplete}
                      disabled={!canComplete || loading}
                      className={`px-6 py-2 rounded-lg font-medium ${
                        canComplete
                          ? 'bg-green-600 text-white hover:bg-green-700'
                          : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {loading ? 'Processing...' : 'Save & Keep Completed'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {isCompleted && !isExpanded && (
          <div className="p-4 bg-green-50 border-t border-gray-200 text-sm text-gray-700">
            <p className="mt-2"><strong>On-site Visit:</strong> {onsiteVisitRequired ? 'Required' : 'Not Required'}</p>
            {step?.completed_at && (
              <p className="mt-2 text-xs text-gray-500">
                Completed on {new Date(step.completed_at).toLocaleDateString()}
              </p>
            )}
            <p className="mt-2 text-xs text-blue-600 italic">Click to edit this step</p>
          </div>
        )}
      </div>
    )
  }

  // STEP 4: FINAL SITE SELECTION OUTCOME
  const renderSiteSelectionOutcome = () => {
    const step = getStep('site_selection_outcome')
    const isCompleted = isStepCompleted('site_selection_outcome')
    const isLocked = isStepLocked('site_selection_outcome')
    const isExpanded = expandedStep === 'site_selection_outcome'
    const stepData = step?.step_data || {}
    const localData = localState.site_selection_outcome || {}
    
    const decision = localData.decision ?? stepData.decision ?? ''
    const comments = localData.comments ?? stepData.comments ?? ''
    const feasibilityStep = getStep('feasibility')

    // A "Not Selected" outcome must carry a short reason (captured in comments)
    // so the record explains why the site stays Pending rather than going Active.
    const needsReason = decision === 'not_selected'
    const canComplete = !!decision && (!needsReason || comments.trim() !== '')

    const handleComplete = async () => {
      if (!decision) {
        setError('Please select a final decision before completing')
        return
      }
      if (needsReason && comments.trim() === '') {
        setError('Please add a brief reason in Comments for not selecting this site')
        return
      }
      
      const newStepData = {
        ...stepData,
        decision: decision,
        comments: comments,
      }
      
      await updateStep('site_selection_outcome', 'completed', newStepData)
      setLocalState({ ...localState, site_selection_outcome: {} })
    }

    const handleReopen = async () => {
      // Change status back to in_progress to allow editing
      const newStepData = {
        ...stepData,
        decision: decision,
        comments: comments,
      }
      await updateStep('site_selection_outcome', 'in_progress', newStepData)
      setLocalState({ ...localState, site_selection_outcome: {} })
    }

    const handleSave = async () => {
      const newStepData = {
        ...stepData,
        decision: decision,
        comments: comments,
      }
      await updateStep('site_selection_outcome', isCompleted ? 'completed' : 'in_progress', newStepData)
      setLocalState({ ...localState, site_selection_outcome: {} })
    }

    return (
      <div className="border border-gray-300 rounded-lg mb-4 shadow-sm">
        <div
          className={`p-4 cursor-pointer flex items-center justify-between ${
            isLocked ? 'bg-gray-100 opacity-60' : isCompleted ? 'bg-green-50 hover:bg-green-100' : 'bg-blue-50 hover:bg-blue-100'
          }`}
          onClick={() => !isLocked && setExpandedStep(isExpanded ? null : 'site_selection_outcome')}
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                isCompleted
                  ? 'bg-green-600 text-white'
                  : isLocked
                  ? 'bg-gray-400 text-white'
                  : 'bg-blue-600 text-white'
              }`}
            >
              {isCompleted ? '✓' : isLocked ? '🔒' : '4'}
            </div>
            <div>
              <h4 className="font-semibold text-gray-900">Step 4: Final Site Selection Outcome</h4>
              <p className="text-xs text-gray-600">
                {isCompleted
                  ? `Decision: ${decision === 'selected' ? 'Site Selected' : 'Site Not Selected'}`
                  : isLocked
                  ? getLockReason('site_selection_outcome')
                  : 'Review feasibility and make final selection decision'}
              </p>
            </div>
          </div>
          {!isLocked && (
            <svg
              className={`w-5 h-5 text-gray-500 transform transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        {isExpanded && !isLocked && (
          <div className="p-6 bg-white border-t border-gray-200">
            <div className="space-y-6">
              <div className="bg-gray-50 p-4 rounded-lg">
                <h5 className="text-sm font-semibold text-gray-700 mb-3">Feasibility Summary</h5>
                <div className="text-sm text-gray-600 space-y-1">
                  <p>
                    <strong>On-site Visit:</strong>{' '}
                    {feasibilityStep?.step_data?.onsite_visit_required ? 'Required' : 'Not Required'}
                  </p>
                  {feasibilityStep?.step_data?.onsite_visit_required && (
                    <p>
                      <strong>Visit Report:</strong>{' '}
                      {feasibilityStep?.step_data?.onsite_report_uploaded ? '✓ Uploaded' : 'Pending'}
                    </p>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Comments {needsReason && <span className="text-red-500">*</span>}
                </label>
                <textarea
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  rows={4}
                  value={comments}
                  onChange={(e) => setLocalState({
                    ...localState,
                    site_selection_outcome: { ...localData, comments: e.target.value }
                  })}
                  placeholder={needsReason
                    ? 'Briefly explain why this site was not selected...'
                    : 'Add any comments or notes for this decision...'}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Final Decision <span className="text-red-500">*</span>
                </label>
                <div className="space-y-3">
                  <label className="flex items-center p-4 border-2 border-gray-200 rounded-lg hover:bg-green-50 cursor-pointer">
                    <input
                      type="radio"
                      name="selection_decision"
                      value="selected"
                      checked={decision === 'selected'}
                      onChange={(e) => setLocalState({
                        ...localState,
                        site_selection_outcome: { ...localData, decision: e.target.value }
                      })}
                      className="mr-3"
                    />
                    <div>
                      <span className="font-medium text-green-700">Site Selected</span>
                      <p className="text-xs text-gray-500">Site will proceed to start-up phase</p>
                    </div>
                  </label>
                  <label className="flex items-center p-4 border-2 border-gray-200 rounded-lg hover:bg-red-50 cursor-pointer">
                    <input
                      type="radio"
                      name="selection_decision"
                      value="not_selected"
                      checked={decision === 'not_selected'}
                      onChange={(e) => setLocalState({
                        ...localState,
                        site_selection_outcome: { ...localData, decision: e.target.value }
                      })}
                      className="mr-3"
                    />
                    <div>
                      <span className="font-medium text-red-700">Site Not Selected</span>
                      <p className="text-xs text-gray-500">Site will not proceed further</p>
                    </div>
                  </label>
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t border-gray-200">
                {!isCompleted && (
                  <button
                    onClick={handleComplete}
                    disabled={!canComplete || loading}
                    className={`px-6 py-2 rounded-lg font-medium ${
                      canComplete
                        ? 'bg-green-600 text-white hover:bg-green-700'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    }`}
                  >
                    {loading ? 'Processing...' : 'Complete Step & Finalize Decision'}
                  </button>
                )}
                {isCompleted && (
                  <>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                      disabled={loading}
                    >
                      Save Changes
                    </button>
                    <button
                      onClick={handleReopen}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      disabled={loading}
                    >
                      Re-open for Editing
                    </button>
                    <button
                      onClick={handleComplete}
                      disabled={!canComplete || loading}
                      className={`px-6 py-2 rounded-lg font-medium ${
                        canComplete
                          ? 'bg-green-600 text-white hover:bg-green-700'
                          : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {loading ? 'Processing...' : 'Save & Keep Completed'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {isCompleted && !isExpanded && (
          <div className="p-4 bg-green-50 border-t border-gray-200 text-sm text-gray-700">
            <div className="p-3 bg-white border border-green-200 rounded-lg">
              <p className="font-semibold text-green-800 mb-2">
                ✓ Final Decision: {decision === 'selected' ? 'Site Selected' : 'Site Not Selected'}
              </p>
              {comments && <p className="mt-2"><strong>Comments:</strong> {comments}</p>}
            </div>
            {step?.completed_at && (
              <p className="mt-2 text-xs text-gray-500">
                Completed on {new Date(step.completed_at).toLocaleDateString()}
              </p>
            )}
            <p className="mt-2 text-xs text-blue-600 italic">Click to edit this step</p>
          </div>
        )}
      </div>
    )
  }

  if (loading && steps.length === 0) {
    return (
      <div className="p-4 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="text-sm text-gray-600 mt-2">Loading workflow...</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">{error}</div>
      )}

      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Under Consideration Workflow</h3>
          <p className="text-sm text-gray-600">
            Complete each step sequentially. Each step contains functional work areas where you perform actions.
            Steps are only completed when you explicitly click "Complete Step" after finishing all required work.
          </p>
        </div>
        <button
          type="button"
          onClick={handleResetWorkflow}
          disabled={loading}
          className="inline-flex items-center rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Reset workflow for this site
        </button>
      </div>

      {renderSiteIdentification()}
      {renderCDAExecution()}
      {renderFeasibility()}
      {renderSiteSelectionOutcome()}
    </div>
  )
}

export default UnderConsiderationWorkflow