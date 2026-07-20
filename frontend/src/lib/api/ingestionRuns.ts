import { apiFetch } from './client'
import type { IngestionRunOut } from './types'

/** 202 Accepted, status="pending" -- the real work is scheduled as a
 * BackgroundTasks job and hasn't started by the time this resolves (see
 * docs/phase-4.md). Callers must poll getIngestionRun() for real progress. */
export function triggerIngestionRun(): Promise<IngestionRunOut> {
  return apiFetch<IngestionRunOut>('/ingestion-runs', { method: 'POST' })
}

export function getIngestionRun(runId: string): Promise<IngestionRunOut> {
  return apiFetch<IngestionRunOut>(`/ingestion-runs/${runId}`)
}
