import { apiFetch } from './client'
import type { ModelOut } from './types'

export function listModels(): Promise<ModelOut[]> {
  return apiFetch<ModelOut[]>('/models')
}
