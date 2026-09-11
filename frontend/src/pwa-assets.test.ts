/// <reference types="node" />
// @vitest-environment node

import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const publicPath = (...parts: string[]) =>
  resolve(process.cwd(), 'public', ...parts)

describe('PWA assets', () => {
  it('provides an installable manifest with dedicated regular and maskable icons', async () => {
    const manifest = JSON.parse(
      await readFile(publicPath('manifest.webmanifest'), 'utf8'),
    ) as {
      id?: string
      name?: string
      short_name?: string
      start_url?: string
      scope?: string
      display?: string
      background_color?: string
      theme_color?: string
      icons?: Array<{
        src: string
        sizes: string
        type: string
        purpose?: string
      }>
    }

    expect(manifest).toMatchObject({
      id: '/',
      name: 'Tuck',
      short_name: 'Tuck',
      start_url: '/notes',
      scope: '/',
      display: 'standalone',
      background_color: '#f5f1e8',
      theme_color: '#245c46',
    })
    expect(manifest.icons).toEqual(
      expect.arrayContaining([
        {
          src: '/icons/tuck-192.png',
          sizes: '192x192',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/icons/tuck-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/icons/tuck-maskable-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ]),
    )

    await Promise.all(
      manifest.icons?.map(({ src }) =>
        expect(
          readFile(publicPath(src.replace(/^\//, ''))),
        ).resolves.not.toThrow(),
      ) ?? [],
    )
  })

  it('caches the app shell without caching API or mutation responses', async () => {
    const serviceWorker = await readFile(publicPath('sw.js'), 'utf8')

    expect(serviceWorker).toContain('const APP_SHELL = [')
    expect(serviceWorker).toContain("url.pathname.startsWith('/api/')")
    expect(serviceWorker).toContain("event.request.method !== 'GET'")
    expect(serviceWorker).toContain("event.request.mode === 'navigate'")
    expect(serviceWorker).toContain('await response.text()')
    expect(serviceWorker).toContain("startsWith('/assets/')")
    expect(serviceWorker).not.toContain('self.skipWaiting()')
  })
})
