export type ConnectionStatus = 'checking' | 'connected' | 'disconnected'

export interface ThreadSummary {
  thread_id: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface MessageMetadata {
  response_type?: 'answer' | 'refusal'
  source_url?: string | null
  source_title?: string | null
  last_updated?: string | null
  educational_link?: EducationalLink | null
}

export interface MessageRecord {
  message_id: string
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  metadata: MessageMetadata
  created_at: string
}

export interface EducationalLink {
  label: string
  url: string
}

export interface ChatResponse {
  thread_id: string
  answer: string
  source_url: string | null
  source_title: string | null
  last_updated: string | null
  response_type: 'answer' | 'refusal'
  educational_link: EducationalLink | null
  chunk_ids: string[]
}
