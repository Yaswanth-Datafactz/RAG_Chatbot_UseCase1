import type { PersistedCitation, SseCitation } from '../../lib/api/types'

/** A single citation shape the UI renders, regardless of whether it came
 * from a live SSE `citations` event or from a reloaded conversation's
 * persisted history -- those two backend shapes differ (see below), so
 * every consumer works from this instead of either wire shape directly. */
export interface DisplayCitation {
  rank: number
  documentId: string
  documentTitle: string
  sectionPath: string | null
  snippet: string
  rerankerScore: number | null
  // Only ever real for PDF-sourced chunks -- null for DOCX/Markdown, which
  // have no page concept. Never fabricated: render nothing rather than a
  // guessed page number when this is null.
  pageNo: number | null
}

/** Reloaded conversation history (GET /conversations/{id}) returns
 * CitationOut, which -- confirmed against backend/app/schemas/conversation.py
 * -- has no document_title field, unlike the SSE `citations` event's
 * payload. section_path is always prefixed with the document's title
 * (corpus-wide convention, verified by
 * backend/tests/test_ingestion_real_corpus.py asserting
 * `section_path.startswith(document_title)` for every real corpus
 * document), so that's used as a well-grounded fallback rather than
 * showing a raw document_id or leaving the title blank. See
 * docs/phase-5.md's Deviations for the full reasoning. */
function titleFromSectionPath(sectionPath: string | null): string {
  if (!sectionPath) return 'Source document'
  return sectionPath.split(' > ')[0] ?? sectionPath
}

export function fromSseCitation(citation: SseCitation): DisplayCitation {
  return {
    rank: citation.rank,
    documentId: citation.document_id,
    documentTitle: citation.document_title,
    sectionPath: citation.section_path,
    snippet: citation.snippet,
    rerankerScore: citation.reranker_score,
    pageNo: citation.page_no,
  }
}

export function fromPersistedCitation(citation: PersistedCitation): DisplayCitation {
  return {
    rank: citation.rank,
    documentId: citation.document_id,
    documentTitle: titleFromSectionPath(citation.section_path),
    sectionPath: citation.section_path,
    snippet: citation.snippet,
    rerankerScore: citation.reranker_score,
    pageNo: citation.page_no,
  }
}
