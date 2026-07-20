import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { getIngestionRun, triggerIngestionRun } from '../../lib/api/ingestionRuns'
import type { IngestionRunOut } from '../../lib/api/types'

const POLL_INTERVAL_MS = 2000

// There is no GET /ingestion-runs (list) or GET /ingestion-runs/current
// route (confirmed against backend/app/api/v1/ingestion.py) -- only
// POST /ingestion-runs and GET /ingestion-runs/{id}, which requires an id
// this client already has. So "the current run's status" can only ever
// mean "the last run this browser triggered or resumed," not the true
// live-index status on a fresh browser that has never triggered one. The
// run id is persisted here purely so a page reload mid-poll resumes
// watching the same run instead of losing track of it. See docs/phase-6.md.
const STORAGE_KEY = 'ragchatbot-last-ingestion-run-id'

/** Manages the re-index trigger + poll-until-terminal lifecycle described
 * in docs/plan.md's Phase 6 scope: POST starts a run at status="pending"
 * (the real work happens later, in the BackgroundTasks job -- see
 * docs/phase-2.md's atomic swap), and only polling GET /ingestion-runs/{id}
 * until it reaches "succeeded" or "failed" reflects what actually
 * happened. */
export function useIngestionRun() {
  const [run, setRun] = useState<IngestionRunOut | null>(null)
  const [isTriggering, setIsTriggering] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const pollTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    // See useConversations.ts for why this must be reset here, not only in
    // useRef's initializer -- Strict Mode's dev-only double-mount would
    // otherwise leave this permanently false, so trigger()'s and
    // pollUntilTerminal()'s `.then()` callbacks would silently no-op
    // forever: isTriggering would never clear and no poll would ever fire.
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (pollTimeoutRef.current !== null) {
        window.clearTimeout(pollTimeoutRef.current)
      }
    }
  }, [])

  const pollUntilTerminal = useCallback((runId: string) => {
    setIsPolling(true)
    setRequestError(null)

    const tick = () => {
      getIngestionRun(runId)
        .then((data) => {
          if (!mountedRef.current) return
          setRun(data)
          if (data.status === 'succeeded' || data.status === 'failed') {
            setIsPolling(false)
          } else {
            pollTimeoutRef.current = window.setTimeout(tick, POLL_INTERVAL_MS)
          }
        })
        .catch((error: unknown) => {
          if (!mountedRef.current) return
          setIsPolling(false)
          setRequestError(error instanceof ApiError ? error.message : 'Could not check the re-index run status.')
        })
    }

    tick()
  }, [])

  // Resume watching the last-triggered run across a reload or remount, so
  // an in-progress re-index doesn't silently stop being tracked.
  useEffect(() => {
    const storedId = window.localStorage.getItem(STORAGE_KEY)
    if (!storedId) return

    getIngestionRun(storedId)
      .then((data) => {
        if (!mountedRef.current) return
        setRun(data)
        if (data.status !== 'succeeded' && data.status !== 'failed') {
          pollUntilTerminal(storedId)
        }
      })
      .catch((error: unknown) => {
        if (!mountedRef.current) return
        if (error instanceof ApiError && error.status === 404) {
          // A newer run from elsewhere superseded and cleaned up this one
          // (Phase 2's atomic swap deletes the previous run) -- benign.
          window.localStorage.removeItem(STORAGE_KEY)
          return
        }
        setRequestError(error instanceof ApiError ? error.message : 'Could not load the last re-index run.')
      })
    // pollUntilTerminal is stable (useCallback with empty deps), so this
    // still only runs once per mount in practice.
  }, [pollUntilTerminal])

  const trigger = useCallback(() => {
    setIsTriggering(true)
    setRequestError(null)
    triggerIngestionRun()
      .then((data) => {
        if (!mountedRef.current) return
        setRun(data)
        setIsTriggering(false)
        window.localStorage.setItem(STORAGE_KEY, data.id)
        pollUntilTerminal(data.id)
      })
      .catch((error: unknown) => {
        if (!mountedRef.current) return
        setIsTriggering(false)
        setRequestError(error instanceof ApiError ? error.message : 'Could not start a re-index run.')
      })
  }, [pollUntilTerminal])

  // Resumes checking the *existing* run after a poll request failed --
  // distinct from trigger(), which would start a brand-new re-index.
  const refreshStatus = useCallback(() => {
    if (run) {
      pollUntilTerminal(run.id)
    }
  }, [run, pollUntilTerminal])

  return { run, isTriggering, isPolling, requestError, trigger, refreshStatus }
}
