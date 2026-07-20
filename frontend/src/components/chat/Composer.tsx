import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { Button } from '../ui/Button'
import { ModelPicker } from './ModelPicker'
import type { ModelOut } from '../../lib/api/types'

export function Composer({
  disabled,
  onSend,
  models,
  provider,
  onProviderChange,
}: {
  disabled: boolean
  onSend: (content: string) => void
  models: ModelOut[]
  provider: string | null
  onProviderChange: (id: string) => void
}) {
  const [value, setValue] = useState('')

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  function handleFormSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={handleFormSubmit} className="flex flex-col gap-2 border-t border-line bg-surface-raised px-6 py-4">
      <ModelPicker models={models} value={provider} onChange={onProviderChange} />
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Ask about a Contoso Corp policy"
          className="max-h-40 min-h-10 flex-1 resize-none rounded-btn border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-brand-orange focus:outline-none disabled:opacity-60"
        />
        <Button type="submit" disabled={disabled || value.trim().length === 0} aria-label="Send message">
          <Send className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </form>
  )
}
