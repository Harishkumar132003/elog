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

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { body, headers, ...rest } = options
  const token = getToken()

  // A file upload goes as FormData, which must be sent untouched: the browser
  // writes its own multipart Content-Type with the boundary, and stringifying it
  // would produce "[object FormData]".
  const isForm = body instanceof FormData

  const response = await fetch(`/api${path}`, {
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
