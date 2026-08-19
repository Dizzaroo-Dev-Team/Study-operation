import React, { useEffect, useMemo, useState } from 'react'
import {
  FeasibilityFormData,
  FeasibilityQuestion,
  useFeasibilityForm,
  useSubmitFeasibility,
} from '@/lib/queries/useFeasibility'

const FeasibilityForm: React.FC = () => {
  // Get token from URL query parameters
  const token = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('token')
  }, [])

  const [localError, setLocalError] = useState<string | null>(
    token ? null : 'Missing token parameter',
  )
  const [success, setSuccess] = useState(false)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const formQuery = useFeasibilityForm(token)
  const submitMutation = useSubmitFeasibility()

  const loading = Boolean(token) && formQuery.isLoading
  const submitting = submitMutation.isPending
  const formData: FeasibilityFormData | null = formQuery.data ?? null

  // Seed the answers map exactly once when the form payload arrives, then
  // surface a "no questions" error if the server returned an empty list.
  useEffect(() => {
    if (!formQuery.isSuccess || !formQuery.data) return
    if (!formQuery.data.questions || formQuery.data.questions.length === 0) {
      setLocalError(
        'No questions found for this feasibility form. Please contact the study team.',
      )
      return
    }
    const initialAnswers: Record<string, string> = {}
    formQuery.data.questions.forEach((q, idx) => {
      const answerKey = q.text && q.text.trim() ? q.text : `question-${idx}`
      initialAnswers[answerKey] = ''
    })
    setAnswers(initialAnswers)
  }, [formQuery.isSuccess, formQuery.data])

  const fetchError = useMemo(() => {
    if (!formQuery.isError) return null
    const err = formQuery.error as any
    return err?.response?.data?.detail || err?.message || 'Failed to load form'
  }, [formQuery.isError, formQuery.error])
  const error = localError ?? fetchError

  const handleAnswerChange = (questionText: string, value: string, questionIndex?: number) => {
    // Use question text as key, but fallback to index if text is empty
    const answerKey = questionText && questionText.trim() ? questionText : `question-${questionIndex}`
    setAnswers({
      ...answers,
      [answerKey]: value
    })
  }

  const validateForm = (): boolean => {
    if (!formData) return false
    
    for (let idx = 0; idx < formData.questions.length; idx++) {
      const question = formData.questions[idx]
      const answerKey = question.text && question.text.trim() ? question.text : `question-${idx}`
      const answer = answers[answerKey]
      if (!answer || answer.trim() === '') {
        const questionLabel = question.text || `Question ${idx + 1}`
        setLocalError(`Please answer: ${questionLabel}`)
        return false
      }
    }
    
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData || !token) return
    
    if (!validateForm()) {
      return
    }

    setLocalError(null)
    try {
      await submitMutation.mutateAsync({
        token,
        answers: formData.questions.map((q, idx) => {
          const answerKey = q.text && q.text.trim() ? q.text : `question-${idx}`
          return {
            question_text: q.text || `Question ${idx + 1}`,
            question_id: q.id || null,
            answer: answers[answerKey] || '',
            section: q.section || null,
          }
        }),
      })
      setSuccess(true)
    } catch (err: any) {
      setLocalError(err.response?.data?.detail || err.message || 'Failed to submit form')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading form...</p>
        </div>
      </div>
    )
  }

  if (error && !formData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6">
          <div className="text-center">
            <div className="text-red-600 text-4xl mb-4">⚠️</div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Error</h2>
            <p className="text-gray-600">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6">
          <div className="text-center">
            <div className="text-green-600 text-4xl mb-4">✓</div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Form Submitted Successfully</h2>
            <p className="text-gray-600">
              Thank you for completing the feasibility form. Your responses have been received.
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!formData) {
    return null
  }

  // Check if questions exist
  if (!formData.questions || formData.questions.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Feasibility Form</h1>
            <p className="text-gray-600 mb-4">
              <strong>Study:</strong> {formData.study_name}
            </p>
            <p className="text-gray-600 mb-4">
              <strong>Site:</strong> {formData.site_name}
            </p>
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mt-4">
              <p className="text-yellow-800">
                No questions found for this feasibility form. Please contact the study team.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Group questions by section
  const groupedQuestions: Record<string, FeasibilityQuestion[]> = {}
  const ungroupedQuestions: FeasibilityQuestion[] = []

  formData.questions.forEach((q) => {
    if (q.section) {
      if (!groupedQuestions[q.section]) {
        groupedQuestions[q.section] = []
      }
      groupedQuestions[q.section].push(q)
    } else {
      ungroupedQuestions.push(q)
    }
  })

  return (
    <div className="min-h-screen bg-gray-50 py-8 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4">
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Feasibility Form</h1>
          <p className="text-gray-600">
            <strong>Study:</strong> {formData.study_name}
          </p>
          <p className="text-gray-600">
            <strong>Site:</strong> {formData.site_name}
          </p>
          {formData.protocol_synopsis && (
            <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-blue-900 mb-1">Protocol Synopsis</h3>
                  <p className="text-sm text-blue-700">{formData.protocol_synopsis.file_name}</p>
                  <p className="text-xs text-blue-600 mt-1">
                    {(formData.protocol_synopsis.size / 1024).toFixed(2)} KB
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (!formData.protocol_synopsis || !token) return
                    const downloadUrl = `/api/feasibility-attachments/${formData.protocol_synopsis.study_site_id}/download?token=${token}`
                    window.open(downloadUrl, '_blank')
                  }}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Download
                </button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-lg p-6 max-h-[calc(100vh-300px)] overflow-y-auto">
          {/* Grouped questions */}
          {Object.entries(groupedQuestions).map(([section, questions]) => (
            <div key={section} className="mb-8">
              <h2 className="text-lg font-semibold text-gray-900 mb-4 pb-2 border-b border-gray-200">
                {section}
              </h2>
              <div className="space-y-6">
                {questions.map((question, idx) => {
                  const questionKey = question.id || `q-${section}-${idx}`
                  const inputName = `question-${questionKey}`
                  const answerKey = question.text && question.text.trim() ? question.text : `question-${idx}`
                  const questionText = question.text && question.text.trim() ? question.text : `Question ${idx + 1}`
                  
                  return (
                    <div key={questionKey} className="space-y-2">
                      <label htmlFor={inputName} className="block text-sm font-medium text-gray-700">
                        {questionText}
                        <span className="text-red-500 ml-1">*</span>
                      </label>
                      {question.type === 'yes_no' ? (
                        <div className="flex gap-4">
                          <label className="flex items-center">
                            <input
                              type="radio"
                              name={inputName}
                              id={`${inputName}-yes`}
                              value="yes"
                              checked={answers[answerKey] === 'yes'}
                              onChange={(e) => handleAnswerChange(question.text, e.target.value, idx)}
                              className="mr-2"
                              required
                            />
                            Yes
                          </label>
                          <label className="flex items-center">
                            <input
                              type="radio"
                              name={inputName}
                              id={`${inputName}-no`}
                              value="no"
                              checked={answers[answerKey] === 'no'}
                              onChange={(e) => handleAnswerChange(question.text, e.target.value, idx)}
                              className="mr-2"
                              required
                            />
                            No
                          </label>
                        </div>
                      ) : question.type === 'number' ? (
                        <input
                          type="number"
                          id={inputName}
                          name={inputName}
                          value={answers[answerKey] || ''}
                          onChange={(e) => handleAnswerChange(question.text, e.target.value, idx)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        />
                      ) : (
                        <textarea
                          id={inputName}
                          name={inputName}
                          value={answers[answerKey] || ''}
                          onChange={(e) => handleAnswerChange(question.text, e.target.value, idx)}
                          rows={4}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}

          {/* Ungrouped questions */}
          {ungroupedQuestions.length > 0 && (
            <div className="mb-8">
              {ungroupedQuestions.map((question, idx) => {
                const questionKey = question.id || `q-ungrouped-${idx}`
                const inputName = `question-${questionKey}`
                // Calculate the actual index in the full questions array
                const actualIdx = formData.questions.findIndex(q => q === question)
                const answerKey = question.text && question.text.trim() ? question.text : `question-${actualIdx >= 0 ? actualIdx : idx}`
                const questionText = question.text && question.text.trim() ? question.text : `Question ${idx + 1}`
                
                return (
                  <div key={questionKey} className="mb-6 space-y-2">
                    <label htmlFor={inputName} className="block text-sm font-medium text-gray-700">
                      {questionText}
                      <span className="text-red-500 ml-1">*</span>
                    </label>
                    {question.type === 'yes_no' ? (
                      <div className="flex gap-4">
                        <label className="flex items-center">
                          <input
                            type="radio"
                            name={inputName}
                            id={`${inputName}-yes`}
                            value="yes"
                            checked={answers[answerKey] === 'yes'}
                            onChange={(e) => handleAnswerChange(question.text, e.target.value, actualIdx >= 0 ? actualIdx : idx)}
                            className="mr-2"
                            required
                          />
                          Yes
                        </label>
                        <label className="flex items-center">
                          <input
                            type="radio"
                            name={inputName}
                            id={`${inputName}-no`}
                            value="no"
                            checked={answers[answerKey] === 'no'}
                            onChange={(e) => handleAnswerChange(question.text, e.target.value, actualIdx >= 0 ? actualIdx : idx)}
                            className="mr-2"
                            required
                          />
                          No
                        </label>
                      </div>
                    ) : question.type === 'number' ? (
                      <input
                        type="number"
                        id={inputName}
                        name={inputName}
                        value={answers[answerKey] || ''}
                        onChange={(e) => handleAnswerChange(question.text, e.target.value, actualIdx >= 0 ? actualIdx : idx)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        required
                      />
                    ) : (
                      <textarea
                        id={inputName}
                        name={inputName}
                        value={answers[answerKey] || ''}
                        onChange={(e) => handleAnswerChange(question.text, e.target.value, actualIdx >= 0 ? actualIdx : idx)}
                        rows={4}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        required
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex justify-end gap-4 pt-6 border-t border-gray-200">
            <button
              type="submit"
              disabled={submitting}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? 'Submitting...' : 'Submit Form'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default FeasibilityForm
