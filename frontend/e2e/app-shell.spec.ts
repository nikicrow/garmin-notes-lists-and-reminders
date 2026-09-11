import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') {
      await route.fulfill({ json: { username: 'niki' } })
      return
    }
    if (
      path === '/api/v1/notes' ||
      path === '/api/v1/lists' ||
      path === '/api/v1/reminders'
    ) {
      await route.fulfill({ json: [] })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'Not found' } })
  })
})

test('navigates the authenticated app without horizontal overflow', async ({
  page,
}) => {
  await page.goto('/notes')

  await expect(page.getByRole('heading', { name: 'Notes' })).toBeVisible()
  await page.getByRole('link', { name: 'Lists' }).click()
  await expect(page).toHaveURL(/\/lists$/)
  await expect(page.getByRole('heading', { name: 'Lists' })).toBeVisible()
  await page.getByRole('link', { name: 'Reminders' }).click()
  await expect(page).toHaveURL(/\/reminders$/)
  await expect(page.getByRole('heading', { name: 'Reminders' })).toBeVisible()

  const hasHorizontalOverflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  )
  expect(hasHorizontalOverflow).toBe(false)
})

test('serves the manifest and registers the production service worker', async ({
  page,
}) => {
  await page.goto('/notes')

  const manifestHref = await page
    .locator('link[rel="manifest"]')
    .getAttribute('href')
  expect(manifestHref).toBe('/manifest.webmanifest')
  const manifestResponse = await page.request.get('/manifest.webmanifest')
  expect(manifestResponse.ok()).toBe(true)
  await expect
    .poll(async () =>
      page.evaluate(
        async () =>
          (await navigator.serviceWorker.getRegistration())?.active?.scriptURL,
      ),
    )
    .toContain('/sw.js')
})
