// Run against the same-origin gateway/docs and migrated synthetic API.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.SWAGGER_ORIGIN || 'http://localhost:5189'
const output = process.env.SWAGGER_EVIDENCE || '/tmp/issue89-swagger-evidence'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const errors = []
    let logins = 0
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/token/login') logins++
    })
    const schema = await (await context.request.get(origin + '/openapi.json')).json()
    const me = schema.paths['/api/v1/me'].get
    const docsPath = `/docs?view=shared-session#/${me.tags[0]}/${me.operationId}`
    const operation = page
      .locator('.opblock-get')
      .filter({ has: page.locator('[data-path="/api/v1/me"]') })
    async function ready(authorized) {
      await page.waitForFunction(() => window.peopleGatorDocsReady && window.peopleGatorDocsAuth)
      if (authorized)
        await page.waitForFunction(() =>
          Boolean(window.ui.authSelectors.authorized().get('PeopleGatorBearer')),
        )
    }
    async function openOperation() {
      if (!(await operation.locator('.opblock-body').isVisible()))
        await operation.locator('.opblock-summary').click()
      if (await operation.getByRole('button', { name: 'Try it out', exact: true }).isVisible())
        await operation.getByRole('button', { name: 'Try it out', exact: true }).click()
    }
    async function execute() {
      await openOperation()
      const response = page.waitForResponse(
        (item) =>
          new URL(item.url()).pathname === '/api/v1/me' && item.request().method() === 'GET',
      )
      await operation.getByRole('button', { name: 'Execute', exact: true }).click()
      const result = await response
      assert.equal(result.status(), 200)
      const header = result.request().headers().authorization
      assert.ok(
        await page.evaluate(
          (value) => value === 'Bearer ' + sessionStorage.getItem('people-gator.access-token'),
          header,
        ),
        'Swagger must use the shared browser bearer',
      )
      assert.ok(
        !result.request().headers()['x-api-key'],
        'Browser bearer requests must not include API keys',
      )
      assert.ok((await result.json()).user_id)
    }
    async function signIn() {
      await page.getByLabel('Username').fill('test')
      await page.getByLabel('Password').fill('test')
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      await page.waitForURL(origin + docsPath)
      await ready(true)
    }

    await page.goto(origin + docsPath)
    await ready(false)
    assert.equal(logins, 0)
    await page.getByRole('button', { name: 'Authorize', exact: false }).first().click()
    await page.getByRole('link', { name: 'Sign in', exact: true }).waitFor()
    await page.screenshot({ path: `${output}/${label}-docs-sign-in.png` })
    await page.getByRole('link', { name: 'Sign in', exact: true }).focus()
    await page.keyboard.press('Enter')
    await page.waitForURL('**/login.html?**')
    assert.equal(new URL(page.url()).searchParams.get('return'), docsPath)
    assert.ok(!/access_token|refresh_token/.test(page.url()))
    await page.screenshot({ path: `${output}/${label}-docs-gateway.png` })
    await signIn()
    await execute()

    const oldRefresh = await page.evaluate(() =>
      sessionStorage.getItem('people-gator.refresh-token'),
    )
    await page.evaluate(() => sessionStorage.removeItem('people-gator.access-token'))
    await execute()
    assert.ok(
      await page.evaluate(
        (previous) => sessionStorage.getItem('people-gator.refresh-token') !== previous,
        oldRefresh,
      ),
      'Docs requests must rotate an expired access session',
    )
    // Collapse the operation before capturing; Swagger's Curl panel contains the token.
    await operation.locator('.opblock-summary').click()
    await operation.locator('.opblock-body').waitFor({ state: 'hidden' })
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `${output}/${label}-docs-authorized.png` })

    await page.goto(origin + '/people?q=Ada')
    await page.getByText('Ada Novak', { exact: true }).first().waitFor()
    assert.equal(await page.getByRole('button', { name: 'Sign out', exact: true }).count(), 0)
    await page.goto(origin + docsPath)
    await ready(true)
    await execute()
    assert.equal(logins, 1, 'The app session must be reused without another credential exchange')

    // Invalid saved sessions leave anonymous docs/API-key use available.
    await page.evaluate(() => {
      sessionStorage.removeItem('people-gator.access-token')
      sessionStorage.setItem('people-gator.refresh-token', 'expired')
    })
    const refused = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/token/refresh',
    )
    await page.reload()
    assert.equal((await refused).status(), 401)
    await page.waitForFunction(
      () => window.peopleGatorDocsAuth && !sessionStorage.getItem('people-gator.refresh-token'),
    )
    assert.equal(new URL(page.url()).pathname, '/docs')
    await page.getByRole('button', { name: 'Authorize', exact: false }).first().click()
    await page.getByRole('link', { name: 'Sign in', exact: true }).click()
    await page.waitForURL('**/login.html?**')
    assert.equal(new URL(page.url()).searchParams.get('return'), docsPath)
    await signIn()
    await execute()

    // Exercise real Swagger authorization state without provisioning usable API-key credentials.
    const keyOnly = await page.evaluate(async () => {
      const token = sessionStorage.getItem('people-gator.access-token')
      window.ui.preauthorizeApiKey('PeopleGatorAPIKey', 'docs-test-key')
      const request = await window.peopleGatorDocsAuth.intercept({
        url: location.origin + '/api/v1/me',
        headers: { Authorization: 'Bearer ' + token, 'X-API-Key': 'docs-test-key' },
      })
      return (
        !request.headers.Authorization &&
        request.headers['X-API-Key'] === 'docs-test-key' &&
        !window.ui.authSelectors.authorized().get('PeopleGatorBearer') &&
        Boolean(sessionStorage.getItem('people-gator.access-token'))
      )
    })
    assert.ok(keyOnly, 'API-key selection must clear only Swagger’s managed bearer')
    assert.deepEqual(errors, [])
    await context.close()
    console.log(
      `${label}: gateway return/hash, shared session, Try it out, refresh, recovery, API-key isolation and keyboard passed`,
    )
  }
} finally {
  await browser.close()
}
