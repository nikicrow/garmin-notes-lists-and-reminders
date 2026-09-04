import { useEffect, useState } from 'react'

import { ApiError, authApi, type User } from './api'

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
  const page = pages[path]

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
        <h1>{page.title}</h1>
        <p role="status">{page.empty}</p>
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
