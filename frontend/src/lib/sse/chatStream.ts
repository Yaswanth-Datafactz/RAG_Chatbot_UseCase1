import { API_BASE_URL, ApiError, authHeaders, parseErrorBody } from '../api/client'
import type { SseCitation } from '../api/types'

// The exact 4 event types docs/phase-4.md documents, with their exact
// JSON keys -- confirmed against that doc (and services/chat.py) before
// writing this, not guessed.
export type ChatStreamEvent =
  | { type: 'citations'; citations: SseCitation[] }
  | { type: 'token'; delta: string }
  | { type: 'done'; message_id: string; refused: boolean; model: string | null }
  | { type: 'error'; error: { type: string; message: string } }

interface SseFrame {
  event: string
  data: string
}

/** Splits a raw SSE byte stream into {event, data} frames. docs/phase-4.md's
 * wire format is exactly "event: <name>\ndata: <json>\n\n" -- one blank
 * line between frames -- so frames are found by splitting on a blank
 * line (tolerating \r\n defensively, even though the backend only emits
 * \n). */
async function* parseSseFrames(reader: ReadableStreamDefaultReader<Uint8Array>): AsyncGenerator<SseFrame> {
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })

    let separatorMatch = buffer.match(/\r?\n\r?\n/)
    while (separatorMatch?.index !== undefined) {
      const rawFrame = buffer.slice(0, separatorMatch.index)
      buffer = buffer.slice(separatorMatch.index + separatorMatch[0].length)

      const lines = rawFrame.split(/\r?\n/)
      const eventLine = lines.find((line) => line.startsWith('event: '))
      const dataLine = lines.find((line) => line.startsWith('data: '))
      if (eventLine && dataLine) {
        yield { event: eventLine.slice('event: '.length), data: dataLine.slice('data: '.length) }
      }

      separatorMatch = buffer.match(/\r?\n\r?\n/)
    }
  }
}

/** Consumes POST /conversations/{id}/messages's text/event-stream body
 * (docs/phase-4.md). Native EventSource can't be used here since it only
 * supports GET requests, not a POST with a JSON body -- this hand-rolls
 * the same frame parsing the backend's own tests exercise on the server
 * side.
 *
 * HTTP-level failures (401/404/422 -- rejected before any streaming
 * begins) throw ApiError; the in-stream `error` event (which can arrive
 * after citations/tokens were already yielded) is yielded instead, never
 * thrown. Callers must handle both distinctly, exactly as docs/phase-4.md's
 * valid-orderings table distinguishes them. */
export async function* streamChatMessage(
  conversationId: string,
  content: string,
  options?: { signal?: AbortSignal; provider?: string | null },
): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...authHeaders(),
    },
    body: JSON.stringify({ content, provider: options?.provider ?? null }),
    signal: options?.signal,
  })

  if (!response.ok || !response.body) {
    const { type, message } = await parseErrorBody(response)
    throw new ApiError(message, response.status, type)
  }

  const reader = response.body.getReader()
  for await (const frame of parseSseFrames(reader)) {
    const payload = JSON.parse(frame.data) as Record<string, unknown>
    switch (frame.event) {
      case 'citations':
        yield { type: 'citations', citations: payload.citations as SseCitation[] }
        break
      case 'token':
        yield { type: 'token', delta: payload.delta as string }
        break
      case 'done':
        yield {
          type: 'done',
          message_id: payload.message_id as string,
          refused: payload.refused as boolean,
          model: (payload.model as string | null | undefined) ?? null,
        }
        break
      case 'error':
        yield { type: 'error', error: payload.error as { type: string; message: string } }
        break
      default:
        // Forward-compatible: ignore any event type not in phase-4.md's
        // documented protocol rather than crashing the stream.
        break
    }
  }
}
