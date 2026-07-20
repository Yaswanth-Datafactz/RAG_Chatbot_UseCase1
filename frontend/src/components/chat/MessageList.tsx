import { useEffect, useRef } from 'react'
import { MessageSquare } from 'lucide-react'
import { Card } from '../ui/Card'
import { ErrorBanner } from '../ui/ErrorBanner'
import { Spinner } from '../ui/Spinner'
import { MessageBubble } from './MessageBubble'
import type { UiMessage } from './useChat'

// One question per corpus topic, spanning distinct source documents so the
// suggestions double as a quick tour of what's indexed -- see
// corpus/manifest.json for the full document set.
const SAMPLE_QUESTIONS = [
  "What is Contoso Corp's policy on paid time off?",
  'How do I report a suspected security incident?',
  'What are the guidelines for working remotely?',
  'What health and welfare benefits does Contoso Corp offer?',
]

export function MessageList({
  messages,
  historyStatus,
  historyError,
  onSampleQuestion,
}: {
  messages: UiMessage[]
  historyStatus: 'idle' | 'loading' | 'ready' | 'error'
  historyError: string | null
  onSampleQuestion?: (question: string) => void
}) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  if (historyStatus === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  if (historyStatus === 'error') {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <ErrorBanner message={historyError ?? 'Could not load this conversation.'} className="max-w-md" />
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <MessageSquare className="h-8 w-8 text-brand-orange" aria-hidden="true" />
        <p className="text-base font-semibold text-ink">Ask about a Contoso Corp policy</p>
        <p className="max-w-sm text-sm text-ink-muted">
          Your teams can ask about PTO, benefits, security, and other Contoso Corp policies. Answers are grounded in
          the indexed policy documents and always cite their source.
        </p>

        {onSampleQuestion ? (
          <div className="mt-4 grid w-full max-w-lg grid-cols-1 gap-2 text-left sm:grid-cols-2">
            {SAMPLE_QUESTIONS.map((question) => (
              <Card
                key={question}
                onClick={() => onSampleQuestion(question)}
                className="cursor-pointer px-4 py-3 text-sm text-ink hover:bg-surface"
              >
                {question}
              </Card>
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-6 py-6">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
