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
