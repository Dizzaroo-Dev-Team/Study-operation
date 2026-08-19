import React, { useMemo, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import {
  useUserEvents,
  useUserIisStudies,
  useUserProfile,
  useUserPublicInfo,
  useUserRdStudies,
} from '@/lib/queries/useProfile'

interface ProfileProps {
  apiBase: string
  onBack?: () => void
  userId?: string
}

interface UserProfile {
  id: string
  user_id: string
  name?: string
  address?: string
  phone?: string
  email?: string
  affiliation?: string
  specialty?: string
}

interface RDStudy {
  id: string
  study_title: string
  nct_number?: string
  asset?: string
  indication?: string
  enrollment?: number
  phases?: string
  start_date?: string
  completion_date?: string
}

interface IISStudy {
  id: string
  study_title: string
  asset?: string
  indication?: string
  phases?: string
  enrollment?: number
  enrollment_start_date?: string
  completion_date?: string
  other_associated_hcp_ids?: string[]
}

interface Event {
  id: string
  event_name: string
  internal_external: string
  event_type?: string
  date_of_event?: string
  event_description?: string
  event_report?: string
  relevant_internal_stakeholders?: string[]
}

interface ResearchPaper {
  title: string
  link: string
  snippet: string
  source?: string
  relatedStudy?: string | null
}

const Profile: React.FC<ProfileProps> = ({ onBack, userId }) => {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'basic' | 'rd' | 'iis' | 'events' | 'public'>('basic')

  const targetUserId = userId || user?.user_id || ''
  const enabled = Boolean(targetUserId)

  // Distinguish "lookup by id" (Profile viewing someone else) from "self"
  // (the authed user's own profile). The hook layer picks the right URL.
  const lookupId = userId ?? null

  const profileQuery = useUserProfile(lookupId, { enabled })
  const rdQuery = useUserRdStudies(lookupId, { enabled })
  const iisQuery = useUserIisStudies(lookupId, { enabled })
  const eventsQuery = useUserEvents(lookupId, { enabled })

  const profile: UserProfile | null = (profileQuery.data ?? null) as UserProfile | null
  const rdStudies: RDStudy[] = (rdQuery.data ?? []) as RDStudy[]
  const iisStudies: IISStudy[] = (iisQuery.data ?? []) as IISStudy[]
  const events: Event[] = (eventsQuery.data ?? []) as Event[]

  // Derive the search query the legacy code built from the profile fields.
  // Empty string means "no searchable info" and the query stays disabled.
  const publicSearchQuery = useMemo(() => {
    if (!profile) return ''
    const terms = [profile.name, profile.affiliation, profile.specialty]
      .filter((t): t is string => Boolean(t && t.trim()))
    const unique = [...new Set(terms)]
    return unique.join(' ')
  }, [profile])

  const publicInfoEnabled =
    activeTab === 'public' &&
    Boolean(targetUserId) &&
    Boolean(profile) &&
    publicSearchQuery.length > 0

  const papersQuery = useUserPublicInfo(lookupId, publicSearchQuery, {
    enabled: publicInfoEnabled,
  })
  const papers: ResearchPaper[] = papersQuery.data ?? []
  const loadingPapers = publicInfoEnabled && papersQuery.isFetching

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A'
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    })
  }


      return (
        <div className="h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col overflow-hidden">
          <div className="max-w-7xl mx-auto w-full flex flex-col h-full p-6">
            {/* Header */}
            <div className="bg-white rounded-xl shadow-lg p-6 mb-6 flex-shrink-0">
              <div className="flex justify-between items-center">
                <div>
                  <h1 className="text-3xl font-bold text-gray-800 mb-2">👤 User Profile</h1>
                  <p className="text-gray-600">View user profile information, studies, events, and research</p>
                  {userId && profile?.name && (
                    <p className="text-sm text-gray-500 mt-1">Viewing profile for: <span className="font-semibold">{profile.name}</span></p>
                  )}
                </div>
                {onBack && (
                  <button
                    onClick={onBack}
                    className="px-5 py-2.5 bg-dizzaroo-deep-blue text-white rounded-xl hover:bg-dizzaroo-blue-green font-semibold transition shadow-lg"
                  >
                    ← Back to Inbox
                  </button>
                )}
              </div>
            </div>

        {/* Tabs */}
        <div className="bg-white rounded-xl shadow-lg mb-6 flex-shrink-0">
          <div className="flex border-b border-gray-200 overflow-x-auto">
            {[
              { id: 'basic', label: 'Basic Details', icon: '👤' },
              { id: 'rd', label: 'R&D Studies', icon: '🔬' },
              { id: 'iis', label: 'IIS Studies', icon: '📊' },
              { id: 'events', label: 'Events', icon: '📅' },
              { id: 'public', label: 'Public Info', icon: '🔍' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-6 py-4 font-semibold text-sm transition-all whitespace-nowrap ${
                  activeTab === tab.id
                        ? 'text-dizzaroo-deep-blue border-b-2 border-dizzaroo-deep-blue bg-dizzaroo-deep-blue/10'
                        : 'text-gray-600 hover:text-dizzaroo-deep-blue hover:bg-gray-50'
                }`}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Basic Details Tab */}
        {activeTab === 'basic' && (
          <div className="bg-white rounded-xl shadow-lg p-6 flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex justify-between items-center mb-6 flex-shrink-0">
              <h2 className="text-2xl font-bold text-gray-800">Basic Details</h2>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0" style={{ WebkitOverflowScrolling: 'touch' }}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pr-2">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Name</label>
                <p className="text-gray-800">{profile?.name || 'N/A'}</p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Email</label>
                <p className="text-gray-800">{profile?.email || 'N/A'}</p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Phone</label>
                <p className="text-gray-800">{profile?.phone || 'N/A'}</p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Affiliation</label>
                <p className="text-gray-800">{profile?.affiliation || 'N/A'}</p>
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-2">Address</label>
                <p className="text-gray-800">{profile?.address || 'N/A'}</p>
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-semibold text-gray-700 mb-2">Specialty</label>
                <p className="text-gray-800">{profile?.specialty || 'N/A'}</p>
              </div>
              </div>
            </div>
          </div>
        )}

        {/* R&D Studies Tab */}
        {activeTab === 'rd' && (
          <div className="bg-white rounded-xl shadow-lg p-6 flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex justify-between items-center mb-6 flex-shrink-0">
              <h2 className="text-2xl font-bold text-gray-800">R&D Studies</h2>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0" style={{ WebkitOverflowScrolling: 'touch' }}>
              {rdStudies.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p className="text-lg">No R&D studies available.</p>
                </div>
              ) : (
                <div className="space-y-4 pr-2">
                {rdStudies.map(study => (
                  <div key={study.id} className="border-2 border-gray-200 rounded-lg p-6 hover:shadow-md transition">
                    <div className="flex justify-between items-start mb-4">
                      <h3 className="text-xl font-bold text-gray-800">{study.study_title}</h3>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="font-semibold text-gray-600">NCT Number:</span>
                        <p className="text-gray-800">{study.nct_number || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Asset:</span>
                        <p className="text-gray-800">{study.asset || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Indication:</span>
                        <p className="text-gray-800">{study.indication || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Enrollment:</span>
                        <p className="text-gray-800">{study.enrollment || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Phases:</span>
                        <p className="text-gray-800">{study.phases || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Start Date:</span>
                        <p className="text-gray-800">{formatDate(study.start_date)}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Completion Date:</span>
                        <p className="text-gray-800">{formatDate(study.completion_date)}</p>
                      </div>
                    </div>
                  </div>
                ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* IIS Studies Tab */}
        {activeTab === 'iis' && (
          <div className="bg-white rounded-xl shadow-lg p-6 flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex justify-between items-center mb-6 flex-shrink-0">
              <h2 className="text-2xl font-bold text-gray-800">IIS Studies</h2>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0" style={{ WebkitOverflowScrolling: 'touch' }}>
              {iisStudies.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p className="text-lg">No IIS studies available.</p>
                </div>
              ) : (
                <div className="space-y-4 pr-2">
                {iisStudies.map(study => (
                  <div key={study.id} className="border-2 border-gray-200 rounded-lg p-6 hover:shadow-md transition">
                    <div className="flex justify-between items-start mb-4">
                      <h3 className="text-xl font-bold text-gray-800">{study.study_title}</h3>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="font-semibold text-gray-600">Asset:</span>
                        <p className="text-gray-800">{study.asset || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Indication:</span>
                        <p className="text-gray-800">{study.indication || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Phases:</span>
                        <p className="text-gray-800">{study.phases || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Enrollment:</span>
                        <p className="text-gray-800">{study.enrollment || 'N/A'}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Enrollment Start:</span>
                        <p className="text-gray-800">{formatDate(study.enrollment_start_date)}</p>
                      </div>
                      <div>
                        <span className="font-semibold text-gray-600">Completion Date:</span>
                        <p className="text-gray-800">{formatDate(study.completion_date)}</p>
                      </div>
                      {study.other_associated_hcp_ids && study.other_associated_hcp_ids.length > 0 && (
                        <div className="md:col-span-2">
                          <span className="font-semibold text-gray-600">Other HCP IDs:</span>
                          <p className="text-gray-800">{study.other_associated_hcp_ids.join(', ')}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Events Tab */}
        {activeTab === 'events' && (
          <div className="bg-white rounded-xl shadow-lg p-6 flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex justify-between items-center mb-6 flex-shrink-0">
              <h2 className="text-2xl font-bold text-gray-800">Events</h2>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0" style={{ WebkitOverflowScrolling: 'touch' }}>
              {events.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p className="text-lg">No events available.</p>
                </div>
              ) : (
                <div className="space-y-4 pr-2">
                {events.map(event => (
                  <div key={event.id} className="border-2 border-gray-200 rounded-lg p-6 hover:shadow-md transition">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h3 className="text-xl font-bold text-gray-800">{event.event_name}</h3>
                        <div className="flex gap-2 mt-2">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${
                            event.internal_external === 'Internal' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'
                          }`}>
                            {event.internal_external}
                          </span>
                          {event.event_type && (
                            <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs font-bold">
                              {event.event_type}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="space-y-2 text-sm">
                      {event.date_of_event && (
                        <div>
                          <span className="font-semibold text-gray-600">Date:</span>
                          <p className="text-gray-800">{formatDate(event.date_of_event)}</p>
                        </div>
                      )}
                      {event.event_description && (
                        <div>
                          <span className="font-semibold text-gray-600">Description:</span>
                          <p className="text-gray-800">{event.event_description}</p>
                        </div>
                      )}
                      {event.event_report && (
                        <div>
                          <span className="font-semibold text-gray-600">Report:</span>
                          <p className="text-gray-800 whitespace-pre-wrap">{event.event_report}</p>
                        </div>
                      )}
                      {event.relevant_internal_stakeholders && event.relevant_internal_stakeholders.length > 0 && (
                        <div>
                          <span className="font-semibold text-gray-600">Stakeholders:</span>
                          <p className="text-gray-800">{event.relevant_internal_stakeholders.join(', ')}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Public Info Tab */}
        {activeTab === 'public' && (
          <div className="bg-white rounded-xl shadow-lg p-6 flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex justify-between items-center mb-6 flex-shrink-0">
              <h2 className="text-2xl font-bold text-gray-800">Public Info - Research Papers</h2>
              <button
                onClick={() => void papersQuery.refetch()}
                disabled={loadingPapers}
                className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl hover:bg-dizzaroo-blue-green transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loadingPapers ? (
                  <>
                    <span className="animate-spin">⏳</span>
                    <span>Loading...</span>
                  </>
                ) : (
                  <>
                    <span>🔄</span>
                    <span>Refresh</span>
                  </>
                )}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0" style={{ WebkitOverflowScrolling: 'touch' }}>
              {loadingPapers && (
                <div className="text-center py-12">
                  <div className="animate-spin text-4xl mb-4">⏳</div>
                  <p className="text-gray-600">Loading research papers related to your studies...</p>
                </div>
              )}

              {!loadingPapers && papers.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <p className="text-lg mb-2">No research papers found.</p>
                  <p className="text-sm">Fill in your Basic Details (Name, Affiliation, Specialty) to automatically see your research papers and publications.</p>
                </div>
              )}

              {!loadingPapers && papers.length > 0 && (
                <div className="space-y-4 pr-2">
                  <div className="mb-4 p-3 bg-dizzaroo-deep-blue/10 border-2 border-dizzaroo-deep-blue/20 rounded-xl">
                    <p className="text-sm text-dizzaroo-deep-blue font-semibold">
                      📚 Found {papers.length} research paper{papers.length !== 1 ? 's' : ''} related to {profile?.name || 'your profile'}
                    </p>
                  </div>
                  {papers.map((paper, index) => (
                    <div key={index} className="border-2 border-gray-200 rounded-lg p-6 hover:shadow-md transition">
                      <h3 className="text-lg font-bold text-dizzaroo-deep-blue mb-2">
                        <a href={paper.link} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {paper.title}
                        </a>
                      </h3>
                      {paper.source && (
                        <p className="text-sm text-gray-500 mb-2">Source: {paper.source}</p>
                      )}
                      <p className="text-gray-700 mb-3">{paper.snippet}</p>
                      <a
                        href={paper.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-dizzaroo-deep-blue hover:text-dizzaroo-blue-green text-sm font-medium inline-flex items-center gap-1"
                      >
                        <span>Read full paper</span>
                        <span>→</span>
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}

export default Profile

