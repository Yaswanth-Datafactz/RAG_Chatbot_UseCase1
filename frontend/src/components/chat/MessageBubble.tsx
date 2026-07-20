import { AlertTriangle, Bot, ShieldQuestion } from 'lucide-react'
import { cn } from '../../lib/cn'
import { Spinner } from '../ui/Spinner'
import { CitationChipRow } from './CitationChipRow'
import { MarkdownMessage } from './MarkdownMessage'
import type { UiMessage } from './useChat'

export function MessageBubble({ message }: { message: UiMessage }) {
  const isUser = message.role === 'user'
  const isThinking = message.status === 'streaming' && message.content.length === 0 && !message.citations

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[75%] rounded-card px-4 py-3 text-sm leading-relaxed',
          isUser ? 'bg-brand-orange text-white' : 'border border-line bg-surface-raised text-ink',
        )}
      >
        {!isUser && message.refused ? (
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            <ShieldQuestion className="h-3.5 w-3.5" aria-hidden="true" />
            Outside the knowledge base
          </div>
        ) : null}

        {/* Citations render as soon as they arrive, ahead of the answer
            text itself (docs/phase-4.md: citations event precedes tokens). */}
        {!isUser && message.citations && message.citations.length > 0 ? (
          <div className="mb-2">
            <CitationChipRow citations={message.citations} />
          </div>
        ) : null}

        {isThinking ? (
          <div className="flex items-center gap-2 text-ink-muted">
            <Spinner className="h-4 w-4" />
            Generating a response
          </div>
        ) : isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownMessage content={message.content} />
        )}

        {!isUser && !message.refused && message.status === 'done' && message.model ? (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-ink-muted">
            <Bot className="h-3 w-3 shrink-0" aria-hidden="true" />
            Answered by {message.model}
          </div>
        ) : null}

        {message.status === 'error' ? (
          <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-brand-red">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {message.streamErrorMessage ?? 'Something went wrong. Your teams can try sending this again.'}
          </div>
        ) : null}
      </div>
    </div>
  )
}
