import { useEffect, useRef, useState } from 'react'

import {
  ApiError,
  authApi,
  householdApi,
  listsApi,
  notesApi,
  remindersApi,
  type HouseholdUser,
  type ListItem,
  type Note,
  type Reminder,
  type TuckList,
  type User,
} from './api'

type AuthState =
  | { status: 'checking' }
  | { status: 'guest' }
  | { status: 'authenticated'; user: User }
  | { status: 'error'; message: string }

function messageFor(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Something went wrong. Please try again.'
}

function LoginForm({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      onLogin(await authApi.login(username, password))
    } catch (caught) {
      setError(messageFor(caught))
      setSubmitting(false)
    }
  }

  return (
    <main className="centered-page">
      <form className="auth-card" onSubmit={(event) => void submit(event)}>
        <p className="eyebrow">Tuck</p>
        <h1>Sign in</h1>
        <p>Capture it before it disappears.</p>
        {error === null ? null : <p role="alert">{error}</p>}
        <label htmlFor="username">Username</label>
        <input
          autoComplete="username"
          id="username"
          onChange={(event) => setUsername(event.target.value)}
          required
          value={username}
        />
        <label htmlFor="password">Password</label>
        <input
          autoComplete="current-password"
          id="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
        <button disabled={submitting} type="submit">
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

function NotesPage() {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [newBody, setNewBody] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editBody, setEditBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void notesApi
      .list()
      .then((loadedNotes) => {
        if (active) setNotes(loadedNotes)
      })
      .catch(() => {
        if (active) setNotes([])
      })
    return () => {
      active = false
    }
  }, [])

  async function createNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await notesApi.create(newBody)
      setNotes((current) => [created, ...(current ?? [])])
      setNewBody('')
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editingId === null) return
    setSubmitting(true)
    setError(null)
    try {
      const edited = await notesApi.edit(editingId, editBody)
      setNotes(
        (current) =>
          current?.map((note) => (note.id === edited.id ? edited : note)) ?? [],
      )
      setEditingId(null)
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function archiveNote(noteId: string) {
    setSubmitting(true)
    setError(null)
    try {
      await notesApi.archive(noteId)
      setNotes((current) => current?.filter((note) => note.id !== noteId) ?? [])
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="notes-page" aria-labelledby="notes-heading">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Your space</p>
          <h1 id="notes-heading">Notes</h1>
        </div>
      </div>
      <form
        className="note-composer"
        onSubmit={(event) => void createNote(event)}
      >
        <label htmlFor="new-note">New note</label>
        <textarea
          id="new-note"
          onChange={(event) => setNewBody(event.target.value)}
          placeholder="What do you want to remember?"
          required
          rows={4}
          value={newBody}
        />
        <button disabled={submitting} type="submit">
          Add note
        </button>
      </form>
      {error === null ? null : <p role="alert">{error}</p>}
      {notes === null ? <p role="status">Loading notes…</p> : null}
      {notes?.length === 0 ? <p role="status">No notes yet.</p> : null}
      {notes === null || notes.length === 0 ? null : (
        <ul className="note-list" aria-label="Notes">
          {notes.map((note) => (
            <li className="note-card" key={note.id}>
              {editingId === note.id ? (
                <form onSubmit={(event) => void saveNote(event)}>
                  <label htmlFor={`edit-${note.id}`}>Edit note</label>
                  <textarea
                    id={`edit-${note.id}`}
                    onChange={(event) => setEditBody(event.target.value)}
                    required
                    rows={5}
                    value={editBody}
                  />
                  <div className="note-actions">
                    <button disabled={submitting} type="submit">
                      Save
                    </button>
                    <button
                      className="secondary-button"
                      disabled={submitting}
                      onClick={() => setEditingId(null)}
                      type="button"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <p className="note-body">{note.body}</p>
                  <div className="note-actions">
                    <button
                      className="secondary-button"
                      disabled={submitting}
                      onClick={() => {
                        setEditingId(note.id)
                        setEditBody(note.body)
                      }}
                      type="button"
                    >
                      Edit
                    </button>
                    <button
                      className="danger-button"
                      disabled={submitting}
                      onClick={() => void archiveNote(note.id)}
                      type="button"
                    >
                      Archive
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ListsPage() {
  const [lists, setLists] = useState<TuckList[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [items, setItems] = useState<ListItem[] | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newItem, setNewItem] = useState('')
  const [memberId, setMemberId] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editItemBody, setEditItemBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void listsApi
      .list()
      .then((loaded) => {
        if (active) setLists(loaded)
      })
      .catch((caught: unknown) => {
        if (active) {
          setLists([])
          setError(messageFor(caught))
        }
      })
    return () => {
      active = false
    }
  }, [])

  const selectedList = lists?.find((list) => list.id === selectedId) ?? null

  function replaceList(updated: TuckList) {
    setLists(
      (current) =>
        current?.map((list) => (list.id === updated.id ? updated : list)) ?? [],
    )
  }

  async function createList(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await listsApi.create(newTitle)
      setLists((current) => [created, ...(current ?? [])])
      setNewTitle('')
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function openList(list: TuckList) {
    setSelectedId(list.id)
    setItems(null)
    setError(null)
    try {
      setItems(await listsApi.listItems(list.id))
    } catch (caught) {
      setItems([])
      setError(messageFor(caught))
    }
  }

  async function renameList(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (renamingId === null) return
    setSubmitting(true)
    setError(null)
    try {
      replaceList(await listsApi.rename(renamingId, renameTitle))
      setRenamingId(null)
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function archiveList(list: TuckList) {
    setSubmitting(true)
    setError(null)
    try {
      await listsApi.archive(list.id)
      setLists(
        (current) => current?.filter((entry) => entry.id !== list.id) ?? [],
      )
      if (selectedId === list.id) {
        setSelectedId(null)
        setItems(null)
      }
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function share(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedList === null) return
    setSubmitting(true)
    setError(null)
    try {
      replaceList(await listsApi.share(selectedList.id, memberId))
      setMemberId('')
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function unshare(removedMemberId: string) {
    if (selectedList === null) return
    setSubmitting(true)
    setError(null)
    try {
      replaceList(await listsApi.unshare(selectedList.id, removedMemberId))
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function addItem(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedList === null) return
    setSubmitting(true)
    setError(null)
    try {
      const created = await listsApi.addItem(selectedList.id, newItem)
      setItems((current) => [...(current ?? []), created])
      setNewItem('')
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function updateItem(
    item: ListItem,
    changes: { body?: string; is_checked?: boolean },
  ) {
    if (selectedList === null) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await listsApi.editItem(selectedList.id, item.id, changes)
      setItems(
        (current) =>
          current?.map((entry) =>
            entry.id === updated.id ? updated : entry,
          ) ?? [],
      )
      if (changes.body !== undefined) setEditingItemId(null)
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function deleteItem(item: ListItem) {
    if (selectedList === null) return
    setSubmitting(true)
    setError(null)
    try {
      await listsApi.deleteItem(selectedList.id, item.id)
      setItems(
        (current) =>
          current
            ?.filter((entry) => entry.id !== item.id)
            .map((entry, position) => ({ ...entry, position })) ?? [],
      )
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function moveItem(index: number, offset: -1 | 1) {
    if (selectedList === null || items === null) return
    const destination = index + offset
    if (destination < 0 || destination >= items.length) return
    const reordered = [...items]
    ;[reordered[index], reordered[destination]] = [
      reordered[destination],
      reordered[index],
    ]
    setSubmitting(true)
    setError(null)
    try {
      setItems(await listsApi.reorderItems(selectedList.id, reordered))
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="lists-page" aria-labelledby="lists-heading">
      <div className="page-heading">
        <p className="eyebrow">Keep it together</p>
        <h1 id="lists-heading">Lists</h1>
      </div>
      <form
        className="inline-composer"
        onSubmit={(event) => void createList(event)}
      >
        <label htmlFor="new-list">New list</label>
        <div>
          <input
            id="new-list"
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Shopping"
            required
            value={newTitle}
          />
          <button disabled={submitting} type="submit">
            Add list
          </button>
        </div>
      </form>
      {error === null ? null : <p role="alert">{error}</p>}
      {lists === null ? <p role="status">Loading lists…</p> : null}
      {lists?.length === 0 ? <p role="status">No lists yet.</p> : null}
      {lists === null || lists.length === 0 ? null : (
        <ul className="resource-list" aria-label="Lists">
          {lists.map((list) => (
            <li
              className={selectedId === list.id ? 'selected' : ''}
              key={list.id}
            >
              {renamingId === list.id ? (
                <form
                  className="inline-editor"
                  onSubmit={(event) => void renameList(event)}
                >
                  <label htmlFor={`rename-${list.id}`}>List name</label>
                  <input
                    id={`rename-${list.id}`}
                    onChange={(event) => setRenameTitle(event.target.value)}
                    required
                    value={renameTitle}
                  />
                  <div className="compact-actions">
                    <button disabled={submitting} type="submit">
                      Save name
                    </button>
                    <button
                      className="secondary-button"
                      onClick={() => setRenamingId(null)}
                      type="button"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <h2>{list.title}</h2>
                  <p>
                    {list.shared_user_ids.length === 0
                      ? 'Private'
                      : `Shared with ${list.shared_user_ids.length}`}
                  </p>
                  <div className="compact-actions">
                    <button
                      aria-label={`Open ${list.title}`}
                      className="secondary-button"
                      onClick={() => void openList(list)}
                      type="button"
                    >
                      Open
                    </button>
                    <button
                      aria-label={`Rename ${list.title}`}
                      className="secondary-button"
                      onClick={() => {
                        setRenamingId(list.id)
                        setRenameTitle(list.title)
                      }}
                      type="button"
                    >
                      Rename
                    </button>
                    <button
                      aria-label={`Archive ${list.title}`}
                      className="danger-button"
                      disabled={submitting}
                      onClick={() => void archiveList(list)}
                      type="button"
                    >
                      Archive
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {selectedList === null ? null : (
        <section
          className="list-detail"
          aria-labelledby="selected-list-heading"
        >
          <div className="detail-heading">
            <div>
              <p className="eyebrow">Open list</p>
              <h2 id="selected-list-heading">{selectedList.title}</h2>
            </div>
            <button
              className="secondary-button"
              onClick={() => {
                setSelectedId(null)
                setItems(null)
              }}
              type="button"
            >
              Close
            </button>
          </div>
          <form
            className="inline-composer"
            onSubmit={(event) => void addItem(event)}
          >
            <label htmlFor="new-item">New item</label>
            <div>
              <input
                id="new-item"
                onChange={(event) => setNewItem(event.target.value)}
                required
                value={newItem}
              />
              <button disabled={submitting} type="submit">
                Add item
              </button>
            </div>
          </form>
          {items === null ? <p role="status">Loading items…</p> : null}
          {items?.length === 0 ? <p role="status">No items yet.</p> : null}
          {items === null || items.length === 0 ? null : (
            <ul
              className="item-list"
              aria-label={`${selectedList.title} items`}
            >
              {items.map((item, index) => (
                <li key={item.id}>
                  {editingItemId === item.id ? (
                    <form
                      className="inline-editor"
                      onSubmit={(event) => {
                        event.preventDefault()
                        void updateItem(item, { body: editItemBody })
                      }}
                    >
                      <label htmlFor={`edit-item-${item.id}`}>Edit item</label>
                      <input
                        id={`edit-item-${item.id}`}
                        onChange={(event) =>
                          setEditItemBody(event.target.value)
                        }
                        required
                        value={editItemBody}
                      />
                      <div className="compact-actions">
                        <button disabled={submitting} type="submit">
                          Save item
                        </button>
                        <button
                          className="secondary-button"
                          onClick={() => setEditingItemId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <label className="check-label">
                        <input
                          checked={item.completed_at !== null}
                          disabled={submitting}
                          onChange={() =>
                            void updateItem(item, {
                              is_checked: item.completed_at === null,
                            })
                          }
                          type="checkbox"
                        />
                        <span>{item.body}</span>
                      </label>
                      <div className="compact-actions">
                        <button
                          aria-label={`Move ${item.body} up`}
                          className="icon-button"
                          disabled={submitting || index === 0}
                          onClick={() => void moveItem(index, -1)}
                          type="button"
                        >
                          ↑
                        </button>
                        <button
                          aria-label={`Move ${item.body} down`}
                          className="icon-button"
                          disabled={submitting || index === items.length - 1}
                          onClick={() => void moveItem(index, 1)}
                          type="button"
                        >
                          ↓
                        </button>
                        <button
                          aria-label={`Edit ${item.body}`}
                          className="secondary-button"
                          onClick={() => {
                            setEditingItemId(item.id)
                            setEditItemBody(item.body)
                          }}
                          type="button"
                        >
                          Edit
                        </button>
                        <button
                          aria-label={`Delete ${item.body}`}
                          className="danger-button"
                          disabled={submitting}
                          onClick={() => void deleteItem(item)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
          <section className="sharing" aria-labelledby="sharing-heading">
            <h3 id="sharing-heading">Sharing</h3>
            <form
              className="inline-composer"
              onSubmit={(event) => void share(event)}
            >
              <label htmlFor="member-id">Share with user ID</label>
              <div>
                <input
                  id="member-id"
                  onChange={(event) => setMemberId(event.target.value)}
                  required
                  value={memberId}
                />
                <button disabled={submitting} type="submit">
                  Share
                </button>
              </div>
            </form>
            {selectedList.shared_user_ids.length === 0 ? (
              <p>Not shared.</p>
            ) : (
              <ul className="member-list">
                {selectedList.shared_user_ids.map((id) => (
                  <li key={id}>
                    <code>{id}</code>
                    <button
                      aria-label={`Remove access for ${id}`}
                      className="danger-button"
                      disabled={submitting}
                      onClick={() => void unshare(id)}
                      type="button"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </section>
      )}
    </section>
  )
}

function localTimeInTimezoneToUtc(localTime: string, timezone: string): string {
  const [date, time] = localTime.split('T')
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  const desired = Date.UTC(year, month - 1, day, hour, minute)
  let candidate = desired
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = Object.fromEntries(
      formatter
        .formatToParts(new Date(candidate))
        .filter((part) => part.type !== 'literal')
        .map((part) => [part.type, Number(part.value)]),
    )
    const represented = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
    )
    candidate += desired - represented
  }
  return new Date(candidate).toISOString()
}

function displayNames(userIds: string[], household: HouseholdUser[]): string {
  const selected = new Set(userIds)
  const names = household
    .filter((user) => selected.has(user.id))
    .map((user) => user.username)
  return new Intl.ListFormat('en', {
    style: 'long',
    type: 'conjunction',
  }).format(names.map((name) => name.charAt(0).toUpperCase() + name.slice(1)))
}

function deliveryStatusLabel(status: Reminder['deliveries'][number]['status']) {
  return {
    pending: 'Waiting',
    claimed: 'Sending',
    sent: 'Sent',
    retryable: 'Retry scheduled',
    failed: 'Failed',
  }[status]
}

function RemindersPage({ currentUsername }: { currentUsername: string }) {
  const [reminders, setReminders] = useState<Reminder[] | null>(null)
  const [household, setHousehold] = useState<HouseholdUser[] | null>(null)
  const [recipientUserIds, setRecipientUserIds] = useState<string[]>([])
  const mutationRevision = useRef(0)
  const [title, setTitle] = useState('')
  const [detail, setDetail] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [timezone, setTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  )
  const [urgent, setUrgent] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDetail, setEditDetail] = useState('')
  const [editUrgent, setEditUrgent] = useState(false)
  const [timingAction, setTimingAction] = useState<{
    id: string
    kind: 'snooze' | 'reschedule'
  } | null>(null)
  const [newDueAt, setNewDueAt] = useState('')
  const [newTimezone, setNewTimezone] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const requestedAtRevision = mutationRevision.current
    void remindersApi
      .list()
      .then((loaded) => {
        if (active && mutationRevision.current === requestedAtRevision) {
          setReminders(loaded)
        }
      })
      .catch((caught: unknown) => {
        if (active && mutationRevision.current === requestedAtRevision) {
          setReminders([])
          setError(messageFor(caught))
        }
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    void householdApi
      .users()
      .then((users) => {
        if (active) {
          setHousehold(users)
          const currentUser = users.find(
            (user) => user.username === currentUsername,
          )
          if (currentUser !== undefined) {
            setRecipientUserIds((current) =>
              current.length === 0 ? [currentUser.id] : current,
            )
          }
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setHousehold([])
          setError(messageFor(caught))
        }
      })
    return () => {
      active = false
    }
  }, [currentUsername])

  async function createReminder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await remindersApi.create({
        title,
        detail: detail || null,
        due_at_utc: localTimeInTimezoneToUtc(dueAt, timezone),
        source_timezone: timezone,
        is_urgent: urgent,
        recipient_user_ids: recipientUserIds,
      })
      mutationRevision.current += 1
      upsertReminder(created)
      setTitle('')
      setDetail('')
      setDueAt('')
      setUrgent(false)
      const currentUser = household?.find(
        (user) => user.username === currentUsername,
      )
      setRecipientUserIds(currentUser === undefined ? [] : [currentUser.id])
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  function upsertReminder(updated: Reminder) {
    setReminders((current) => {
      const existing = current ?? []
      if (!existing.some((reminder) => reminder.id === updated.id)) {
        return [...existing, updated]
      }
      return existing.map((reminder) =>
        reminder.id === updated.id ? updated : reminder,
      )
    })
  }

  async function saveReminder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editingId === null) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await remindersApi.edit(editingId, {
        title: editTitle,
        detail: editDetail || null,
        is_urgent: editUrgent,
      })
      mutationRevision.current += 1
      upsertReminder(updated)
      setEditingId(null)
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function changeStatus(
    reminder: Reminder,
    action: 'complete' | 'cancel',
  ) {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await remindersApi[action](reminder.id)
      mutationRevision.current += 1
      upsertReminder(updated)
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function changeTiming(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (timingAction === null) return
    setSubmitting(true)
    setError(null)
    try {
      const dueAtUtc = localTimeInTimezoneToUtc(newDueAt, newTimezone)
      const updated =
        timingAction.kind === 'snooze'
          ? await remindersApi.snooze(timingAction.id, dueAtUtc)
          : await remindersApi.reschedule(
              timingAction.id,
              dueAtUtc,
              newTimezone,
            )
      mutationRevision.current += 1
      upsertReminder(updated)
      setTimingAction(null)
      setNewDueAt('')
    } catch (caught) {
      setError(messageFor(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="reminders-page" aria-labelledby="reminders-heading">
      <div className="page-heading">
        <p className="eyebrow">Right on time</p>
        <h1 id="reminders-heading">Reminders</h1>
        <p className="phase-notice">
          Delivery status updates after reminders are due.
        </p>
      </div>
      <form
        className="reminder-composer"
        onSubmit={(event) => void createReminder(event)}
      >
        <label htmlFor="reminder-title">Reminder title</label>
        <input
          id="reminder-title"
          onChange={(event) => setTitle(event.target.value)}
          required
          value={title}
        />
        <label htmlFor="reminder-detail">Details</label>
        <textarea
          id="reminder-detail"
          onChange={(event) => setDetail(event.target.value)}
          rows={3}
          value={detail}
        />
        <label htmlFor="reminder-due">Due date and time</label>
        <input
          id="reminder-due"
          onChange={(event) => setDueAt(event.target.value)}
          required
          type="datetime-local"
          value={dueAt}
        />
        <label htmlFor="reminder-timezone">Timezone</label>
        <input
          id="reminder-timezone"
          onChange={(event) => setTimezone(event.target.value)}
          required
          value={timezone}
        />
        <label className="check-label">
          <input
            checked={urgent}
            onChange={(event) => setUrgent(event.target.checked)}
            type="checkbox"
          />
          <span>Urgent</span>
        </label>
        <fieldset>
          <legend>Recipients</legend>
          {household?.map((user) => (
            <label className="check-label" key={user.id}>
              <input
                checked={recipientUserIds.includes(user.id)}
                onChange={(event) =>
                  setRecipientUserIds((current) =>
                    event.target.checked
                      ? [...current, user.id]
                      : current.filter((id) => id !== user.id),
                  )
                }
                type="checkbox"
              />
              <span>
                {user.username.charAt(0).toUpperCase() + user.username.slice(1)}
              </span>
            </label>
          ))}
        </fieldset>
        <button
          disabled={
            submitting || household === null || recipientUserIds.length === 0
          }
          type="submit"
        >
          Add reminder
        </button>
      </form>
      {error === null ? null : <p role="alert">{error}</p>}
      {reminders === null ? <p role="status">Loading reminders…</p> : null}
      {reminders?.length === 0 ? (
        <p role="status">No upcoming reminders.</p>
      ) : null}
      {reminders === null || reminders.length === 0 ? null : (
        <ul className="reminder-list" aria-label="Reminders">
          {reminders.map((reminder) => (
            <li
              className={reminder.is_urgent ? 'urgent' : ''}
              key={reminder.id}
            >
              {editingId === reminder.id ? (
                <form
                  className="reminder-editor"
                  onSubmit={(event) => void saveReminder(event)}
                >
                  <label htmlFor={`edit-reminder-title-${reminder.id}`}>
                    Edit reminder title
                  </label>
                  <input
                    id={`edit-reminder-title-${reminder.id}`}
                    onChange={(event) => setEditTitle(event.target.value)}
                    required
                    value={editTitle}
                  />
                  <label htmlFor={`edit-reminder-detail-${reminder.id}`}>
                    Edit details
                  </label>
                  <textarea
                    id={`edit-reminder-detail-${reminder.id}`}
                    onChange={(event) => setEditDetail(event.target.value)}
                    rows={3}
                    value={editDetail}
                  />
                  <label className="check-label">
                    <input
                      checked={editUrgent}
                      onChange={(event) => setEditUrgent(event.target.checked)}
                      type="checkbox"
                    />
                    <span>Edit urgent</span>
                  </label>
                  <div className="compact-actions">
                    <button disabled={submitting} type="submit">
                      Save changes
                    </button>
                    <button
                      className="secondary-button"
                      onClick={() => setEditingId(null)}
                      type="button"
                    >
                      Close editor
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="reminder-heading">
                    <h2>{reminder.title}</h2>
                    {reminder.is_urgent ? <strong>Urgent</strong> : null}
                  </div>
                  {reminder.detail === null ? null : <p>{reminder.detail}</p>}
                  <p className="reminder-due">
                    Due {new Date(reminder.due_at_utc).toLocaleString()} (
                    {reminder.source_timezone})
                  </p>
                  <p>
                    Recipients:{' '}
                    {displayNames(reminder.recipient_user_ids, household ?? [])}
                  </p>
                  {household?.find((user) => user.username === currentUsername)
                    ?.id === reminder.creator_user_id ? null : (
                    <p>
                      Received from{' '}
                      {displayNames(
                        [reminder.creator_user_id],
                        household ?? [],
                      )}
                    </p>
                  )}
                  {reminder.deliveries.length === 0 ? (
                    <p>Delivery: Waiting until due</p>
                  ) : (
                    <ul aria-label={`Delivery history for ${reminder.title}`}>
                      {reminder.deliveries.map((delivery) => (
                        <li key={delivery.recipient_user_id}>
                          <p>
                            Delivery to{' '}
                            {displayNames(
                              [delivery.recipient_user_id],
                              household ?? [],
                            )}
                            : {deliveryStatusLabel(delivery.status)}
                          </p>
                          <p>
                            {delivery.attempt_count}{' '}
                            {delivery.attempt_count === 1
                              ? 'attempt'
                              : 'attempts'}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className={`status-badge ${reminder.status}`}>
                    {reminder.status}
                  </p>
                  {reminder.status === 'pending' &&
                  household?.find((user) => user.username === currentUsername)
                    ?.id === reminder.creator_user_id ? (
                    <div className="compact-actions">
                      <button
                        aria-label={`Edit ${reminder.title}`}
                        className="secondary-button"
                        onClick={() => {
                          setEditingId(reminder.id)
                          setEditTitle(reminder.title)
                          setEditDetail(reminder.detail ?? '')
                          setEditUrgent(reminder.is_urgent)
                        }}
                        type="button"
                      >
                        Edit
                      </button>
                      <button
                        aria-label={`Snooze ${reminder.title}`}
                        className="secondary-button"
                        onClick={() => {
                          setTimingAction({ id: reminder.id, kind: 'snooze' })
                          setNewTimezone(reminder.source_timezone)
                          setNewDueAt('')
                        }}
                        type="button"
                      >
                        Snooze
                      </button>
                      <button
                        aria-label={`Reschedule ${reminder.title}`}
                        className="secondary-button"
                        onClick={() => {
                          setTimingAction({
                            id: reminder.id,
                            kind: 'reschedule',
                          })
                          setNewTimezone(reminder.source_timezone)
                          setNewDueAt('')
                        }}
                        type="button"
                      >
                        Reschedule
                      </button>
                      <button
                        aria-label={`Complete ${reminder.title}`}
                        disabled={submitting}
                        onClick={() => void changeStatus(reminder, 'complete')}
                        type="button"
                      >
                        Complete
                      </button>
                      <button
                        aria-label={`Cancel ${reminder.title}`}
                        className="danger-button"
                        disabled={submitting}
                        onClick={() => void changeStatus(reminder, 'cancel')}
                        type="button"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : null}
                </>
              )}
              {timingAction?.id === reminder.id ? (
                <form
                  className="timing-editor"
                  onSubmit={(event) => void changeTiming(event)}
                >
                  <label htmlFor={`new-due-${reminder.id}`}>
                    {timingAction.kind === 'snooze'
                      ? 'Snooze until'
                      : 'New due date and time'}
                  </label>
                  <input
                    id={`new-due-${reminder.id}`}
                    onChange={(event) => setNewDueAt(event.target.value)}
                    required
                    type="datetime-local"
                    value={newDueAt}
                  />
                  {timingAction.kind === 'reschedule' ? (
                    <>
                      <label htmlFor={`new-timezone-${reminder.id}`}>
                        New timezone
                      </label>
                      <input
                        id={`new-timezone-${reminder.id}`}
                        onChange={(event) => setNewTimezone(event.target.value)}
                        required
                        value={newTimezone}
                      />
                    </>
                  ) : null}
                  <div className="compact-actions">
                    <button disabled={submitting} type="submit">
                      {timingAction.kind === 'snooze'
                        ? 'Confirm snooze'
                        : 'Confirm reschedule'}
                    </button>
                    <button
                      className="secondary-button"
                      onClick={() => setTimingAction(null)}
                      type="button"
                    >
                      Close timing editor
                    </button>
                  </div>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

const pages = {
  '/notes': { title: 'Notes', empty: 'No notes yet.' },
  '/lists': { title: 'Lists', empty: 'No lists yet.' },
  '/reminders': { title: 'Reminders', empty: 'No upcoming reminders.' },
} as const

type PagePath = keyof typeof pages

function pagePath(pathname: string): PagePath {
  return pathname in pages ? (pathname as PagePath) : '/notes'
}

function AuthenticatedShell({
  onLogout,
  user,
}: {
  onLogout: () => Promise<void>
  user: User
}) {
  const [path, setPath] = useState<PagePath>(() =>
    pagePath(window.location.pathname),
  )
  const [loggingOut, setLoggingOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (window.location.pathname !== path)
      window.history.replaceState(null, '', path)
    const onPopState = () => setPath(pagePath(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [path])

  function navigate(
    event: React.MouseEvent<HTMLAnchorElement>,
    destination: PagePath,
  ) {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return
    event.preventDefault()
    window.history.pushState(null, '', destination)
    setPath(destination)
  }

  async function logout() {
    setLoggingOut(true)
    setError(null)
    try {
      await onLogout()
    } catch (caught) {
      setError(messageFor(caught))
      setLoggingOut(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a
          className="brand"
          href="/notes"
          onClick={(event) => navigate(event, '/notes')}
        >
          Tuck
        </a>
        <div className="account">
          <p>Signed in as {user.username}</p>
          <button
            disabled={loggingOut}
            onClick={() => void logout()}
            type="button"
          >
            {loggingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </header>
      <nav aria-label="Primary navigation">
        {(Object.keys(pages) as PagePath[]).map((destination) => (
          <a
            aria-current={path === destination ? 'page' : undefined}
            href={destination}
            key={destination}
            onClick={(event) => navigate(event, destination)}
          >
            {pages[destination].title}
          </a>
        ))}
      </nav>
      <main className="page-content">
        {error === null ? null : <p role="alert">{error}</p>}
        {path === '/notes' ? (
          <NotesPage />
        ) : path === '/lists' ? (
          <ListsPage />
        ) : (
          <RemindersPage currentUsername={user.username} />
        )}
      </main>
    </div>
  )
}

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })
  const [restoreAttempt, setRestoreAttempt] = useState(0)

  useEffect(() => {
    let active = true
    void authApi
      .currentUser()
      .then((user) => {
        if (active) setAuth({ status: 'authenticated', user })
      })
      .catch((error: unknown) => {
        if (!active) return
        if (error instanceof ApiError && error.status === 401) {
          setAuth({ status: 'guest' })
        } else {
          setAuth({ status: 'error', message: messageFor(error) })
        }
      })
    return () => {
      active = false
    }
  }, [restoreAttempt])

  if (auth.status === 'checking') {
    return (
      <main className="centered-page">
        <p role="status">Restoring your session…</p>
      </main>
    )
  }

  if (auth.status === 'authenticated') {
    return (
      <AuthenticatedShell
        onLogout={async () => {
          await authApi.logout()
          setAuth({ status: 'guest' })
        }}
        user={auth.user}
      />
    )
  }

  if (auth.status === 'guest') {
    return (
      <LoginForm
        onLogin={(user) => setAuth({ status: 'authenticated', user })}
      />
    )
  }

  return (
    <main className="centered-page">
      <h1>Tuck</h1>
      <p role="alert">{auth.message}</p>
      <button
        onClick={() => {
          setAuth({ status: 'checking' })
          setRestoreAttempt((attempt) => attempt + 1)
        }}
        type="button"
      >
        Try again
      </button>
    </main>
  )
}
