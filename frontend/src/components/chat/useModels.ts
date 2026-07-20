import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { listModels } from '../../lib/api/models'
import type { ModelOut } from '../../lib/api/types'

type Status = 'loading' | 'ready' | 'error'

export function useModels() {
  const [models, setModels] = useState<ModelOut[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    // See useConversations.ts for why this must be reset here, not only in
    // useRef's initializer -- Strict Mode's dev-only double-mount would
    // otherwise leave this permanently false and freeze the UI at "loading".
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(() => {
    setStatus('loading')
    setErrorMessage(null)
    listModels()
      .then((data) => {
        if (mountedRef.current) {
          setModels(data)
          setStatus('ready')
        }
      })
      .catch((error: unknown) => {
        if (mountedRef.current) {
          setErrorMessage(error instanceof ApiError ? error.message : 'Could not load available models.')
          setStatus('error')
        }
      })
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { models, status, errorMessage, refresh }
}
