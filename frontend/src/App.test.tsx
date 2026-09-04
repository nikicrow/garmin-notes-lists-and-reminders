import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

describe('App', () => {
  it('manages a shared shopping list and its items', async () => {
    window.history.replaceState(null, '', '/lists')
    const ownerId = '11111111-1111-1111-1111-111111111111'
    const memberId = '22222222-2222-2222-2222-222222222222'
    const list = {
      id: '33333333-3333-3333-3333-333333333333',
      owner_user_id: ownerId,
      title: 'Shopping',
      shared_user_ids: [],
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      archived_at: null,
    }
    const milk = {
      id: '44444444-4444-4444-4444-444444444444',
      list_id: list.id,
      body: 'Milk',
      position: 0,
      created_by_user_id: ownerId,
      completed_at: null,
      completed_by_user_id: null,
      created_at: '2026-09-04T10:01:00Z',
      updated_at: '2026-09-04T10:01:00Z',
    }
    const bread = {
      ...milk,
      id: '55555555-5555-5555-5555-555555555555',
      body: 'Bread',
      position: 1,
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([list]))
      .mockResolvedValueOnce(jsonResponse([milk, bread]))
      .mockResolvedValueOnce(
        jsonResponse({ ...bread, completed_at: '2026-09-04T10:02:00Z' }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ...list, shared_user_ids: [memberId] }),
      )
      .mockResolvedValueOnce(jsonResponse({ ...list, shared_user_ids: [] }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open Shopping' }),
    )
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Bread' }))

    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `/api/v1/lists/${list.id}/items/${bread.id}`,
      expect.objectContaining({
        body: JSON.stringify({ is_checked: true }),
        credentials: 'include',
        method: 'PATCH',
      }),
    )
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: 'Bread' })).toBeChecked(),
    )

    fireEvent.change(screen.getByLabelText('Share with user ID'), {
      target: { value: memberId },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))

    expect(await screen.findByText(memberId)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      `/api/v1/lists/${list.id}/members/${memberId}`,
      expect.objectContaining({ credentials: 'include', method: 'PUT' }),
    )

    fireEvent.click(
      screen.getByRole('button', { name: `Remove access for ${memberId}` }),
    )

    await waitFor(() =>
      expect(screen.queryByText(memberId)).not.toBeInTheDocument(),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      `/api/v1/lists/${list.id}/members/${memberId}`,
      expect.objectContaining({ credentials: 'include', method: 'DELETE' }),
    )
  })

  it('shows permission feedback and preserves a list rename', async () => {
    window.history.replaceState(null, '', '/lists')
    const list = {
      id: '33333333-3333-3333-3333-333333333333',
      owner_user_id: '11111111-1111-1111-1111-111111111111',
      title: 'Shared shopping',
      shared_user_ids: ['22222222-2222-2222-2222-222222222222'],
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      archived_at: null,
    }
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
        .mockResolvedValueOnce(jsonResponse([list]))
        .mockResolvedValueOnce(
          jsonResponse({ detail: 'Only the owner can rename this list' }, 403),
        ),
    )

    render(<App />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Rename Shared shopping' }),
    )
    const rename = screen.getByLabelText('List name')
    fireEvent.change(rename, { target: { value: 'Weekly groceries' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save name' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only the owner can rename this list',
    )
    expect(rename).toHaveValue('Weekly groceries')
    expect(screen.getByRole('button', { name: 'Save name' })).toBeEnabled()
  })

  it('creates, edits, and archives a note', async () => {
    const draft = {
      id: '11111111-1111-1111-1111-111111111111',
      body: 'Pack the swim bag',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      archived_at: null,
    }
    const edited = {
      ...draft,
      body: 'Pack the swim bag and towels',
      updated_at: '2026-09-04T10:05:00Z',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(draft, 201))
      .mockResolvedValueOnce(jsonResponse(edited))
      .mockResolvedValueOnce(
        jsonResponse({ ...edited, archived_at: '2026-09-04T10:10:00Z' }),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('New note'), {
      target: { value: draft.body },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add note' }))

    expect(await screen.findByText(draft.body)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/notes',
      expect.objectContaining({
        body: JSON.stringify({ body: draft.body }),
        credentials: 'include',
        method: 'POST',
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Edit note'), {
      target: { value: edited.body },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.queryByLabelText('Edit note')).not.toBeInTheDocument()
    })
    expect(screen.getByText(edited.body)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `/api/v1/notes/${draft.id}`,
      expect.objectContaining({
        body: JSON.stringify({ body: edited.body }),
        credentials: 'include',
        method: 'PATCH',
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Archive' }))

    expect(await screen.findByText('No notes yet.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      `/api/v1/notes/${draft.id}`,
      expect.objectContaining({ credentials: 'include', method: 'DELETE' }),
    )
  })

  it('preserves unsaved note text when creation fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'Notes are unavailable' }, 503),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    const composer = await screen.findByLabelText('New note')
    fireEvent.change(composer, { target: { value: 'Do not lose this' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add note' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Notes are unavailable',
    )
    expect(composer).toHaveValue('Do not lose this')
    expect(screen.getByRole('button', { name: 'Add note' })).toBeEnabled()
  })

  it('restores an authenticated session before showing the protected shell', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Restoring your session',
    )
    expect(
      await screen.findByRole('heading', { name: 'Notes' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Signed in as niki')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('signs in and opens the protected shell', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'Authentication required' }, 401),
      )
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'niki' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'secret' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Signed in as niki')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/auth/login',
      expect.objectContaining({
        body: JSON.stringify({ username: 'niki', password: 'secret' }),
        credentials: 'include',
        method: 'POST',
      }),
    )
  })

  it('routes between protected feature shells without reloading', async () => {
    window.history.replaceState(null, '', '/reminders')
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
        .mockResolvedValueOnce(jsonResponse([])),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Reminders' }),
    ).toBeInTheDocument()
    expect(screen.getByText('No upcoming reminders.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Lists' }))

    expect(screen.getByRole('heading', { name: 'Lists' })).toBeInTheDocument()
    expect(await screen.findByText('No lists yet.')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/lists')
  })

  it('logs out and returns to the protected login boundary', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/auth/logout',
      expect.objectContaining({ credentials: 'include', method: 'POST' }),
    )
  })

  it('shows a recoverable session restoration error', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Failed to fetch',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Signed in as niki')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('keeps the protected shell available when logout fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
        .mockResolvedValueOnce(jsonResponse([]))
        .mockResolvedValueOnce(
          jsonResponse({ detail: 'Could not sign out' }, 503),
        ),
    )

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not sign out',
    )
    expect(screen.getByRole('heading', { name: 'Notes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeEnabled()
  })
})
