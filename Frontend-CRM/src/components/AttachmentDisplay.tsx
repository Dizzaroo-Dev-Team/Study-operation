import React, { useState } from 'react'
import { api } from '../lib/api'
import { Attachment } from '../types'

interface AttachmentDisplayProps {
  attachment: Attachment
  apiBase: string
  isOutbound?: boolean
}

const AttachmentDisplay: React.FC<AttachmentDisplayProps> = ({
  attachment,
  apiBase,
  isOutbound = false
}) => {
  const [downloading, setDownloading] = useState(false)

  const getFileIcon = (contentType: string, fileName?: string): string => {
    const ext = fileName?.split('.').pop()?.toLowerCase() || ''

    if (contentType.startsWith('image/')) return '🖼️'
    if (contentType.startsWith('video/')) return '🎥'
    if (contentType.startsWith('audio/')) return '🎵'
    if (contentType.includes('pdf')) return '📄'
    if (contentType.includes('word') || ext === 'doc' || ext === 'docx') return '📝'
    if (contentType.includes('excel') || ext === 'xls' || ext === 'xlsx') return '📊'
    if (contentType.includes('powerpoint') || ext === 'ppt' || ext === 'pptx') return '📽️'
    if (ext === 'zip' || ext === 'rar' || ext === '7z') return '📦'
    if (ext === 'txt') return '📋'
    return '📎'
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleDownload = async () => {
    if (downloading) return

    try {
      setDownloading(true)

      const response = await api.get(
        `${apiBase}/attachments/${attachment.id}/download`,
        {
          responseType: 'blob'
        }
      )

      const blob = new Blob([response.data])
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url

      const contentDisposition = response.headers['content-disposition']
      let fileName =
        attachment.file_name ||
        attachment.file_path.split('/').pop() ||
        'download'

      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename="?(.+)"?/i)
        if (fileNameMatch && fileNameMatch[1]) {
          fileName = fileNameMatch[1]
        }
      }

      link.download = fileName
      document.body.appendChild(link)
      link.click()

      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error: any) {
      console.error('Failed to download file:', error)
      alert(
        error.response?.data?.detail ||
          'Failed to download file. Please try again.'
      )
    } finally {
      setDownloading(false)
    }
  }

  const fileName =
    attachment.file_name || attachment.file_path.split('/').pop() || 'File'


  return (
    <div 
      className={`mt-2 p-3 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md ${
        isOutbound 
          ? 'bg-white/20 border-white/30 hover:bg-white/30' 
          : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
      }`}
      onClick={handleDownload}
    >
      <div className="flex items-center gap-3">
        <div className={`text-3xl flex-shrink-0 ${isOutbound ? 'text-white' : 'text-gray-600'}`}>
          {getFileIcon(attachment.content_type, fileName)}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`font-semibold text-sm truncate ${isOutbound ? 'text-white' : 'text-gray-800'}`}>
            {fileName}
          </div>
          <div className={`text-xs mt-0.5 ${isOutbound ? 'text-white/70' : 'text-gray-500'}`}>
            {formatFileSize(attachment.size)} • {attachment.content_type.split('/')[1]?.toUpperCase() || 'FILE'}
          </div>
        </div>
        <div className={`text-lg flex-shrink-0 ${isOutbound ? 'text-white/70' : 'text-gray-400'} ${downloading ? 'animate-pulse' : ''}`}>
          {downloading ? '⏳' : '⬇️'}
        </div>
      </div>
    </div>
  )
}

export default AttachmentDisplay

