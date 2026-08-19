export interface Conversation {
  id: string
  participant_phone?: string
  participant_email?: string  // Primary/legacy email for backward compatibility
  participant_emails?: string[]  // Array of email addresses for multiple recipients
  subject?: string
  title?: string
  study_id?: string
  site_id?: string
  tracker_code?: string
  is_restricted?: string
  is_confidential?: string
  is_pinned?: string
  conversation_type?: string  // 'notice_board' | 'thread' | …
  created_by?: string
  sponsor_id?: string
  access_level?: string
  privileged_users?: string[]
  created_at: string
  updated_at: string
  // AI auto‑classification & summary fields
  ai_category?: 'ops' | 'admission' | 'sales' | 'support' | 'other'
  ai_priority?: 'low' | 'medium' | 'high' | 'urgent'
  ai_sentiment?: 'negative' | 'neutral' | 'positive'
  ai_next_best_action?: string
  ai_summary?: string
  ai_summary_updated_at?: string
  // Phase-2 persisted operational state.
  status?: ConversationStatus | null
  owner_user_id?: string | null
  owner_name?: string | null
  due_at?: string | null
  priority?: ConversationPriority | null
  snooze_until?: string | null
  messages?: Message[]
}

export type ConversationStatus =
  | 'open'
  | 'awaiting_reply'   // we sent the last message, waiting on them
  | 'awaiting_us'      // they sent the last message, waiting on us
  | 'snoozed'
  | 'resolved'
  | 'closed'

export type ConversationPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface User {
  id: string
  user_id: string
  name?: string
  email?: string
  role: string
  is_privileged: string
  created_at: string
}

export interface ConversationAccess {
  id: string
  conversation_id: string
  user_id: string
  access_type: string
  granted_by?: string
  granted_at: string
}

export interface Message {
  id: string
  conversation_id?: string
  body: string
  metadata?: Record<string, any>
  channel: 'sms' | 'whatsapp' | 'email'
  direction: 'inbound' | 'outbound'
  status: 'queued' | 'sent' | 'delivered' | 'failed'
  author_id?: string
  author_name?: string
  mentioned_emails?: string[]
  // Explicit "decision of record" pin (server-backed, defaults false).
  is_decision?: boolean
  created_at: string
  sent_at?: string
  delivered_at?: string
  provider_message_id?: string
  // AI per‑message analysis
  ai_tone?: string
  ai_delta_summary?: string
  attachments?: Attachment[]
  // System-event fields used by the Public Notice Board renderer. Populated
  // by the backend hooks in `app/utils/system_notices.py` for activity
  // messages; absent on regular user messages. Kept optional so existing
  // call-sites stay unaffected.
  origin?: 'system' | 'user'
  event_type?: string
  is_activity_event?: boolean
}

export interface Attachment {
  id: string
  message_id?: string
  conversation_id: string
  file_path: string
  content_type: string
  size: number
  checksum?: string
  uploaded_at: string
  file_name?: string
}

export interface ThreadAttachment {
  id: string
  thread_id: string
  thread_message_id?: string
  attachment_id: string
  created_at: string
  attachment?: Attachment
}

export interface Thread {
  id: string
  conversation_id: string  // Required: all threads belong to a conversation
  title: string
  description?: string
  thread_type: 'general' | 'issue' | 'patient' | 'agreement'
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  related_patient_id?: string
  related_study_id?: string
  site_id?: string
  created_by?: string
  created_at: string
  updated_at: string
  participants?: ThreadParticipant[]
  participants_emails?: string[]  // List of participant email addresses for access control
  visibility_scope?: 'private' | 'site'  // 'private' or 'site' - controls thread visibility
  messages?: ThreadMessage[]
  tmf_filed?: boolean
  tmf_filed_at?: string
  conversation_address?: string
  agreement_type?: 'CDA' | 'CTA' | string
}

export interface ThreadParticipant {
  id: string
  thread_id: string
  participant_id: string
  participant_name?: string
  participant_email?: string
  role: 'creator' | 'participant' | 'assignee'
  joined_at: string
}

export interface ThreadMessage {
  id: string
  thread_id: string
  message_id?: string
  body: string
  author_id: string
  author_name?: string
  mentioned_emails?: string[]
  created_at: string
  attachments?: ThreadAttachment[]
  message_type?: 'system' | string
}

export interface Stats {
  total_conversations: number
  total_messages: number
  by_channel: Record<string, number>
  by_status: Record<string, number>
}

// Site Status interfaces
export type SiteStatusTaskStatus = 'completed' | 'in_progress' | 'not_started'

export interface SiteStatusTask {
  id: string
  name: string
  status: SiteStatusTaskStatus
}

export interface SiteStatusPhase {
  id: string
  name: string
  tasks: SiteStatusTask[]
}

export interface SiteStatus {
  studyId: string
  siteId: string
  phases: SiteStatusPhase[]
}

// Logistics interfaces
export interface SiteLogistics {
  id: string
  siteId: string
  siteName: string
  location?: string
  totalPatients: number
  activePatients: number
  completedPatients: number
  drugReceived: number
  drugUsed: number
  drugRemaining: number
  drugReorderThreshold?: number
  totalBudget?: number
  amountPaid?: number
  amountDue?: number
  lastPaymentDate?: string | Date
  isDrugLow?: boolean
}

// Monitoring interfaces
export interface MonitoringIssue {
  id: string
  siteId: string
  siteName: string
  detectedAt: string | Date
  sourceSystem: 'DATA_MONITORING_APP'
  category: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'in-progress' | 'resolved' | 'dismissed'
  patientId?: string
  formName?: string
}

export interface MonitoringChecklistItem {
  id: string
  visitId: string
  title: string
  description?: string
  sourceIssueId?: string
  status: 'pending' | 'in-progress' | 'done'
  note?: string
}

export interface MonitoringReport {
  id: string
  visitId: string
  siteId: string
  status: 'draft' | 'submitted' | 'approved' | 'needs-changes'
  overview: string
  dataQualityFindings: string
  protocolDeviations: string
  patientSafetyFindings: string
  otherNotes?: string
  createdByUserId?: string
  createdAt: string | Date
  submittedAt?: string | Date
  approvedAt?: string | Date
  approvedByUserId?: string
}

export interface MonitoringVisitNotes {
  visitId: string
  notes: string
  lastUpdatedAt: string | Date
}

export interface MonitoringVisit {
  id: string
  siteId: string
  siteName: string
  visitNumber: number
  plannedDate: string | Date
  actualDate?: string | Date
  craId?: string
  craName?: string
  status: 'planned' | 'in-progress' | 'report-pending' | 'submitted' | 'approved' | 'needs-changes'
  linkedIssueIds: string[]
  reportId?: string
  openActionItemsCount?: number
  carriedOverItemsCount?: number
  notes?: string
}

// Task Links - supports linking tasks to various entities
export interface TaskLinks {
  siteId?: string
  sponsorId?: string
  monitoringVisitId?: string
  monitoringReportId?: string
  conversationId?: string
  messageId?: string
}

// Task Status type
export type TaskStatus = 'open' | 'in-progress' | 'done' | 'cancelled'

// Task Mode type - where the task is performed
export type TaskMode = 'remote' | 'on-site'

// Task interface - unified task model for conversations and monitoring
export interface MonitoringTask {
  id: string
  title?: string
  description?: string
  status: TaskStatus
  assigneeId?: string
  assigneeName?: string
  requestedBy?: string
  assignedTo?: string
  sponsorId?: string
  sponsorName?: string
  role?: string
  taskMode?: TaskMode
  dueDate?: string | Date
  closedDate?: string | Date
  statusUpdate?: string
  createdAt: string | Date
  updatedAt?: string | Date
  createdByUserId?: string
  // Links to various entities
  links?: TaskLinks
  // Legacy fields for backward compatibility
  siteId?: string
  monitoringVisitId?: string
  monitoringReportId?: string
  sourceConversationId?: string
  carriedFromVisitId?: string
}
