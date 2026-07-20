import { useEffect } from 'react'
import { X } from 'lucide-react'
import { Button } from '../ui/Button'
import { Pill } from '../ui/Pill'
import type { DisplayCitation } from './citation'

/** Renders straight from the citation data already in hand (the SSE
 * `citations` event, or persisted history) -- see docs/phase-5.md's
 * Deviations for why this doesn't call
 * GET /documents/{document_id}/chunks/{chunk_index}: the citation payload
 * never carries a chunk_index to call it with, and the citation's own
 * snippet is already the full original chunk text, denormalized
 * specifically so it survives independent of the live index. */
export function SourcePassageDrawer({ citation, onClose }: { citation: DisplayCitation; onClose: () => void }) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-brand-navy/50" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Source passage: ${citation.documentTitle}`}
        onClick={(event) => event.stopPropagation()}
        className="flex w-full flex-col gap-4 overflow-y-auto border-l border-line bg-surface-raised p-6 shadow-xl sm:w-[40vw] sm:min-w-[40vw] sm:max-w-3xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Source {citation.rank}</p>
              {citation.pageNo !== null ? <Pill tone="neutral">Page {citation.pageNo}</Pill> : null}
            </div>
            <h2 className="mt-1 text-base font-semibold text-ink">{citation.documentTitle}</h2>
            {citation.sectionPath ? <p className="mt-0.5 text-sm text-ink-muted">{citation.sectionPath}</p> : null}
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close source passage">
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">{citation.snippet}</p>

        {citation.rerankerScore !== null ? (
          <p className="mt-auto text-xs text-ink-muted">Relevance score: {citation.rerankerScore.toFixed(2)}</p>
        ) : null}
      </div>
    </div>
  )
}
