import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { useChat } from '../components/chat/useChat'
import { useModels } from '../components/chat/useModels'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { ApiError } from '../lib/api/client'
import type { ChatOutletContext } from '../App'

const PROVIDER_STORAGE_KEY = 'ragchatbot-selected-provider'

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const navigate = useNavigate()
  const { addConversation, refreshConversationTitle } = useOutletContext<ChatOutletContext>()
  const { messages, historyStatus, historyError, isSending, send, markConversationAsFresh } = useChat(conversationId)
  const [createError, setCreateError] = useState<string | null>(null)

  // Owned here (not inside Composer) so the same selected model applies
  // whether the next message comes from typing in the Composer or
  // clicking a MessageList sample question.
  const { models, status: modelsStatus } = useModels()
  const [provider, setProvider] = useState<string | null>(() => window.localStorage.getItem(PROVIDER_STORAGE_KEY))

  // Once real availability is known, make sure the selection is a real,
  // available model -- falls back to the backend's configured default
  // (or any available model) if there's no persisted choice, or the
  // persisted one is stale (unavailable, or no longer a known provider).
  useEffect(() => {
    if (modelsStatus !== 'ready' || models.length === 0) return
    const isValidChoice = provider !== null && models.some((m) => m.id === provider && m.available)
    if (isValidChoice) return
    const fallback = models.find((m) => m.is_default && m.available) ?? models.find((m) => m.available)
    if (fallback) {
      setProvider(fallback.id)
      window.localStorage.setItem(PROVIDER_STORAGE_KEY, fallback.id)
    }
  }, [modelsStatus, models, provider])

  function handleProviderChange(id: string) {
    setProvider(id)
    window.localStorage.setItem(PROVIDER_STORAGE_KEY, id)
  }

  async function handleSend(content: string) {
    setCreateError(null)
    let activeConversationId = conversationId

    if (!activeConversationId) {
      try {
        const created = await addConversation()
        activeConversationId = created.id
        markConversationAsFresh(created.id)
        navigate(`/c/${created.id}`, { replace: true })
      } catch (error) {
        setCreateError(error instanceof ApiError ? error.message : 'Could not start a new conversation.')
        return
      }
    }

    await send(activeConversationId, content, provider)
    // Backend auto-names an untitled conversation from its first question
    // once that question's stream finishes persisting (see
    // backend/app/services/chat.py's _derive_title) -- this is what
    // reflects that new title into the sidebar without a full page reload.
    void refreshConversationTitle(activeConversationId)
  }

  return (
    <div className="flex h-full flex-col">
      {createError ? (
        <div className="px-6 pt-4">
          <ErrorBanner message={createError} onRetry={() => setCreateError(null)} />
        </div>
      ) : null}
      <div className="min-h-0 flex-1">
        <MessageList
          messages={messages}
          historyStatus={historyStatus}
          historyError={historyError}
          onSampleQuestion={(question) => void handleSend(question)}
        />
      </div>
      <Composer
        disabled={isSending}
        onSend={(content) => void handleSend(content)}
        models={models}
        provider={provider}
        onProviderChange={handleProviderChange}
      />
    </div>
  )
}
