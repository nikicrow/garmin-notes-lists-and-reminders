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

test('completes the Phase 2 reminder workflow for both household users', async ({
  page,
}) => {
  const nikiId = '11111111-1111-1111-1111-111111111111'
  const benId = '22222222-2222-2222-2222-222222222222'
  const household = [
    { id: nikiId, username: 'niki' },
    { id: benId, username: 'ben' },
  ]
  let currentUsername = 'niki'
  let nextReminder = 1
  const reminders: Array<Record<string, unknown>> = []
  const subscriptions: string[] = []

  await page.addInitScript(() => {
    const browserSubscription = {
      toJSON: () => ({
        endpoint: 'https://push.example.test/subscriptions/e2e-browser',
        expirationTime: null,
        keys: { p256dh: 'browser-public-key', auth: 'browser-auth-secret' },
      }),
      unsubscribe: async () => true,
    }
    const registration = {
      pushManager: {
        getSubscription: async () => null,
        subscribe: async () => browserSubscription,
      },
    }
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: {
        permission: 'default',
        requestPermission: async () => 'granted',
      },
    })
    Object.defineProperty(window, 'PushManager', {
      configurable: true,
      value: class PushManager {},
    })
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        ready: Promise.resolve(registration),
        register: async () => registration,
      },
    })
  })

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me') {
      await route.fulfill({ json: { username: currentUsername } })
      return
    }
    if (path === '/api/v1/household/users') {
      await route.fulfill({ json: household })
      return
    }
    if (path === '/api/v1/push-subscriptions/vapid-public-key') {
      await route.fulfill({ json: { public_key: 'AQID' } })
      return
    }
    if (path === '/api/v1/push-subscriptions' && request.method() === 'POST') {
      subscriptions.push(currentUsername)
      await route.fulfill({
        status: 201,
        json: { id: `${currentUsername}-subscription`, expirationTime: null },
      })
      return
    }
    if (path === '/api/v1/reminders' && request.method() === 'GET') {
      const currentUserId = currentUsername === 'niki' ? nikiId : benId
      await route.fulfill({
        json: reminders.filter(
          (reminder) =>
            reminder.creator_user_id === currentUserId ||
            (reminder.recipient_user_ids as string[]).includes(currentUserId),
        ),
      })
      return
    }
    if (path === '/api/v1/reminders' && request.method() === 'POST') {
      const payload = request.postDataJSON() as {
        title: string
        detail: string | null
        due_at_utc: string
        source_timezone: string
        is_urgent: boolean
        recipient_user_ids: string[]
      }
      const id = `33333333-3333-3333-3333-${String(nextReminder++).padStart(12, '0')}`
      const reminder = {
        id,
        creator_user_id: nikiId,
        ...payload,
        status: 'pending',
        created_at: '2026-09-12T10:00:00Z',
        updated_at: '2026-09-12T10:00:00Z',
        completed_at: null,
        cancelled_at: null,
        deliveries: payload.recipient_user_ids.map((recipient_user_id) => ({
          recipient_user_id,
          status: 'sent',
          attempt_count: 1,
          next_attempt_at: null,
          sent_at: '2026-09-12T10:01:00Z',
          last_error_code: null,
          updated_at: '2026-09-12T10:01:00Z',
        })),
      }
      reminders.push(reminder)
      await route.fulfill({ status: 201, json: reminder })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'Not found' } })
  })

  const createReminder = async (title: string, recipients: string[]) => {
    await page.getByLabel('Reminder title').fill(title)
    await page.getByLabel('Due date and time').fill('2027-10-01T14:30')
    for (const name of ['Niki', 'Ben']) {
      const checkbox = page.getByRole('checkbox', { name })
      const shouldBeChecked = recipients.includes(name)
      if ((await checkbox.isChecked()) !== shouldBeChecked)
        await checkbox.click()
    }
    await page.getByRole('button', { name: 'Add reminder' }).click()
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
  }

  await page.goto('/reminders')
  await page.getByRole('button', { name: 'Enable notifications' }).click()
  await expect(
    page.getByText('Notifications are enabled on this device.'),
  ).toBeVisible()

  await createReminder('Niki only', ['Niki'])
  await createReminder('Ben only', ['Ben'])
  await createReminder('Everyone', ['Niki', 'Ben'])
  await expect(page.getByText('Delivery to Niki: Sent').last()).toBeVisible()
  await expect(page.getByText('Delivery to Ben: Sent').last()).toBeVisible()

  currentUsername = 'ben'
  await page.evaluate(() => window.localStorage.clear())
  const sharedReminderId = reminders[2].id as string
  await page.goto(`/reminders?reminder=${sharedReminderId}`)
  await expect(page.getByRole('heading', { name: 'Everyone' })).toBeVisible()
  await expect(page.locator(`#reminder-${sharedReminderId}`)).toBeFocused()
  await page.getByRole('button', { name: 'Enable notifications' }).click()
  await expect(
    page.getByText('Notifications are enabled on this device.'),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Niki only' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Ben only' })).toBeVisible()
  await expect(page.getByText('Recipients: Ben')).toBeVisible()
  await expect(page.getByText('Received from Niki')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Edit Everyone' })).toHaveCount(
    0,
  )
  await expect(
    page.getByRole('button', { name: 'Complete Everyone' }),
  ).toHaveCount(0)
  expect(subscriptions).toEqual(['niki', 'ben'])
})
