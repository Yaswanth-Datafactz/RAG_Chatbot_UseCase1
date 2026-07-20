import { FileText } from 'lucide-react'
import { Card } from '../ui/Card'
import { Pill } from '../ui/Pill'
import { Spinner } from '../ui/Spinner'
import { ErrorBanner } from '../ui/ErrorBanner'
import { useDocuments } from './useDocuments'

function formatByteSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function DocumentsTable() {
  const { documents, status, errorMessage, refresh } = useDocuments()

  if (status === 'loading') {
    return (
      <Card className="flex items-center justify-center py-12">
        <Spinner className="h-6 w-6" />
      </Card>
    )
  }

  if (status === 'error') {
    return <ErrorBanner message={errorMessage ?? 'Could not load documents.'} onRetry={refresh} />
  }

  if (documents.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-2 py-12 text-center">
        <FileText className="h-6 w-6 text-ink-muted" aria-hidden="true" />
        <p className="text-sm text-ink-muted">No documents are indexed yet. Trigger a re-index to build the corpus index.</p>
      </Card>
    )
  }

  return (
    <Card hoverLift={false} className="overflow-x-auto p-0">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
            <th className="px-4 py-3 font-medium">Title</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Chunks</th>
            <th className="px-4 py-3 font-medium">Size</th>
            <th className="px-4 py-3 font-medium">Added</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id} className="border-b border-line last:border-0">
              <td className="px-4 py-3">
                <p className="font-medium text-ink">{document.title}</p>
                <p className="text-xs text-ink-muted">{document.source_filename}</p>
              </td>
              <td className="px-4 py-3">
                <Pill tone="neutral">{document.doc_type}</Pill>
              </td>
              <td className="px-4 py-3 text-ink">{document.current_chunk_count}</td>
              <td className="px-4 py-3 text-ink-muted">{formatByteSize(document.byte_size)}</td>
              <td className="px-4 py-3 text-ink-muted">{formatDate(document.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
