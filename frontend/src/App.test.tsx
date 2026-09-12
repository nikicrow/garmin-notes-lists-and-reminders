import {
  act,
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
  it('creates a reminder for both selected household recipients', async () => {
    window.history.replaceState(null, '', '/reminders')
    const nikiId = '11111111-1111-1111-1111-111111111111'
    const benId = '22222222-2222-2222-2222-222222222222'
    const created = {
      id: '33333333-3333-3333-3333-333333333333',
      creator_user_id: nikiId,
      title: 'School pickup',
      detail: null,
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: false,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: [nikiId, benId],
      deliveries: [],
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse([
          { id: benId, username: 'ben' },
          { id: nikiId, username: 'niki' },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(created, 201))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Reminder title'), {
      target: { value: 'School pickup' },
    })
    fireEvent.change(screen.getByLabelText('Due date and time'), {
      target: { value: '2027-10-01T14:30' },
    })
    fireEvent.change(screen.getByLabelText('Timezone'), {
      target: { value: 'Australia/Brisbane' },
    })
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Ben' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))

    expect(
      await screen.findByText('Recipients: Ben and Niki'),
    ).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Niki' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Ben' })).not.toBeChecked()
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      '/api/v1/reminders',
      expect.objectContaining({
        body: JSON.stringify({
          title: 'School pickup',
          detail: null,
          due_at_utc: '2027-10-01T04:30:00.000Z',
          source_timezone: 'Australia/Brisbane',
          is_urgent: false,
          recipient_user_ids: [nikiId, benId],
        }),
        method: 'POST',
      }),
    )
  })

  it('shows forbidden feedback without losing the reminder draft', async () => {
    window.history.replaceState(null, '', '/reminders')
    const nikiId = '11111111-1111-1111-1111-111111111111'
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
        .mockResolvedValueOnce(jsonResponse([]))
        .mockResolvedValueOnce(jsonResponse([{ id: nikiId, username: 'niki' }]))
        .mockResolvedValueOnce(
          jsonResponse({ detail: 'Reminder recipients are forbidden' }, 403),
        ),
    )

    render(<App />)

    const title = await screen.findByLabelText('Reminder title')
    fireEvent.change(title, { target: { value: 'Private appointment' } })
    fireEvent.change(screen.getByLabelText('Due date and time'), {
      target: { value: '2027-10-01T14:30' },
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Add reminder' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Reminder recipients are forbidden',
    )
    expect(title).toHaveValue('Private appointment')
    expect(screen.getByRole('checkbox', { name: 'Niki' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Add reminder' })).toBeEnabled()
  })

  it('presents received reminders read-only with delivery history', async () => {
    window.history.replaceState(null, '', '/reminders')
    const nikiId = '11111111-1111-1111-1111-111111111111'
    const benId = '22222222-2222-2222-2222-222222222222'
    const received = {
      id: '33333333-3333-3333-3333-333333333333',
      creator_user_id: nikiId,
      title: 'School pickup',
      detail: null,
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: false,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: [benId],
      deliveries: [
        {
          recipient_user_id: benId,
          status: 'retryable',
          attempt_count: 2,
          next_attempt_at: '2027-10-01T04:35:00Z',
          sent_at: null,
          last_error_code: 'push_unavailable',
          updated_at: '2027-10-01T04:31:00Z',
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ username: 'ben' }))
        .mockResolvedValueOnce(jsonResponse([received]))
        .mockResolvedValueOnce(
          jsonResponse([
            { id: benId, username: 'ben' },
            { id: nikiId, username: 'niki' },
          ]),
        ),
    )

    render(<App />)

    expect(await screen.findByText('Recipients: Ben')).toBeInTheDocument()
    expect(
      screen.getByText('Delivery to Ben: Retry scheduled'),
    ).toBeInTheDocument()
    expect(screen.getByText('2 attempts')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Edit School pickup' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Complete School pickup' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Received from Niki')).toBeInTheDocument()
  })

  it('submits a reminder in the selected timezone', async () => {
    window.history.replaceState(null, '', '/reminders')
    const created = {
      id: '11111111-1111-1111-1111-111111111111',
      creator_user_id: '11111111-1111-1111-1111-111111111111',
      title: 'Dentist',
      detail: 'Bring paperwork',
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: true,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: ['11111111-1111-1111-1111-111111111111'],
      deliveries: [],
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse([
          { id: '22222222-2222-2222-2222-222222222222', username: 'ben' },
          { id: '11111111-1111-1111-1111-111111111111', username: 'niki' },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(created, 201))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Reminder title'), {
      target: { value: 'Dentist' },
    })
    fireEvent.change(screen.getByLabelText('Details'), {
      target: { value: 'Bring paperwork' },
    })
    fireEvent.change(screen.getByLabelText('Due date and time'), {
      target: { value: '2027-10-01T14:30' },
    })
    fireEvent.change(screen.getByLabelText('Timezone'), {
      target: { value: 'Australia/Brisbane' },
    })
    fireEvent.click(screen.getByLabelText('Urgent'))
    fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))

    expect(await screen.findByText('Dentist')).toBeInTheDocument()
    expect(
      screen.getByText('Urgent', { selector: 'strong' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Delivery status updates after reminders are due.'),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      '/api/v1/reminders',
      expect.objectContaining({
        body: JSON.stringify({
          title: 'Dentist',
          detail: 'Bring paperwork',
          due_at_utc: '2027-10-01T04:30:00.000Z',
          source_timezone: 'Australia/Brisbane',
          is_urgent: true,
          recipient_user_ids: ['11111111-1111-1111-1111-111111111111'],
        }),
        credentials: 'include',
        method: 'POST',
      }),
    )
  })

  it('does not overwrite a newly created reminder with a stale initial list', async () => {
    window.history.replaceState(null, '', '/reminders')
    const created = {
      id: '11111111-1111-1111-1111-111111111111',
      creator_user_id: '11111111-1111-1111-1111-111111111111',
      title: 'Dentist',
      detail: null,
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: false,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: ['11111111-1111-1111-1111-111111111111'],
      deliveries: [],
    }
    let resolveInitialList!: (response: Response) => void
    const initialList = new Promise<Response>((resolve) => {
      resolveInitialList = resolve
    })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockReturnValueOnce(initialList)
      .mockResolvedValueOnce(
        jsonResponse([
          { id: '11111111-1111-1111-1111-111111111111', username: 'niki' },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(created, 201))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Reminder title'), {
      target: { value: 'Dentist' },
    })
    fireEvent.change(screen.getByLabelText('Due date and time'), {
      target: { value: '2027-10-01T14:30' },
    })
    fireEvent.change(screen.getByLabelText('Timezone'), {
      target: { value: 'Australia/Brisbane' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))
    expect(await screen.findByText('Dentist')).toBeInTheDocument()

    await act(async () => resolveInitialList(jsonResponse([])))

    expect(screen.getByText('Dentist')).toBeInTheDocument()
  })

  it('does not duplicate a reminder returned by the concurrent initial list', async () => {
    window.history.replaceState(null, '', '/reminders')
    const created = {
      id: '11111111-1111-1111-1111-111111111111',
      creator_user_id: '11111111-1111-1111-1111-111111111111',
      title: 'Dentist',
      detail: null,
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: false,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: ['11111111-1111-1111-1111-111111111111'],
      deliveries: [],
    }
    let resolveInitialList!: (response: Response) => void
    let resolveCreate!: (response: Response) => void
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolveInitialList = resolve
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          { id: '11111111-1111-1111-1111-111111111111', username: 'niki' },
        ]),
      )
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolveCreate = resolve
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Reminder title'), {
      target: { value: 'Dentist' },
    })
    fireEvent.change(screen.getByLabelText('Due date and time'), {
      target: { value: '2027-10-01T14:30' },
    })
    fireEvent.change(screen.getByLabelText('Timezone'), {
      target: { value: 'Australia/Brisbane' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))

    await act(async () => resolveInitialList(jsonResponse([created])))
    expect(await screen.findByText('Dentist')).toBeInTheDocument()
    await act(async () => resolveCreate(jsonResponse(created, 201)))

    await waitFor(() => expect(screen.getAllByText('Dentist')).toHaveLength(1))
  })

  it('edits, snoozes, reschedules, completes, and cancels reminders', async () => {
    window.history.replaceState(null, '', '/reminders')
    const appointment = {
      id: '11111111-1111-1111-1111-111111111111',
      creator_user_id: '11111111-1111-1111-1111-111111111111',
      title: 'Appointment',
      detail: null,
      due_at_utc: '2027-10-01T04:30:00Z',
      source_timezone: 'Australia/Brisbane',
      is_urgent: false,
      status: 'pending',
      created_at: '2026-09-04T10:00:00Z',
      updated_at: '2026-09-04T10:00:00Z',
      completed_at: null,
      cancelled_at: null,
      recipient_user_ids: ['11111111-1111-1111-1111-111111111111'],
      deliveries: [],
    }
    const cancelMe = {
      ...appointment,
      id: '22222222-2222-2222-2222-222222222222',
      title: 'Cancel me',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ username: 'niki' }))
      .mockResolvedValueOnce(jsonResponse([appointment, cancelMe]))
      .mockResolvedValueOnce(
        jsonResponse([
          { id: '11111111-1111-1111-1111-111111111111', username: 'niki' },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ...appointment, title: 'Dentist', is_urgent: true }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...appointment,
          title: 'Dentist',
          is_urgent: true,
          due_at_utc: '2027-10-01T04:45:00Z',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...appointment,
          title: 'Dentist',
          is_urgent: true,
          due_at_utc: '2027-10-02T05:00:00Z',
          source_timezone: 'Australia/Sydney',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...appointment,
          title: 'Dentist',
          is_urgent: true,
          status: 'completed',
          completed_at: '2027-10-01T00:00:00Z',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...cancelMe,
          status: 'cancelled',
          cancelled_at: '2027-10-01T00:00:00Z',
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Appointment' }),
    )
    fireEvent.change(screen.getByLabelText('Edit reminder title'), {
      target: { value: 'Dentist' },
    })
    fireEvent.click(screen.getByLabelText('Edit urgent'))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Dentist')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `/api/v1/reminders/${appointment.id}`,
      expect.objectContaining({
        body: JSON.stringify({
          title: 'Dentist',
          detail: null,
          is_urgent: true,
        }),
        method: 'PATCH',
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Snooze Dentist' }))
    fireEvent.change(screen.getByLabelText('Snooze until'), {
      target: { value: '2027-10-01T14:45' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm snooze' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5))
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      `/api/v1/reminders/${appointment.id}/snooze`,
      expect.objectContaining({
        body: JSON.stringify({ due_at_utc: '2027-10-01T04:45:00.000Z' }),
        method: 'POST',
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reschedule Dentist' }))
    fireEvent.change(screen.getByLabelText('New due date and time'), {
      target: { value: '2027-10-02T15:00' },
    })
    fireEvent.change(screen.getByLabelText('New timezone'), {
      target: { value: 'Australia/Sydney' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reschedule' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6))
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      `/api/v1/reminders/${appointment.id}/reschedule`,
      expect.objectContaining({
        body: JSON.stringify({
          due_at_utc: '2027-10-02T05:00:00.000Z',
          source_timezone: 'Australia/Sydney',
        }),
        method: 'POST',
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Complete Dentist' }))
    expect(await screen.findByText('completed')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Edit Dentist' }),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Cancel me' }))
    expect(await screen.findByText('cancelled')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      `/api/v1/reminders/${cancelMe.id}/cancel`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

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
    expect(
      await screen.findByText('No upcoming reminders.'),
    ).toBeInTheDocument()

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
