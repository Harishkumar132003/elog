/** Thin fetch wrapper: attaches the bearer token and normalises errors. */

const TOKEN_KEY = 'opbook360.token'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY)

/** Called when a token is rejected, so the app can drop back to the login screen. */
let onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (handler: () => void): void => {
  onUnauthorized = handler
}

interface Options extends Omit<RequestInit, 'body'> {
  body?: unknown
}

/** Where the backend lives.
 *
 *  Unset (the default in `npm run dev`) leaves requests relative, so they go to
 *  the Vite dev server and its proxy forwards them — same origin, no CORS in the
 *  way. Set it to a backend origin such as `http://localhost:7200` and the
 *  browser calls the API directly, which is what a built container needs since
 *  there is no dev server left to proxy through.
 *
 *  Vite inlines this at BUILD time, not at run time: a container has to be built
 *  with the value it will use.
 */
const API_BASE = (import.meta.env.VITE_API_URL ?? '')
  .trim()
  // Tolerate both `http://host:7200` and `http://host:7200/` or `.../api`, so a
  // trailing slash in an .env file is not a silent 404.
  .replace(/\/+$/, '')
  .replace(/\/api$/, '')

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { body, headers, ...rest } = options
  const token = getToken()

  // A file upload goes as FormData, which must be sent untouched: the browser
  // writes its own multipart Content-Type with the boundary, and stringifying it
  // would produce "[object FormData]".
  const isForm = body instanceof FormData

  const response = await fetch(`${API_BASE}/api${path}`, {
    ...rest,
    headers: {
      ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: isForm ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401) {
    clearToken()
    onUnauthorized?.()
    throw new ApiError(401, 'Session expired — please sign in again')
  }

  if (!response.ok) {
    // FastAPI puts the message in `detail`; fall back to the status text.
    let message = response.statusText
    try {
      const payload = await response.json()
      const detail = payload?.detail
      message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? (detail[0]?.msg ?? message)
            : message
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message)
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

/** One decoded server-sent event. */
export interface StreamEvent {
  name: string
  data: unknown
}

/** POST that reads a `text/event-stream` reply frame by frame.
 *
 *  EventSource cannot carry an Authorization header and only speaks GET, so the
 *  stream is read off `fetch` directly. Auth and error handling stay here rather
 *  than at the call site, so a streamed request fails exactly like a plain one.
 *
 *  Throws if streaming is unavailable, which is the signal for a caller to fall
 *  back to the ordinary request.
 */
export async function apiStream(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  // A recording is uploaded as FormData and must go untouched — stringifying it
  // would send the literal text "[object FormData]", and the browser has to set
  // its own multipart Content-Type with the boundary. Same branch `api()` uses.
  const isForm = body instanceof FormData

  const response = await fetch(`${API_BASE}/api${path}`, {
    method: 'POST',
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: isForm ? (body as FormData) : JSON.stringify(body),
    signal,
  })

  if (response.status === 401) {
    clearToken()
    onUnauthorized?.()
    throw new ApiError(401, 'Session expired — please sign in again')
  }

  if (!response.ok) {
    // Guard-rail failures (too long, empty, service off) arrive as ordinary JSON
    // before the stream opens, and their message is worth showing.
    let message = response.statusText
    try {
      const detail = (await response.json())?.detail
      if (typeof detail === 'string') message = detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message)
  }
  if (!response.body) throw new ApiError(0, 'Streaming is not supported here')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Frames are separated by a blank line; anything after the last one is a
    // partial frame and waits for the next chunk.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      let name = 'message'
      const payload: string[] = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) name = line.slice(6).trim()
        else if (line.startsWith('data:')) payload.push(line.slice(5).trim())
      }
      if (!payload.length) continue
      try {
        onEvent({ name, data: JSON.parse(payload.join('\n')) })
      } catch {
        /* a malformed frame is skipped rather than killing the stream */
      }
    }
  }
}
