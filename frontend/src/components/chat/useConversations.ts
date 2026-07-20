import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { createConversation, deleteConversation, getConversation, listConversations } from '../../lib/api/conversations'
import type { ConversationSummary } from '../../lib/api/types'

type Status = 'loading' | 'ready' | 'error'

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    // Explicitly set (not just via useRef's initializer) so this survives
    // React 18/19 Strict Mode's dev-only double-invoke: the throwaway first
    // mount's cleanup flips this to false, and without resetting it here on
    // the real mount, every subsequent fetch().then() would see `false`
    // forever and silently skip its setStatus call -- freezing the UI at
    // its initial "loading" state even though the request succeeded.
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(() => {
    setStatus('loading')
    setErrorMessage(null)
    listConversations()
      .then((data) => {
        if (mountedRef.current) {
          setConversations(data)
          setStatus('ready')
        }
      })
      .catch((error: unknown) => {
        if (mountedRef.current) {
          setErrorMessage(error instanceof ApiError ? error.message : 'Could not load conversations.')
          setStatus('error')
        }
      })
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const addConversation = useCallback(async (title?: string | null) => {
    const created = await createConversation(title)
    if (mountedRef.current) {
      setConversations((current) => [created, ...current])
    }
    return created
  }, [])

  const removeConversation = useCallback(async (conversationId: string) => {
    await deleteConversation(conversationId)
    if (mountedRef.current) {
      setConversations((current) => current.filter((conversation) => conversation.id !== conversationId))
    }
  }, [])

  // Backend auto-names an untitled conversation from its first question
  // (app/services/chat.py's _derive_title, set once the first message's
  // stream completes). Re-fetches just that one conversation's fresh
  // title rather than the whole list -- and skips the network call
  // entirely once we already know it has a title, so this is a no-op on
  // every message after the first, not a fetch on every single turn.
  const refreshConversationTitle = useCallback(
    async (conversationId: string) => {
      const alreadyTitled = conversations.some((c) => c.id === conversationId && c.title !== null)
      if (alreadyTitled) return

      const detail = await getConversation(conversationId)
      if (mountedRef.current) {
        setConversations((current) => current.map((c) => (c.id === conversationId ? { ...c, title: detail.title } : c)))
      }
    },
    [conversations],
  )

  return { conversations, status, errorMessage, refresh, addConversation, removeConversation, refreshConversationTitle }
}
