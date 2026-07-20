import { useState } from 'react'
import type { DisplayCitation } from './citation'
import { CitationChip } from './CitationChip'
import { SourcePassageDrawer } from './SourcePassageDrawer'

export function CitationChipRow({ citations }: { citations: DisplayCitation[] }) {
  const [selected, setSelected] = useState<DisplayCitation | null>(null)

  if (citations.length === 0) return null

  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((citation) => (
          <CitationChip key={citation.rank} citation={citation} onClick={() => setSelected(citation)} />
        ))}
      </div>
      {selected ? <SourcePassageDrawer citation={selected} onClose={() => setSelected(null)} /> : null}
    </>
  )
}
