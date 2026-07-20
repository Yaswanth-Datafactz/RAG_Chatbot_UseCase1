// Base URL/key are overridable via frontend/.env (see .env.example); the
// defaults match the backend's own dev defaults (backend/.env.example)
// purely so the app works out of the box in local dev.
const DEFAULT_BASE_URL = 'http://localhost:8000/api/v1'
const DEFAULT_API_KEY = 'changeme-dev-key'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL
const API_KEY = import.meta.env.VITE_API_KEY ?? DEFAULT_API_KEY

export class ApiError extends Error {
  status: number
  type: string

  constructor(message: string, status: number, type = 'error') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.type = type
  }
}

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return { 'X-API-Key': API_KEY, ...extra }
}

export async function parseErrorBody(response: Response): Promise<{ type: string; message: string }> {
  try {
    const body = (await response.json()) as Partial<{ error: { type: string; message: string } }>
    if (body.error?.message) {
      return { type: body.error.type ?? 'error', message: body.error.message }
    }
  } catch {
    // Response body wasn't JSON (or was empty) -- fall through below.
  }
  return { type: 'error', message: `Request failed with status ${response.status}` }
}

/** JSON fetch wrapper: attaches X-API-Key, and turns the backend's
 * centralized {"error": {"type","message"}} shape into a typed ApiError
 * instead of a generic non-2xx failure. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const { type, message } = await parseErrorBody(response)
    throw new ApiError(message, response.status, type)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
