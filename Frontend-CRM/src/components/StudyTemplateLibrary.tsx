import React, { useState, useEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import {
  useAgreementTemplates,
  useCreateClauseTemplate,
  useDeactivateTemplate,
  useSaveFieldMappings,
  useSavePlaceholderConfig,
  useTemplateAiSuggestions,
  useTemplateFieldMappingOptions,
  useUploadTemplate,
  type TemplateAiSuggestion,
} from '@/lib/queries/useAgreements'
import { useStudySite } from '../contexts/StudySiteContext'
import { useAuth } from '../contexts/AuthContext'
import TemplateDocxViewer from './TemplateDocxViewer'

interface StudyTemplate {
  id: string
  study_id: string
  template_name: string
  template_type: 'CDA' | 'CTA' | 'BUDGET' | 'OTHER'
  template_content: any // TipTap JSON (legacy)
  template_file_path?: string | null // Path to DOCX file
  placeholder_config?: Record<string, { editable: boolean }> | null
  field_mappings?: Record<string, string> | null // Dynamic field mappings: {"PLACEHOLDER_NAME": "data_source.field_name"}
  created_by: string | null
  created_at: string
  updated_at: string
  is_active: string
  composition_mode?: 'DOCX_UPLOAD' | 'CLAUSE_COMPOSED'
}

interface StudyTemplateLibraryProps {
  apiBase?: string
}

interface FieldOption {
  field: string
  label: string
}

/** Render modals at document.body so they sit above the navbar (z-[200]). */
function ModalPortal({ children }: { children: React.ReactNode }) {
  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 p-4">
      {children}
    </div>,
    document.body,
  )
}

const StudyTemplateLibrary: React.FC<StudyTemplateLibraryProps> = () => {
  const { selectedStudyId, selectedSiteId } = useStudySite()
  const navigate = useNavigate()
  useAuth()
  const [error, setError] = useState<string | null>(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<StudyTemplate | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [configTemplate, setConfigTemplate] = useState<StudyTemplate | null>(null)
  const [placeholderConfig, setPlaceholderConfig] = useState<Record<string, { editable: boolean }>>({})

  // Field mappings state
  const [showFieldMappingsModal, setShowFieldMappingsModal] = useState(false)
  const [fieldMappingsTemplate, setFieldMappingsTemplate] = useState<StudyTemplate | null>(null)
  const [fieldMappings, setFieldMappings] = useState<Record<string, string>>({})
  const [newMappingPlaceholder, setNewMappingPlaceholder] = useState('')
  const [newMappingDataSource, setNewMappingDataSource] = useState<'site_profile' | 'agreement'>('site_profile')
  const [newMappingField, setNewMappingField] = useState('')

  // Upload form state
  const [templateName, setTemplateName] = useState('')
  const [templateType, setTemplateType] = useState<'CDA' | 'CTA' | 'BUDGET' | 'OTHER'>('CDA')
  const [templateFile, setTemplateFile] = useState<File | null>(null)

  const templatesQuery = useAgreementTemplates(selectedStudyId, { activeOnly: false })
  const templates: StudyTemplate[] = (templatesQuery.data ?? []) as StudyTemplate[]
  const loading = Boolean(selectedStudyId) && templatesQuery.isFetching

  // Mapping-options query: only fires once the user opens the field-mappings
  // modal, so the dropdown stays cheap when the modal is closed.
  const mappingOptionsQuery = useTemplateFieldMappingOptions({
    enabled: showFieldMappingsModal,
  })
  const mappingOptions = useMemo(
    () => mappingOptionsQuery.data ?? { site_profile: [] as FieldOption[], agreement: [] as FieldOption[] },
    [mappingOptionsQuery.data],
  )

  // AI suggestions query: lazily enabled only while the field-mappings modal
  // is open. Errors are silently swallowed — the modal still works manually.
  const aiSuggestionsQuery = useTemplateAiSuggestions(
    fieldMappingsTemplate?.id,
    { enabled: showFieldMappingsModal },
  )
  // Build a lookup map: placeholder → suggestion (for O(1) access in render)
  const aiSuggestionsMap = useMemo<Record<string, TemplateAiSuggestion>>(() => {
    const suggestions = aiSuggestionsQuery.data?.suggestions ?? []
    return Object.fromEntries(suggestions.map((s) => [s.placeholder, s]))
  }, [aiSuggestionsQuery.data])

  // Suggestions that can still be applied: a valid 'source.field' value AND not
  // already present in the working mappings. Drives BOTH the banner count and the
  // Accept-all button, so applying suggestions visibly updates the UI (the banner
  // shrinks / disappears) instead of looking inert when the new rows land below
  // the fold in the scrollable Current Mappings list.
  const unappliedAiSuggestions = useMemo(
    () => (aiSuggestionsQuery.data?.suggestions ?? []).filter(
      (s) => typeof s.suggested_source === 'string' &&
             s.suggested_source.includes('.') &&
             !fieldMappings[s.placeholder],
    ),
    [aiSuggestionsQuery.data, fieldMappings],
  )

  const [showClauseModal, setShowClauseModal]         = useState(false)
  const [clauseTemplateName, setClauseTemplateName]   = useState('')
  const [clauseTemplateType, setClauseTemplateType]   = useState<'CDA' | 'CTA' | 'BUDGET' | 'OTHER'>('CDA')

  const uploadMutation = useUploadTemplate(selectedStudyId)
  const createClauseMutation = useCreateClauseTemplate(selectedStudyId)
  const deactivateMutation = useDeactivateTemplate(selectedStudyId)
  const savePlaceholderMutation = useSavePlaceholderConfig(selectedStudyId)
  const saveFieldMappingsMutation = useSaveFieldMappings(selectedStudyId)
  const uploading = uploadMutation.isPending
  const savingConfig = savePlaceholderMutation.isPending
  const savingFieldMappings = saveFieldMappingsMutation.isPending

  // Surface query fetch errors with the existing extraction helper.
  const formatApiError = (err: any, fallback: string) => {
    if (!err?.response?.data) return fallback
    const detail = err.response.data.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
    }
    if (typeof detail === 'object' && detail !== null) {
      return detail.msg || JSON.stringify(detail)
    }
    return fallback
  }

  useEffect(() => {
    if (!templatesQuery.isError) return
    setError(formatApiError(templatesQuery.error, 'Failed to load templates'))
  }, [templatesQuery.isError, templatesQuery.error])


  const handleUploadTemplate = async () => {
    if (!selectedStudyId || !templateName || !templateFile) {
      setError('Please provide template name and DOCX file')
      return
    }

    // Validate file type - DOCX only
    const fileName = templateFile.name.toLowerCase()
    if (!fileName.endsWith('.docx') && !fileName.endsWith('.doc')) {
      setError('Only DOCX files are supported. Please upload a .docx file. PDF uploads are no longer supported.')
      return
    }

    setError(null)
    try {
      await uploadMutation.mutateAsync({
        templateName,
        templateType,
        templateFile,
        siteId: selectedSiteId ?? null,
      })
      // Reset form
      setTemplateName('')
      setTemplateType('CDA')
      setTemplateFile(null)
      setShowUploadModal(false)
    } catch (err: any) {
      setError(formatApiError(err, 'Failed to upload template'))
      console.error('Failed to upload template:', err)
    }
  }

  const handleCreateClauseTemplate = async () => {
    if (!selectedStudyId || !clauseTemplateName.trim()) {
      setError('Please provide a template name')
      return
    }
    setError(null)
    try {
      const created = await createClauseMutation.mutateAsync({
        templateName: clauseTemplateName.trim(),
        templateType: clauseTemplateType,
      })
      setClauseTemplateName('')
      setClauseTemplateType('CDA')
      setShowClauseModal(false)
      navigate(`/templates/${created.id}/builder`)
    } catch (err: any) {
      setError(formatApiError(err, 'Failed to create clause template'))
    }
  }

  const handleDeactivateTemplate = async (templateId: string) => {
    if (!confirm('Are you sure you want to deactivate this template? It cannot be used for new agreements.')) {
      return
    }

    try {
      await deactivateMutation.mutateAsync(templateId)
    } catch (err: any) {
      setError(formatApiError(err, 'Failed to deactivate template'))
      console.error('Failed to deactivate template:', err)
    }
  }

  const handlePreviewTemplate = (template: StudyTemplate) => {
    setSelectedTemplate(template)
    setShowPreview(true)
  }

  const handleConfigurePlaceholders = (template: StudyTemplate) => {
    setConfigTemplate(template)
    // Initialize config with template's existing config or default (all editable)
    const config = template.placeholder_config || {}
    setPlaceholderConfig(config)
    setShowConfigModal(true)
  }

  const handleSavePlaceholderConfig = async () => {
    if (!configTemplate) return
    try {
      await savePlaceholderMutation.mutateAsync({
        templateId: configTemplate.id,
        placeholderConfig,
      })
      setShowConfigModal(false)
      setConfigTemplate(null)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save placeholder configuration')
      console.error('Failed to save placeholder config:', err)
    }
  }

  const handleToggleEditable = (placeholderName: string) => {
    setPlaceholderConfig(prev => ({
      ...prev,
      [placeholderName]: {
        editable: !(prev[placeholderName]?.editable ?? true)
      }
    }))
  }

  const handleConfigureFieldMappings = (template: StudyTemplate) => {
    setFieldMappingsTemplate(template)
    // Initialize mappings with template's existing mappings or empty object
    const mappings = template.field_mappings || {}
    setFieldMappings(mappings)
    // Opening the modal triggers useTemplateFieldMappingOptions to fire.
    setShowFieldMappingsModal(true)
  }

  const handleSaveFieldMappings = async () => {
    if (!fieldMappingsTemplate) return
    try {
      await saveFieldMappingsMutation.mutateAsync({
        templateId: fieldMappingsTemplate.id,
        fieldMappings,
      })
      setShowFieldMappingsModal(false)
      setFieldMappingsTemplate(null)
      setFieldMappings({})
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save field mappings')
      console.error('Failed to save field mappings:', err)
    }
  }

  const handleAddFieldMapping = () => {
    if (!newMappingPlaceholder || !newMappingField) {
      setError('Please provide both placeholder name and field name')
      return
    }
    
    const placeholderName = newMappingPlaceholder.toUpperCase().replace(/\s+/g, '_')
    const mappingPath = `${newMappingDataSource}.${newMappingField}`
    
    setFieldMappings(prev => ({
      ...prev,
      [placeholderName]: mappingPath
    }))
    
    // Reset form
    setNewMappingPlaceholder('')
    setNewMappingDataSource('site_profile')
    setNewMappingField('')
  }

  const handleRemoveFieldMapping = (placeholderName: string) => {
    setFieldMappings(prev => {
      const updated = { ...prev }
      delete updated[placeholderName]
      return updated
    })
  }

  const handleAcceptAllAiSuggestions = () => {
    if (unappliedAiSuggestions.length === 0) return
    setFieldMappings(prev => {
      const updated = { ...prev }
      for (const s of unappliedAiSuggestions) {
        // Already de-duped + source-validated by the memo; just apply.
        updated[s.placeholder] = s.suggested_source
      }
      return updated
    })
  }

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString()
  }

  if (!selectedStudyId) {
    return (
      <div className="flex h-full items-center justify-center p-8 bg-slate-50">
        <div className="text-center">
          <div className="mx-auto mb-4 h-14 w-14 rounded-2xl bg-slate-100 flex items-center justify-center">
            <svg className="h-7 w-7 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-slate-700 mb-1">No Study Selected</h2>
          <p className="text-sm text-slate-400">Select a study from the top bar to view templates.</p>
        </div>
      </div>
    )
  }

  return (
  <div className="flex flex-col h-full bg-gray-50 p-6 min-h-0 max-w-7xl mx-auto w-full overflow-hidden">
      {/* Header */}
      <div className="mb-6 shrink-0">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Template Library</h1>
        <p className="text-gray-600">
          Manage document templates for this study. Templates are used to create new agreements.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800 shrink-0">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      {/* Actions */}
      <div className="mb-6 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            data-testid="template-upload-button"
          >
            + Upload Template
          </button>
          <button
            onClick={() => setShowClauseModal(true)}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 font-medium"
            data-testid="template-new-clause-button"
          >
            + New Clause Template
          </button>
        </div>
      </div>

      {/* Templates List */}
      <div className="flex-1 min-h-0 flex flex-col">
      {loading ? (
        <div className="text-center py-8 text-gray-500">Loading templates...</div>
      ) : templates.length === 0 ? (
        <div className="text-center py-8 bg-white rounded-lg border border-gray-200">
          <div className="text-4xl mb-2">📄</div>
          <p className="text-gray-600">No templates found. Upload a template to get started.</p>
        </div>
      ) : (
        <div className="flex flex-col flex-1 min-h-0 bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm" data-testid="template-list-table">
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 sticky top-0 z-10">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Template Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[320px]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {templates.map((template) => (
                <tr key={template.id} className="hover:bg-gray-50/60">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{template.template_name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                      {template.template_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      template.is_active === 'true' 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {template.is_active === 'true' ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(template.created_at)}
                  </td>
                  <td className="px-6 py-4 text-sm font-medium">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handlePreviewTemplate(template)}
                        className="px-2.5 py-1 rounded-md text-blue-600 hover:text-blue-800 hover:bg-blue-50 transition-colors"
                      >
                        View
                      </button>
                      <button
                        type="button"
                        onClick={() => handleConfigurePlaceholders(template)}
                        className="px-2.5 py-1 rounded-md text-purple-600 hover:text-purple-800 hover:bg-purple-50 transition-colors"
                      >
                        Configure
                      </button>
                      <button
                        type="button"
                        onClick={() => handleConfigureFieldMappings(template)}
                        className="px-2.5 py-1 rounded-md text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 transition-colors"
                        title="Configure Field Mappings"
                      >
                        Field Mappings
                      </button>
                      <button
                        type="button"
                        onClick={() => navigate(`/templates/${template.id}/builder`)}
                        className="px-2.5 py-1 rounded-md text-emerald-700 hover:text-emerald-900 hover:bg-emerald-50 border border-emerald-300 transition-colors font-medium"
                        title="Open Clause Builder"
                      >
                        Clause Builder →
                      </button>
                      {template.is_active === 'true' && (
                        <button
                          type="button"
                          onClick={() => handleDeactivateTemplate(template.id)}
                          className="px-2.5 py-1 rounded-md text-red-600 hover:text-red-800 hover:bg-red-50 transition-colors"
                        >
                          Deactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <ModalPortal>
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Upload Template</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Template Name
                </label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  placeholder="e.g., Standard CDA Template"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Template Type
                </label>
                <select
                  value={templateType}
                  onChange={(e) => setTemplateType(e.target.value as any)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  <option value="CDA">CDA</option>
                  <option value="CTA">CTA</option>
                  <option value="BUDGET">BUDGET</option>
                  <option value="OTHER">OTHER</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Template File (DOCX)
                </label>
                <input
                  type="file"
                  accept=".docx,.doc"
                  onChange={(e) => setTemplateFile(e.target.files?.[0] || null)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                />
                <p className="text-xs text-gray-500 mt-1">
                  DOCX files will be automatically converted to editable format. PDF uploads are no longer supported.
                </p>
              </div>
            </div>

            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => {
                  setShowUploadModal(false)
                  setTemplateName('')
                  setTemplateType('CDA')
                  setTemplateFile(null)
                }}
                disabled={uploading}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 disabled:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleUploadTemplate}
                disabled={uploading || !templateName || !templateFile}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
              >
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        </ModalPortal>
      )}

      {/* New Clause Template Modal */}
      {showClauseModal && (
        <ModalPortal>
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-gray-900 mb-1">New Clause Template</h3>
            <p className="text-sm text-gray-500 mb-4">
              Creates a blank clause-composed template. You'll be taken straight to the Clause Builder.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Template Name</label>
                <input
                  type="text"
                  value={clauseTemplateName}
                  onChange={(e) => setClauseTemplateName(e.target.value)}
                  placeholder="e.g. Standard CDA v2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateClauseTemplate() }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Template Type</label>
                <select
                  value={clauseTemplateType}
                  onChange={(e) => setClauseTemplateType(e.target.value as 'CDA' | 'CTA' | 'BUDGET' | 'OTHER')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="CDA">CDA</option>
                  <option value="CTA">CTA</option>
                  <option value="BUDGET">BUDGET</option>
                  <option value="OTHER">OTHER</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => { setShowClauseModal(false); setClauseTemplateName(''); }}
                disabled={createClauseMutation.isPending}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateClauseTemplate}
                disabled={createClauseMutation.isPending || !clauseTemplateName.trim()}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-sm font-medium"
              >
                {createClauseMutation.isPending ? 'Creating…' : 'Create & Open Builder'}
              </button>
            </div>
          </div>
        </ModalPortal>
      )}

      {/* Preview Modal */}
      {showPreview && selectedTemplate && (
        <ModalPortal>
          <div className="flex flex-col bg-white rounded-xl shadow-2xl w-full max-w-[96vw] h-[92vh] overflow-hidden">
            <div className="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-gray-200">
              <div>
                <h3 className="text-lg font-bold text-gray-900">{selectedTemplate.template_name}</h3>
                <div className="mt-1 flex items-center gap-2">
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                    {selectedTemplate.template_type}
                  </span>
                  <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                    selectedTemplate.is_active === 'true'
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}>
                    {selectedTemplate.is_active === 'true' ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowPreview(false)
                  setSelectedTemplate(null)
                }}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100"
                aria-label="Close preview"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden bg-gray-50">
              {selectedTemplate.template_file_path ? (
                <TemplateDocxViewer
                  key={selectedTemplate.id}
                  templateId={selectedTemplate.id}
                  templateName={selectedTemplate.template_name}
                />
              ) : (
                <div className="flex h-full items-center justify-center p-8 text-center">
                  <div>
                    <p className="text-gray-700 font-medium">No document file available</p>
                    <p className="text-sm text-gray-500 mt-2">
                      This template does not have an uploaded DOCX file to preview.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </ModalPortal>
      )}

      {/* Placeholder Configuration Modal */}
      {showConfigModal && configTemplate && (
        <ModalPortal>
          <div className="flex flex-col bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden">
            <div className="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-bold text-gray-900">
                Template Field Configuration
              </h3>
              <button
                type="button"
                onClick={() => {
                  setShowConfigModal(false)
                  setConfigTemplate(null)
                  setPlaceholderConfig({})
                }}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100"
                aria-label="Close configuration"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              <p className="text-sm text-gray-600 mb-4">
                Configure which placeholder fields are editable in agreements created from "{configTemplate.template_name}".
                Uncheck fields that should be locked and cannot be edited.
              </p>

              {Object.keys(placeholderConfig).length === 0 ? (
                <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
                  <p>No placeholders detected in this template.</p>
                  <p className="text-xs mt-2">Placeholders are automatically detected when templates are uploaded.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {Object.entries(placeholderConfig).map(([placeholderName, config]) => (
                    <div
                      key={placeholderName}
                      className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200"
                    >
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config.editable}
                          onChange={() => handleToggleEditable(placeholderName)}
                          className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                        />
                        <span className="text-sm font-medium text-gray-700">
                          {placeholderName.replace(/_/g, ' ')}
                        </span>
                      </label>
                      <span className={`text-xs px-2 py-1 rounded ${
                        config.editable
                          ? 'bg-green-100 text-green-800'
                          : 'bg-yellow-100 text-yellow-800'
                      }`}>
                        {config.editable ? 'Editable' : 'Locked'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex-shrink-0 flex gap-2 justify-end px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                type="button"
                onClick={() => {
                  setShowConfigModal(false)
                  setConfigTemplate(null)
                  setPlaceholderConfig({})
                }}
                disabled={savingConfig}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSavePlaceholderConfig}
                disabled={savingConfig || Object.keys(placeholderConfig).length === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
              >
                {savingConfig ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </ModalPortal>
      )}

      {/* Field Mappings Modal */}
      {showFieldMappingsModal && fieldMappingsTemplate && (
        <ModalPortal>
          <div className="flex flex-col bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden">
            <div className="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-bold text-gray-900">
                Dynamic Field Mapping
              </h3>
              <button
                type="button"
                onClick={() => {
                  setShowFieldMappingsModal(false)
                  setFieldMappingsTemplate(null)
                  setFieldMappings({})
                  setNewMappingPlaceholder('')
                  setNewMappingDataSource('site_profile')
                  setNewMappingField('')
                }}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100"
                aria-label="Close field mappings"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              <p className="text-sm text-gray-600 mb-4">
                Configure how placeholders in "{fieldMappingsTemplate.template_name}" map to data sources.
                When creating an agreement from this template, placeholders will be automatically replaced with values from Site Profile or Agreement.
              </p>

              {/* AI Suggestions banner */}
              {aiSuggestionsQuery.isLoading && (
                <div className="mb-4 flex items-center gap-2 text-xs text-gray-500">
                  <svg className="animate-spin h-3.5 w-3.5 text-blue-500 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Loading AI suggestions…
                </div>
              )}
              {!aiSuggestionsQuery.isLoading && !aiSuggestionsQuery.isError && unappliedAiSuggestions.length > 0 && (
                <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5">
                  <p className="text-xs text-blue-700">
                    AI found {unappliedAiSuggestions.length} suggested mapping{unappliedAiSuggestions.length !== 1 ? 's' : ''} for unmapped placeholders.
                  </p>
                  <button
                    type="button"
                    onClick={handleAcceptAllAiSuggestions}
                    className="shrink-0 rounded-md border border-blue-300 bg-white px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                  >
                    Accept all AI suggestions
                  </button>
                </div>
              )}

              {/* Add New Mapping Form */}
              <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Add New Mapping</h4>
                <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                  <div className="sm:col-span-3">
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      Placeholder
                    </label>
                    <select
                      value={newMappingPlaceholder}
                      onChange={(e) => setNewMappingPlaceholder(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white"
                    >
                      <option value="">Select placeholder</option>
                      {fieldMappingsTemplate?.placeholder_config &&
                        Object.keys(fieldMappingsTemplate.placeholder_config).sort().map((name) => (
                          <option key={name} value={name}>
                            {`{{${name}}}`}
                          </option>
                        ))}
                    </select>
                  </div>
                  <div className="sm:col-span-3">
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      Data Source
                    </label>
                    <select
                      value={newMappingDataSource}
                      onChange={(e) => setNewMappingDataSource(e.target.value as 'site_profile' | 'agreement')}
                      className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white"
                    >
                      <option value="site_profile">Site Profile</option>
                      <option value="agreement">Agreement</option>
                    </select>
                  </div>
                  <div className="sm:col-span-4">
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      Field Name
                    </label>
                    <select
                      value={newMappingField}
                      onChange={(e) => setNewMappingField(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white"
                    >
                      <option value="">Select field</option>
                      {mappingOptions[newMappingDataSource].map((opt) => (
                        <option key={opt.field} value={opt.field}>
                          {opt.label} ({opt.field})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="sm:col-span-2 flex items-end">
                    <button
                      type="button"
                      onClick={handleAddFieldMapping}
                      disabled={!newMappingPlaceholder || !newMappingField}
                      className="w-full px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                    >
                      Add
                    </button>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Example: Placeholder "SITE_NAME" → Site Profile → "site_name"
                </p>
              </div>

            {/* Existing Mappings */}
            <div className="mb-6">
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Current Mappings</h4>
              {Object.keys(fieldMappings).length === 0 ? (
                <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
                  <p>No field mappings configured.</p>
                  <p className="text-xs mt-2">Add mappings above to enable automatic placeholder replacement.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {Object.entries(fieldMappings).map(([placeholderName, mappingPath]) => {
                    const [dataSource, fieldName] = (mappingPath || '').split('.', 2)
                    const aiSuggestion = aiSuggestionsMap[placeholderName]
                    const isAiSuggested =
                      aiSuggestion != null &&
                      aiSuggestion.suggested_source === mappingPath
                    return (
                      <div
                        key={placeholderName}
                        className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200"
                      >
                        <div className="flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-gray-900">
                              {`{{${placeholderName}}}`}
                            </span>
                            <span className="text-gray-400">→</span>
                            <span className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded">
                              {dataSource}
                            </span>
                            <span className="text-gray-400">→</span>
                            <span className="text-sm text-gray-700">
                              {fieldName}
                            </span>
                            {isAiSuggested && (
                              <span
                                className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded"
                                title={aiSuggestion.reasoning}
                              >
                                AI suggested ({Math.round(aiSuggestion.confidence * 100)}%)
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => handleRemoveFieldMapping(placeholderName)}
                          className="ml-2 px-2 py-1 text-xs text-red-600 hover:text-red-800 hover:bg-red-50 rounded"
                        >
                          Remove
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Available Fields Reference */}
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
              <h4 className="text-sm font-semibold text-blue-900 mb-2">Available Fields</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div>
                  <p className="font-medium text-blue-800 mb-1">Site Profile:</p>
                  <ul className="text-blue-700 space-y-1">
                    <li>• site_name</li>
                    <li>• pi_name (principal_investigator)</li>
                    <li>• address_line_1</li>
                    <li>• city, state, country</li>
                    <li>• authorized_signatory_name</li>
                    <li>• authorized_signatory_email</li>
                  </ul>
                </div>
                <div>
                  <p className="font-medium text-blue-800 mb-1">Agreement:</p>
                  <ul className="text-blue-700 space-y-1">
                    <li>• title</li>
                  </ul>
                </div>
              </div>
            </div>
            </div>

            <div className="flex-shrink-0 flex gap-2 justify-end px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                type="button"
                onClick={() => {
                  setShowFieldMappingsModal(false)
                  setFieldMappingsTemplate(null)
                  setFieldMappings({})
                  setNewMappingPlaceholder('')
                  setNewMappingDataSource('site_profile')
                  setNewMappingField('')
                }}
                disabled={savingFieldMappings}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveFieldMappings}
                disabled={savingFieldMappings}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
              >
                {savingFieldMappings ? 'Saving...' : 'Save Mappings'}
              </button>
            </div>
          </div>
        </ModalPortal>
      )}
  </div>
  )
}

export default StudyTemplateLibrary
