import { apiFetch } from './client'
import type { ConversationDetail, ConversationSummary } from './types'

export function listConversations(): Promise<ConversationSummary[]> {
  return apiFetch<ConversationSummary[]>('/conversations')
}

export function createConversation(title?: string | null): Promise<ConversationSummary> {
  return apiFetch<ConversationSummary>('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title ?? null }),
  })
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/conversations/${conversationId}`)
}

export function deleteConversation(conversationId: string): Promise<void> {
  return apiFetch<void>(`/conversations/${conversationId}`, { method: 'DELETE' })
}
