import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { listDocuments } from '../../lib/api/documents'
import type { DocumentOut } from '../../lib/api/types'

type Status = 'loading' | 'ready' | 'error'

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentOut[]>([])
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
    listDocuments()
      .then((data) => {
        if (mountedRef.current) {
          setDocuments(data)
          setStatus('ready')
        }
      })
      .catch((error: unknown) => {
        if (mountedRef.current) {
          setErrorMessage(error instanceof ApiError ? error.message : 'Could not load documents.')
          setStatus('error')
        }
      })
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { documents, status, errorMessage, refresh }
}
