import { FileText } from 'lucide-react'
import { Pill } from '../ui/Pill'
import type { DisplayCitation } from './citation'

export function CitationChip({ citation, onClick }: { citation: DisplayCitation; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="cursor-pointer border-0 bg-transparent p-0">
      <Pill tone="brand" className="max-w-64 transition-colors hover:bg-brand-orange/20">
        <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="truncate">
          {citation.rank}. {citation.documentTitle}
          {citation.pageNo !== null ? `, p. ${citation.pageNo}` : ''}
        </span>
      </Pill>
    </button>
  )
}
