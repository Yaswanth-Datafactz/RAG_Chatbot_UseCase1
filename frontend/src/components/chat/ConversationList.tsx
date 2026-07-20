import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Plus, Trash2, X } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { ErrorBanner } from '../ui/ErrorBanner'
import { ApiError } from '../../lib/api/client'
import { cn } from '../../lib/cn'
import type { ConversationSummary } from '../../lib/api/types'
import type { useConversations } from './useConversations'

export function ConversationList({
  activeConversationId,
  conversations,
  status,
  errorMessage,
  refresh,
  addConversation,
  removeConversation,
}: {
  activeConversationId?: string
  conversations: ConversationSummary[]
  status: 'loading' | 'ready' | 'error'
  errorMessage: string | null
  refresh: ReturnType<typeof useConversations>['refresh']
  addConversation: ReturnType<typeof useConversations>['addConversation']
  removeConversation: ReturnType<typeof useConversations>['removeConversation']
}) {
  const navigate = useNavigate()
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleNewConversation() {
    const created = await addConversation()
    navigate(`/c/${created.id}`)
  }

  async function handleConfirmDelete(conversationId: string) {
    setDeletingId(conversationId)
    setDeleteError(null)
    try {
      await removeConversation(conversationId)
      if (activeConversationId === conversationId) {
        navigate('/')
      }
    } catch (error) {
      setDeleteError(error instanceof ApiError ? error.message : 'Could not delete this conversation.')
    } finally {
      setDeletingId(null)
      setPendingDeleteId(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <Button type="button" variant="secondary" size="sm" onClick={handleNewConversation} className="justify-start">
        <Plus className="h-4 w-4" aria-hidden="true" />
        New conversation
      </Button>

      {status === 'loading' ? (
        <div className="flex items-center justify-center py-6">
          <Spinner className="h-5 w-5" />
        </div>
      ) : null}

      {status === 'error' ? (
        <ErrorBanner message={errorMessage ?? 'Could not load conversations.'} onRetry={refresh} />
      ) : null}

      {deleteError ? <ErrorBanner message={deleteError} onRetry={() => setDeleteError(null)} /> : null}

      {status === 'ready' && conversations.length === 0 ? (
        <p className="px-1 text-xs text-ink-muted">No conversations yet. Start one to ask about a Contoso Corp policy.</p>
      ) : null}

      {status === 'ready' && conversations.length > 0 ? (
        <ul className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pb-4">
          {conversations.map((conversation) => {
            const isPendingDelete = pendingDeleteId === conversation.id
            const isDeleting = deletingId === conversation.id

            return (
              <li key={conversation.id}>
                <Card
                  hoverLift={false}
                  onClick={isPendingDelete ? undefined : () => navigate(`/c/${conversation.id}`)}
                  className={cn(
                    'group flex items-center gap-2 px-3 py-2',
                    isPendingDelete ? '' : 'cursor-pointer',
                    activeConversationId === conversation.id
                      ? 'border-brand-orange/50 bg-brand-orange/5'
                      : 'hover:bg-surface',
                  )}
                >
                  {isPendingDelete ? (
                    <>
                      <p className="flex-1 truncate text-sm text-ink-muted">Delete this conversation?</p>
                      <button
                        type="button"
                        aria-label="Confirm delete"
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation()
                          void handleConfirmDelete(conversation.id)
                        }}
                        className="rounded-btn p-1 text-brand-red hover:bg-brand-red/10 disabled:opacity-50"
                      >
                        {isDeleting ? <Spinner className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" aria-hidden="true" />}
                      </button>
                      <button
                        type="button"
                        aria-label="Cancel delete"
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation()
                          setPendingDeleteId(null)
                        }}
                        className="rounded-btn p-1 text-ink-muted hover:bg-surface disabled:opacity-50"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </>
                  ) : (
                    <>
                      <p className="flex-1 truncate text-sm font-medium text-ink">
                        {conversation.title ?? 'Untitled conversation'}
                      </p>
                      <button
                        type="button"
                        aria-label="Delete conversation"
                        onClick={(event) => {
                          event.stopPropagation()
                          setPendingDeleteId(conversation.id)
                        }}
                        className="shrink-0 rounded-btn p-1 text-ink-muted opacity-0 hover:bg-surface hover:text-brand-red group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </>
                  )}
                </Card>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
