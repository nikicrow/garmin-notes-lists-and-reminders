/// <reference types="node" />
// @vitest-environment node

import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'

import { describe, expect, it, vi } from 'vitest'

type WorkerEvent = { waitUntil(promise: Promise<unknown>): void }
type WorkerListener = (event: WorkerEvent & Record<string, unknown>) => void

async function loadServiceWorker() {
  const listeners = new Map<string, WorkerListener>()
  const showNotification = vi.fn().mockResolvedValue(undefined)
  const clients = {
    claim: vi.fn(),
    matchAll: vi.fn(),
    openWindow: vi.fn(),
  }
  const self = {
    addEventListener: (type: string, listener: WorkerListener) =>
      listeners.set(type, listener),
    clients,
    location: { origin: 'https://tuck.example.test' },
    registration: { showNotification },
  }
  const caches = {
    delete: vi.fn(),
    keys: vi.fn(),
    match: vi.fn(),
    open: vi.fn(),
  }
  const source = await readFile(
    resolve(process.cwd(), 'public', 'sw.js'),
    'utf8',
  )
  runInNewContext(source, { caches, fetch: vi.fn(), self, Set, URL })
  return { clients, listeners, showNotification }
}

describe('notification service worker', () => {
  it('validates and displays a privacy-safe reminder notification', async () => {
    const worker = await loadServiceWorker()
    let operation: Promise<unknown> | undefined
    worker.listeners.get('push')?.({
      data: {
        json: () => ({
          title: 'Tuck reminder',
          body: 'You have a reminder.',
          data: {
            reminderId: '11111111-1111-1111-1111-111111111111',
            url: '/reminders',
            urgency: 'normal',
          },
        }),
      },
      waitUntil: (promise) => {
        operation = promise
      },
    })
    await operation

    expect(worker.showNotification).toHaveBeenCalledWith('Tuck reminder', {
      body: 'You have a reminder.',
      data: {
        url: '/reminders?reminder=11111111-1111-1111-1111-111111111111',
      },
      icon: '/icons/tuck-192.png',
      tag: 'reminder-11111111-1111-1111-1111-111111111111',
    })
  })

  it('ignores malformed or non-reminder push payloads', async () => {
    const worker = await loadServiceWorker()
    let operation: Promise<unknown> | undefined
    worker.listeners.get('push')?.({
      data: { json: () => ({ data: { url: 'https://evil.example.test' } }) },
      waitUntil: (promise) => {
        operation = promise
      },
    })
    await operation

    expect(worker.showNotification).not.toHaveBeenCalled()
  })

  it('routes notification clicks to the reminder deep link', async () => {
    const worker = await loadServiceWorker()
    const navigate = vi.fn().mockResolvedValue(undefined)
    const focus = vi.fn().mockResolvedValue(undefined)
    worker.clients.matchAll.mockResolvedValue([
      { url: 'https://tuck.example.test/notes', navigate, focus },
    ])
    const close = vi.fn()
    let operation: Promise<unknown> | undefined
    worker.listeners.get('notificationclick')?.({
      notification: {
        close,
        data: {
          url: '/reminders?reminder=11111111-1111-1111-1111-111111111111',
        },
      },
      waitUntil: (promise) => {
        operation = promise
      },
    })
    await operation

    expect(close).toHaveBeenCalledOnce()
    expect(navigate).toHaveBeenCalledWith(
      'https://tuck.example.test/reminders?reminder=11111111-1111-1111-1111-111111111111',
    )
    expect(focus).toHaveBeenCalledOnce()
    expect(worker.clients.openWindow).not.toHaveBeenCalled()
  })
})
