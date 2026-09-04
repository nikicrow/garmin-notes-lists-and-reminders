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
      vi.fn().mockResolvedValue(jsonResponse({ username: 'niki' })),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Reminders' }),
    ).toBeInTheDocument()
    expect(screen.getByText('No upcoming reminders.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Lists' }))

    expect(screen.getByRole('heading', { name: 'Lists' })).toBeInTheDocument()
    expect(screen.getByText('No lists yet.')).toBeInTheDocument()
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
