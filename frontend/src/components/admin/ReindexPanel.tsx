import { RefreshCw } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { ErrorBanner } from '../ui/ErrorBanner'
import { Spinner } from '../ui/Spinner'
import { IngestionStatusBadge } from './IngestionStatusBadge'
import { useIngestionRun } from './useIngestionRun'

function formatDateTime(iso: string | null): string | null {
  if (!iso) return null
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function ReindexPanel() {
  const { run, isTriggering, isPolling, requestError, trigger, refreshStatus } = useIngestionRun()
  const busy = isTriggering || isPolling

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-ink">Re-index</h2>
          <p className="mt-1 max-w-md text-sm text-ink-muted">
            Rebuilds the search index from the current corpus. Your teams keep querying the existing index until the
            new one finishes and swaps in.
          </p>
        </div>
        <Button type="button" onClick={trigger} disabled={busy}>
          {isTriggering ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          Re-index
        </Button>
      </div>

      {requestError ? <ErrorBanner message={requestError} onRetry={run ? refreshStatus : trigger} /> : null}

      {!requestError && !run ? (
        <p className="text-sm text-ink-muted">No re-index has been triggered from this browser yet.</p>
      ) : null}

      {run ? (
        <div className="flex flex-col gap-3 rounded-card border border-line bg-surface px-4 py-3">
          <div className="flex items-center gap-2 text-sm">
            <IngestionStatusBadge status={run.status} />
            <span className="text-ink-muted">run {run.id.slice(0, 8)}</span>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-ink-muted">Documents</dt>
              <dd className="text-ink">{run.doc_count}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Chunks</dt>
              <dd className="text-ink">{run.chunk_count}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Started</dt>
              <dd className="text-ink">{formatDateTime(run.started_at) ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Finished</dt>
              <dd className="text-ink">{formatDateTime(run.finished_at) ?? '—'}</dd>
            </div>
          </dl>
          {run.status === 'failed' && run.error ? <ErrorBanner message={run.error} /> : null}
        </div>
      ) : null}
    </Card>
  )
}
