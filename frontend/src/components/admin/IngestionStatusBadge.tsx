import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-react'
import { Pill } from '../ui/Pill'
import type { IngestionRunOut } from '../../lib/api/types'

export function IngestionStatusBadge({ status }: { status: IngestionRunOut['status'] }) {
  switch (status) {
    case 'pending':
      return (
        <Pill tone="neutral">
          <Clock className="h-3 w-3" aria-hidden="true" />
          Pending
        </Pill>
      )
    case 'running':
      return (
        <Pill tone="neutral">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
          Running
        </Pill>
      )
    case 'succeeded':
      return (
        <Pill tone="brand">
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          Succeeded
        </Pill>
      )
    case 'failed':
      return (
        <Pill tone="danger">
          <XCircle className="h-3 w-3" aria-hidden="true" />
          Failed
        </Pill>
      )
  }
}
