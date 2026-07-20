import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Renders an assistant message's Markdown (the model is asked to answer
 * in prose with citations, but naturally reaches for bold/lists/tables --
 * see CHAT_SYSTEM_PROMPT in backend/app/services/chat.py) as actual
 * formatted text instead of raw '**'/'-'/'#' characters. Re-parses the
 * full string on every render, so a streaming answer's not-yet-closed
 * markup (e.g. an unterminated "**") can look momentarily odd until the
 * closing token arrives -- the same tradeoff every token-streaming chat
 * UI makes, and it self-corrects within a token or two. User-typed
 * messages are rendered as plain text elsewhere, not through this. */
export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-1">{children}</li>,
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-orange underline underline-offset-2 hover:text-brand-orange/80"
            >
              {children}
            </a>
          ),
          h1: ({ children }) => <h1 className="text-base font-semibold text-ink">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-semibold text-ink">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-ink">{children}</h3>,
          h4: ({ children }) => <h4 className="text-sm font-semibold text-ink">{children}</h4>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-line pl-3 text-ink-muted italic">{children}</blockquote>
          ),
          hr: () => <hr className="border-line" />,
          code: ({ children }) => (
            <code className="rounded-btn bg-surface px-1 py-0.5 font-mono text-xs text-ink">{children}</code>
          ),
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-card bg-surface p-3 font-mono text-xs text-ink">{children}</pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-line px-2 py-1 font-medium text-ink-muted">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-line px-2 py-1">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
