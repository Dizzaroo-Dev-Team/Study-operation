import { api } from '@/lib/api'

export type ISFFolderNode = {
  folder_id: string
  folder_type: 'zone' | 'section' | 'artifact' | 'subartifact'
  folder_name: string
  folder_number?: string | null
  document_count?: number
  subfolders: ISFFolderNode[]
}

export type ISFDocumentListItem = {
  id: string
  title: string
  mime_type?: string | null
  file_url?: string | null
  file_size?: number | null
  modification_date?: string | null
  version?: number | string | null
}

export type ISFImportItem = {
  id: string
  title: string
  mime_type?: string | null
  url: string
}

export const isfBrowserService = {
  async getFolders(): Promise<ISFFolderNode[]> {
    const res = await api.get('/isf/folders')
    return (res.data || []) as ISFFolderNode[]
  },

  async getDocuments(folderId: string): Promise<ISFDocumentListItem[]> {
    const res = await api.get('/isf/documents', { params: { folder_id: folderId } })
    return (res.data || []) as ISFDocumentListItem[]
  },

  async importDocuments(documentIds: string[]): Promise<ISFImportItem[]> {
    const res = await api.post('/isf/import', { document_ids: documentIds })
    return ((res.data || {}).documents || []) as ISFImportItem[]
  },
}

