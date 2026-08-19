import React, { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import OnlyOfficeEditor, { type OnlyOfficeEditorHandle } from '@/components/OnlyOfficeEditor'

interface AgreementSignData {
  agreement: {
    id: string
    title: string
    status: string
  }
  site: {
    id: string | null
    site_id: string | null
    name: string | null
  }
  document: {
    id: string | null
    version_number: number | null
    document_file_path: string | null
  } | null
  token: string
  signer_email?: string | null
  role?: string | null
  can_sign_with_otp?: boolean
}

const AgreementSignPage: React.FC = () => {
  const pathParts = window.location.pathname.split('/')
  const agreementId = pathParts[pathParts.length - 1]
  const urlParams = new URLSearchParams(window.location.search)
  const token = urlParams.get('token')
  // Unified mode (?flow=unified): the SAME page, but OTP send + sign target the new
  // compliant unified endpoints (/agreements/{id}/sign/*) instead of the legacy CDA
  // OTP path. Default (no flag) is byte-for-byte the existing CDA behavior.
  const isUnified = urlParams.get('flow') === 'unified'
  const apiBase = (import.meta as any).env.VITE_API_BASE || '/api'

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [signData, setSignData] = useState<AgreementSignData | null>(null)
  const [showOtpModal, setShowOtpModal] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [signerName, setSignerName] = useState('')
  const [signerTitle, setSignerTitle] = useState('')
  // Signer-affirmed intent/meaning (unified compliant flow only).
  const [signerMeaning, setSignerMeaning] = useState('I approve and electronically sign this document')
  const [otpSending, setOtpSending] = useState(false)
  const [otpVerifying, setOtpVerifying] = useState(false)
  const [otpInfo, setOtpInfo] = useState<string | null>(null)
  const [otpCooldownSeconds, setOtpCooldownSeconds] = useState(0)
  const [success, setSuccess] = useState(false)
  const ooEditorRef = useRef<OnlyOfficeEditorHandle>(null)

  useEffect(() => {
    if (!agreementId || !token) {
      setError('Missing agreement ID or token')
      setLoading(false)
      return
    }

    const fetchData = async () => {
      try {
        const response = await axios.get(`${apiBase}/agreement/sign/${agreementId}`, {
          params: { token },
          headers: {},
        })
        setSignData(response.data)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load agreement')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [agreementId, token, apiBase])

  useEffect(() => {
    if (otpCooldownSeconds <= 0) return
    const timer = window.setTimeout(() => {
      setOtpCooldownSeconds((seconds) => Math.max(seconds - 1, 0))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [otpCooldownSeconds])

  const sendOtp = async () => {
    if (!agreementId || !token) return
    setOtpSending(true)
    setError(null)
    setOtpInfo(null)
    try {
      const response = isUnified
        ? await axios.post(`${apiBase}/agreements/${agreementId}/sign/request-otp`, { token })
        : await axios.post(`${apiBase}/auth/send-sign-otp`, { agreement_id: agreementId, token })
      setOtpCooldownSeconds(response.data.resend_cooldown_seconds || 30)
      setOtpInfo(`OTP sent to ${response.data.email || signData?.signer_email || 'your email'}.`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send OTP')
    } finally {
      setOtpSending(false)
    }
  }

  const openOtpFlow = async () => {
    setShowOtpModal(true)
    setOtpCode('')
    await sendOtp()
  }

  const handleSign = async () => {
    if (!agreementId || !token) return
    if (!signerName.trim()) {
      setError('Please enter your full name.')
      return
    }
    if (otpCode.trim().length !== 6) {
      setError('Enter the 6-digit OTP.')
      return
    }

    setOtpVerifying(true)
    setError(null)
    try {
      if (isUnified) {
        // New compliant unified path: verify code + record the manifested signature.
        await axios.post(`${apiBase}/agreements/${agreementId}/sign/submit`, {
          token,
          otp: otpCode.trim(),
          signer_name: signerName.trim(),
          signer_title: signerTitle.trim() || null,
          meaning: signerMeaning.trim() || undefined, // signer-affirmed intent
        })
      } else {
        await axios.post(`${apiBase}/agreement/sign`, {
          agreement_id: agreementId,
          token,
          otp: otpCode.trim(),
          signer_name: signerName.trim(),
          signer_title: signerTitle.trim() || null,
        })
      }
      setShowOtpModal(false)
      setSuccess(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to sign document')
    } finally {
      setOtpVerifying(false)
    }
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50 text-gray-600">Loading agreement...</div>
  }

  if (error && !signData) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50 text-red-700">{error}</div>
  }

  if (!signData) return null

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6 text-center">
          <div className="text-green-600 text-5xl mb-4">✓</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Document Signed</h1>
          <p className="text-gray-600">Your OTP signature has been recorded. You can close this page.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50" style={{ height: '100vh', overflowY: 'auto' }}>
      <div className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{signData.agreement.title}</h1>
            <p className="text-sm text-gray-600 mt-1">Site: {signData.site.name || signData.site.site_id || 'N/A'}</p>
          </div>
          <button
            onClick={openOtpFlow}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
          >
            Sign Document
          </button>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 pb-20">
        {error && <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">{error}</div>}
        <div className="bg-white shadow-sm rounded-lg overflow-hidden">
          <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Document Ready for Signature</h2>
              <p className="text-sm text-gray-600 mt-1">Version {signData.document?.version_number}</p>
            </div>
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-300">
              Read-Only Signing View
            </span>
          </div>
          <div className="p-4 bg-blue-50 border-b border-blue-200 text-sm text-blue-900">
            Review the document, then click <strong>Sign Document</strong>. OTP verification is required before your signature is applied.
          </div>
          <div
            className="flex flex-col min-h-0"
            style={{ height: 'calc(100vh - 220px)', minHeight: '480px' }}
          >
            {signData.document ? (
              <OnlyOfficeEditor
                ref={ooEditorRef}
                agreementId={signData.agreement.id}
                apiBase={apiBase}
                canEdit={false}
                publicSession
                editorContainerId={`onlyoffice-sign-${signData.agreement.id}`}
                configEndpoint={
                  signData.document.id
                    ? `/agreements/${signData.agreement.id}/onlyoffice-config?document_id=${signData.document.id}&token=${token}`
                    : `/agreements/${signData.agreement.id}/onlyoffice-config?version=${signData.document.version_number}&token=${token}`
                }
              />
            ) : (
              <div className="p-8 text-center text-gray-600">No document available for signing</div>
            )}
          </div>
        </div>
      </div>

      {showOtpModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Sign Document</h3>
            <p className="text-sm text-gray-600 mb-4">{otpInfo || `We will send an OTP to ${signData.signer_email || 'your email'}.`}</p>

            <label className="block text-xs font-medium text-gray-700 mb-1">
              Your Full Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
              placeholder="e.g. Dr. Jane Smith"
              className="w-full mb-3 px-3 py-2 border border-gray-300 rounded-lg"
            />

            <label className="block text-xs font-medium text-gray-700 mb-1">
              Title <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="text"
              value={signerTitle}
              onChange={(e) => setSignerTitle(e.target.value)}
              placeholder="e.g. Principal Investigator"
              className="w-full mb-3 px-3 py-2 border border-gray-300 rounded-lg"
            />

            {isUnified && (
              <>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Signing meaning / intent <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={signerMeaning}
                  onChange={(e) => setSignerMeaning(e.target.value)}
                  placeholder="e.g. I approve and electronically sign this document"
                  className="w-full mb-3 px-3 py-2 border border-gray-300 rounded-lg"
                />
              </>
            )}

            <label className="block text-xs font-medium text-gray-700 mb-1">
              One-Time Code <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              maxLength={6}
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg tracking-[0.4em] text-center text-lg"
              placeholder="000000"
            />
            <p className="text-xs text-gray-500 mt-1">
              Your typed name will be rendered as your signature on the document.
            </p>
            <div className="mt-4 flex items-center justify-between">
              <button
                type="button"
                onClick={sendOtp}
                disabled={otpSending || otpCooldownSeconds > 0}
                className="text-sm text-blue-700 disabled:text-gray-400"
              >
                {otpSending ? 'Sending...' : otpCooldownSeconds > 0 ? `Resend in ${otpCooldownSeconds}s` : 'Resend OTP'}
              </button>
              <div className="flex gap-2">
                <button onClick={() => setShowOtpModal(false)} className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg">Cancel</button>
                <button onClick={handleSign} disabled={otpVerifying} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
                  {otpVerifying ? 'Signing...' : 'Sign'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AgreementSignPage
