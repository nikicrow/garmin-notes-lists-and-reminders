export interface User {
  username: string
}

export interface HouseholdUser {
  id: string
  username: string
}

export interface Note {
  id: string
  body: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface TuckList {
  id: string
  owner_user_id: string
  title: string
  shared_user_ids: string[]
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface ListItem {
  id: string
  list_id: string
  body: string
  position: number
  created_by_user_id: string
  completed_at: string | null
  completed_by_user_id: string | null
  created_at: string
  updated_at: string
}

export interface Reminder {
  id: string
  creator_user_id: string
  title: string
  detail: string | null
  due_at_utc: string
  source_timezone: string
  is_urgent: boolean
  status: 'pending' | 'completed' | 'cancelled'
  created_at: string
  updated_at: string
  completed_at: string | null
  cancelled_at: string | null
  recipient_user_ids: string[]
  deliveries: ReminderDelivery[]
}

export interface ReminderDelivery {
  recipient_user_id: string
  status: 'pending' | 'claimed' | 'sent' | 'retryable' | 'failed'
  attempt_count: number
  next_attempt_at: string | null
  sent_at: string | null
  last_error_code: string | null
  updated_at: string
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

export const householdApi = {
  users: () => request<HouseholdUser[]>('/api/v1/household/users'),
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

export const remindersApi = {
  list: () => request<Reminder[]>('/api/v1/reminders'),
  create: (payload: {
    title: string
    detail: string | null
    due_at_utc: string
    source_timezone: string
    is_urgent: boolean
    recipient_user_ids: string[]
  }) =>
    request<Reminder>('/api/v1/reminders', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  edit: (
    id: string,
    changes: { title: string; detail: string | null; is_urgent: boolean },
  ) =>
    request<Reminder>(`/api/v1/reminders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  complete: (id: string) =>
    request<Reminder>(`/api/v1/reminders/${id}/complete`, { method: 'POST' }),
  cancel: (id: string) =>
    request<Reminder>(`/api/v1/reminders/${id}/cancel`, { method: 'POST' }),
  snooze: (id: string, dueAtUtc: string) =>
    request<Reminder>(`/api/v1/reminders/${id}/snooze`, {
      method: 'POST',
      body: JSON.stringify({ due_at_utc: dueAtUtc }),
    }),
  reschedule: (id: string, dueAtUtc: string, sourceTimezone: string) =>
    request<Reminder>(`/api/v1/reminders/${id}/reschedule`, {
      method: 'POST',
      body: JSON.stringify({
        due_at_utc: dueAtUtc,
        source_timezone: sourceTimezone,
      }),
    }),
}

export const listsApi = {
  list: () => request<TuckList[]>('/api/v1/lists'),
  create: (title: string) =>
    request<TuckList>('/api/v1/lists', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  rename: (id: string, title: string) =>
    request<TuckList>(`/api/v1/lists/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  archive: (id: string) =>
    request<TuckList>(`/api/v1/lists/${id}`, { method: 'DELETE' }),
  share: (id: string, memberId: string) =>
    request<TuckList>(`/api/v1/lists/${id}/members/${memberId}`, {
      method: 'PUT',
    }),
  unshare: (id: string, memberId: string) =>
    request<TuckList>(`/api/v1/lists/${id}/members/${memberId}`, {
      method: 'DELETE',
    }),
  listItems: (id: string) => request<ListItem[]>(`/api/v1/lists/${id}/items`),
  addItem: (id: string, body: string) =>
    request<ListItem>(`/api/v1/lists/${id}/items`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
  editItem: (
    listId: string,
    itemId: string,
    changes: { body?: string; is_checked?: boolean },
  ) =>
    request<ListItem>(`/api/v1/lists/${listId}/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  deleteItem: (listId: string, itemId: string) =>
    request<void>(`/api/v1/lists/${listId}/items/${itemId}`, {
      method: 'DELETE',
    }),
  reorderItems: (listId: string, items: ListItem[]) =>
    request<ListItem[]>(`/api/v1/lists/${listId}/items/reorder`, {
      method: 'PUT',
      body: JSON.stringify({
        positions: items.map((item, position) => ({
          item_id: item.id,
          position,
        })),
      }),
    }),
}
