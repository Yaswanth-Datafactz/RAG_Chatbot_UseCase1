// Mirrors backend/app/schemas/conversation.py and document.py exactly
// (field names, nullability) -- confirmed against the source, not guessed.

export interface ConversationSummary {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface PersistedCitation {
  id: string
  document_id: string
  rank: number
  reranker_score: number | null
  section_path: string | null
  snippet: string
  // Only ever populated for PDF-sourced chunks -- null for DOCX/Markdown,
  // which have no page concept (backend/app/services/chat.py's
  // _citation_payload docstring). Never fabricated.
  page_no: number | null
}

export interface PersistedMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  refused: boolean
  model: string | null
  created_at: string
  citations: PersistedCitation[]
}

export interface ConversationDetail extends ConversationSummary {
  messages: PersistedMessage[]
}

// docs/phase-4.md's `citations` SSE event shape -- distinct from
// PersistedCitation above: it carries document_title (for display without
// a second lookup) but no `id`, and no `chunk_index` (see docs/phase-5.md
// "Deviations" for why the source-passage viewer renders from this shape
// directly rather than calling GET /documents/{id}/chunks/{chunk_index}).
export interface SseCitation {
  rank: number
  document_id: string
  document_title: string
  section_path: string | null
  snippet: string
  reranker_score: number | null
  page_no: number | null
}

// Mirrors backend/app/schemas/document.py::DocumentOut exactly. Note there
// is no ingestion-run reference on this shape -- a document's row doesn't
// know which run produced its current_chunk_count, only the count itself
// (see docs/phase-6.md for why the admin UI can't show a per-document run
// status).
export interface DocumentOut {
  id: string
  source_filename: string
  title: string
  doc_type: string
  byte_size: number
  created_at: string
  current_chunk_count: number
}

// Mirrors backend/app/schemas/models.py::ModelOut exactly. `id` is exactly
// what a client sends back as ChatMessageRequest.provider.
export interface ModelOut {
  id: string
  label: string
  available: boolean
  is_default: boolean
}

// Mirrors backend/app/schemas/ingestion.py::IngestionRunOut exactly. The
// three status values actually written by backend/app/services/ingestion.py
// are "pending" (on creation), "running" (once the background job starts),
// and a terminal "succeeded" or "failed" -- confirmed by reading that file,
// not guessed.
export interface IngestionRunOut {
  id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  embedding_model: string
  doc_count: number
  chunk_count: number
  is_current: boolean
  error: string | null
  started_at: string | null
  finished_at: string | null
}
