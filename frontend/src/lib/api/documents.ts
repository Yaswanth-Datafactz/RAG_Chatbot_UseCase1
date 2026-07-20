import { apiFetch } from './client'
import type { DocumentOut } from './types'

export function listDocuments(): Promise<DocumentOut[]> {
  return apiFetch<DocumentOut[]>('/documents')
}
