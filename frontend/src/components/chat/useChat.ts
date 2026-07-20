import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { getConversation } from '../../lib/api/conversations'
import type { PersistedMessage } from '../../lib/api/types'
import { streamChatMessage } from '../../lib/sse/chatStream'
import { type DisplayCitation, fromPersistedCitation, fromSseCitation } from './citation'

export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: DisplayCitation[]
  refused?: boolean
  // Which generation provider actually answered (docs/plan.md Decisions
  // Register #4) -- null for user messages, refused answers, or while
  // still streaming (arrives with the `done` event).
  model?: string | null
  status: 'streaming' | 'done' | 'error'
  streamErrorMessage?: string
}

type HistoryStatus = 'idle' | 'loading' | 'ready' | 'error'

function toUiMessage(message: PersistedMessage): UiMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations.length > 0 ? message.citations.map(fromPersistedCitation) : undefined,
    refused: message.refused,
    model: message.model,
    status: 'done',
  }
}

/** Owns one conversation's message list: loading its persisted history
 * when `conversationId` changes, and driving a live send through the SSE
 * protocol documented in docs/phase-4.md. `send()` takes the conversation
 * id explicitly (rather than closing over the `conversationId` argument)
 * so a caller can create a conversation and send the first message to it
 * in the same action, before the id has round-tripped through routing. */
export function useChat(conversationId: string | undefined) {
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>('idle')
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  // Set by markConversationAsFresh() when *this client* just created a
  // conversation and is about to send its first message: the route param
  // changing to that new id would otherwise re-trigger the effect below
  // and GET a conversation we already know has no persisted history yet,
  // racing with (and potentially wiping) the optimistic messages send()
  // is about to add. Skipping the fetch for exactly that one transition
  // removes the race instead of trying to win it.
  const skipNextLoadRef = useRef<string | null>(null)

  const markConversationAsFresh = useCallback((id: string) => {
    skipNextLoadRef.current = id
  }, [])

  useEffect(() => {
    if (!conversationId) {
      abortControllerRef.current?.abort()
      setMessages([])
      setHistoryStatus('idle')
      return
    }

    if (skipNextLoadRef.current === conversationId) {
      // This id was just created by *this* client and send() is actively
      // streaming into it (see markConversationAsFresh) -- aborting here
      // would cancel that in-flight stream the instant navigate() lands,
      // since this effect re-runs the moment conversationId changes.
      skipNextLoadRef.current = null
      setHistoryStatus('ready')
      return
    }

    abortControllerRef.current?.abort()

    let cancelled = false
    setHistoryStatus('loading')
    setHistoryError(null)

    getConversation(conversationId)
      .then((detail) => {
        if (cancelled) return
        setMessages(detail.messages.map(toUiMessage))
        setHistoryStatus('ready')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setHistoryError(error instanceof ApiError ? error.message : 'Could not load this conversation.')
        setHistoryStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [conversationId])

  useEffect(() => () => abortControllerRef.current?.abort(), [])

  const send = useCallback(async (activeConversationId: string, content: string, provider?: string | null) => {
    const userMessage: UiMessage = {
      id: `local-user-${crypto.randomUUID()}`,
      role: 'user',
      content,
      status: 'done',
    }
    const assistantId = `local-assistant-${crypto.randomUUID()}`
    const assistantMessage: UiMessage = { id: assistantId, role: 'assistant', content: '', status: 'streaming' }

    setMessages((current) => [...current, userMessage, assistantMessage])
    setIsSending(true)

    const controller = new AbortController()
    abortControllerRef.current = controller

    const updateAssistant = (patch: Partial<UiMessage>) => {
      setMessages((current) => current.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)))
    }

    try {
      for await (const event of streamChatMessage(activeConversationId, content, {
        signal: controller.signal,
        provider,
      })) {
        if (event.type === 'citations') {
          updateAssistant({ citations: event.citations.map(fromSseCitation) })
        } else if (event.type === 'token') {
          setMessages((current) =>
            current.map((m) => (m.id === assistantId ? { ...m, content: m.content + event.delta } : m)),
          )
        } else if (event.type === 'done') {
          updateAssistant({ id: event.message_id, refused: event.refused, model: event.model, status: 'done' })
        } else if (event.type === 'error') {
          updateAssistant({ status: 'error', streamErrorMessage: event.error.message })
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof ApiError ? error.message : 'Could not send this message.'
        updateAssistant({ status: 'error', streamErrorMessage: message })
      }
    } finally {
      setIsSending(false)
    }
  }, [])

  return { messages, historyStatus, historyError, isSending, send, markConversationAsFresh }
}
