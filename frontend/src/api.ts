export interface User {
  username: string
}

export interface Note {
  id: string
  body: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.body === undefined
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...init.headers,
    },
  })

  if (!response.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') {
        message = body.detail
      }
    } catch {
      // Keep the safe fallback for non-JSON responses.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const authApi = {
  currentUser: () => request<User>('/api/v1/auth/me'),
  login: (username: string, password: string) =>
    request<User>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
}

export const notesApi = {
  list: () => request<Note[]>('/api/v1/notes'),
  create: (body: string) =>
    request<Note>('/api/v1/notes', {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
  edit: (id: string, body: string) =>
    request<Note>(`/api/v1/notes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ body }),
    }),
  archive: (id: string) =>
    request<Note>(`/api/v1/notes/${id}`, { method: 'DELETE' }),
}
