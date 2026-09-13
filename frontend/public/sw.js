const CACHE_PREFIX = 'tuck-'
const CACHE_NAME = `${CACHE_PREFIX}shell-v2`
const RUNTIME_CACHE = `${CACHE_PREFIX}runtime-v2`
const APP_SHELL = [
  '/manifest.webmanifest',
  '/icons/tuck-192.png',
  '/icons/tuck-512.png',
]
const REMINDER_ID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i

function reminderNotification(payload) {
  if (
    payload === null ||
    typeof payload !== 'object' ||
    payload.data === null ||
    typeof payload.data !== 'object' ||
    !REMINDER_ID_PATTERN.test(payload.data.reminderId) ||
    payload.data.url !== '/reminders' ||
    !['normal', 'high'].includes(payload.data.urgency)
  ) {
    return null
  }

  const reminderId = payload.data.reminderId
  return {
    title: 'Tuck reminder',
    options: {
      body: 'You have a reminder.',
      data: { url: `/reminders?reminder=${encodeURIComponent(reminderId)}` },
      icon: '/icons/tuck-192.png',
      tag: `reminder-${reminderId}`,
    },
  }
}

self.addEventListener('push', (event) => {
  let notification = null
  try {
    notification = reminderNotification(event.data?.json())
  } catch {
    // Ignore malformed or non-JSON push messages.
  }
  event.waitUntil(
    notification === null
      ? Promise.resolve()
      : self.registration.showNotification(
          notification.title,
          notification.options,
        ),
  )
})

function notificationTarget(data) {
  if (
    data === null ||
    typeof data !== 'object' ||
    typeof data.url !== 'string'
  ) {
    return null
  }
  const target = new URL(data.url, self.location.origin)
  const reminderId = target.searchParams.get('reminder')
  if (
    target.origin !== self.location.origin ||
    target.pathname !== '/reminders' ||
    target.searchParams.size !== 1 ||
    reminderId === null ||
    !REMINDER_ID_PATTERN.test(reminderId)
  ) {
    return null
  }
  return target.href
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = notificationTarget(event.notification.data)
  if (target === null) return

  event.waitUntil(
    self.clients
      .matchAll({ includeUncontrolled: true, type: 'window' })
      .then(async (windows) => {
        const existing = windows.find(
          (client) => new URL(client.url).origin === self.location.origin,
        )
        if (existing === undefined) return self.clients.openWindow(target)
        await existing.navigate(target)
        return existing.focus()
      }),
  )
})

async function cacheAppShell() {
  const cache = await caches.open(CACHE_NAME)
  const response = await fetch('/')
  if (!response.ok) throw new Error('Could not fetch the app shell')

  await cache.put('/', response.clone())
  const html = await response.text()
  const assetUrls = [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
    .map((match) => match[1])
    .filter((path) => path.startsWith('/assets/'))

  await cache.addAll([...APP_SHELL, ...new Set(assetUrls)])
}

self.addEventListener('install', (event) => {
  // Let an update wait until existing tabs close instead of replacing code in use.
  event.waitUntil(cacheAppShell())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter(
              (name) =>
                name.startsWith(CACHE_PREFIX) &&
                name !== CACHE_NAME &&
                name !== RUNTIME_CACHE,
            )
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  if (
    event.request.method !== 'GET' ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith('/api/')
  ) {
    return
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/')))
    return
  }

  if (
    !['style', 'script', 'image', 'font'].includes(event.request.destination)
  ) {
    return
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached !== undefined) return cached

      return fetch(event.request).then((response) => {
        if (!response.ok) return response
        const copy = response.clone()
        void caches
          .open(RUNTIME_CACHE)
          .then((cache) => cache.put(event.request, copy))
        return response
      })
    }),
  )
})
