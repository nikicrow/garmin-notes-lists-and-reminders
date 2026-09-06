const CACHE_PREFIX = 'tuck-'
const CACHE_NAME = `${CACHE_PREFIX}shell-v2`
const RUNTIME_CACHE = `${CACHE_PREFIX}runtime-v2`
const APP_SHELL = [
  '/manifest.webmanifest',
  '/icons/tuck-192.png',
  '/icons/tuck-512.png',
]

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
