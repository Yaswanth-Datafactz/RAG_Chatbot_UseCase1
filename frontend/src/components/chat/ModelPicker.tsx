import { Bot } from 'lucide-react'
import type { ModelOut } from '../../lib/api/types'

/** Purely presentational -- ChatPage owns the model list (useModels())
 * and the selected provider, so the same selection is shared between the
 * Composer's typed messages and MessageList's sample-question clicks. */
export function ModelPicker({
  models,
  value,
  onChange,
}: {
  models: ModelOut[]
  value: string | null
  onChange: (id: string) => void
}) {
  if (models.length === 0) return null

  return (
    <label className="flex items-center gap-1.5 text-xs text-ink-muted">
      <Bot className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <select
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-btn border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-brand-orange focus:outline-none"
      >
        {models.map((model) => (
          <option key={model.id} value={model.id} disabled={!model.available}>
            {model.label}
            {model.available ? '' : ' (not configured)'}
          </option>
        ))}
      </select>
    </label>
  )
}
