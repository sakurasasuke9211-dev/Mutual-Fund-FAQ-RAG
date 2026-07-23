import type { ChatResponse, MessageRecord, ThreadSummary } from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001').replace(/\/$/, '')
// Railway first chat can load embedding/reranker models (~60s+); keep headroom.
const REQUEST_TIMEOUT_MS = 120_000

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })

    if (!response.ok) {
      let detail = ''
      try {
        const body = (await response.json()) as { detail?: string }
        detail = body.detail || ''
      } catch {
        // The status-specific message below is enough when the body is not JSON.
      }

      if (response.status === 404) throw new ApiError(detail || 'Conversation not found.', 404)
      if (response.status === 422) throw new ApiError(detail || 'Please check your question.', 422)
      if (response.status === 429) {
        throw new ApiError('Request limit reached. Please try again shortly.', 429)
      }
      throw new ApiError(detail || 'The service could not complete this request.', response.status)
    }

    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The request took too long. Please try again.')
    }
    throw new ApiError('Unable to reach the information service.')
  } finally {
    window.clearTimeout(timeout)
  }
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  listThreads: () => request<ThreadSummary[]>('/threads'),
  createThread: () =>
    request<{ thread_id: string; created_at: string }>('/threads', { method: 'POST' }),
  getMessages: (threadId: string) =>
    request<MessageRecord[]>(`/threads/${encodeURIComponent(threadId)}/messages`),
  chat: (threadId: string, query: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ thread_id: threadId, query }),
    }),
}
