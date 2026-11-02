// Real OIDC/PKCE browser journey. Works unchanged with the built-in issuer or Keycloak.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.OIDC_APP_ORIGIN || 'http://localhost:5189'
const authority = process.env.OIDC_AUTHORITY || origin
const output = process.env.OIDC_EVIDENCE || '/tmp/issue89-oidc-evidence'
const username = process.env.OIDC_TEST_USERNAME || 'test'
const password = process.env.OIDC_TEST_PASSWORD || 'test'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
let stage = 'initialization'
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const metadata = await (
      await context.request.get(authority + '/.well-known/openid-configuration')
    ).json()
    const schema = await (await context.request.get(origin + '/openapi.json')).json()
    const operation = schema.paths['/api/v1/me'].get
    const docsPath = `/docs?view=oidc#/${operation.tags[0]}/${operation.operationId}`
    const errors = []
    let latestToken,
      refreshes = 0,
      pkceRequests = 0
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.origin + url.pathname === metadata.authorization_endpoint) {
        assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
        assert.ok(url.searchParams.get('code_challenge'))
        assert.ok(url.searchParams.get('state'))
        assert.ok(url.searchParams.get('nonce'))
        pkceRequests++
      }
    })
    page.on('response', async (response) => {
      if (response.url() !== metadata.token_endpoint || response.status() !== 200) return
      latestToken = await response.json()
      if (
        new URLSearchParams(response.request().postData() || '').get('grant_type') ===
        'refresh_token'
      )
        refreshes++
    })
    async function ready(authorized = true) {
      await page.waitForFunction(() => window.peopleGatorDocsReady && window.peopleGatorDocsAuth)
      if (authorized)
        await page.waitForFunction(() =>
          Boolean(window.ui.authSelectors.authorized().get('PeopleGatorBearer')),
        )
    }
    async function noStoredTokens() {
      const stored = await page.evaluate(() => [
        ...Object.values(sessionStorage),
        ...Object.values(localStorage),
      ])
      assert.ok(stored.every((value) => !/"(?:access_token|refresh_token|id_token)"/.test(value)))
      for (const token of [
        latestToken?.access_token,
        latestToken?.refresh_token,
        latestToken?.id_token,
      ]) {
        if (token) assert.ok(stored.every((value) => !value.includes(token)))
      }
      const params = new URL(page.url()).searchParams
      for (const key of ['access_token', 'refresh_token', 'id_token', 'code', 'state'])
        assert.equal(params.has(key), false)
    }
    stage = label + ': anonymous docs'
    await page.goto(origin + docsPath)
    await ready(false)
    assert.equal(pkceRequests, 0)
    await page.locator('button.authorize').first().click()
    await page.getByRole('link', { name: 'Sign in', exact: true }).waitFor()
    await page.screenshot({ path: `${output}/${label}-docs-sign-in.png` })
    await page.getByRole('link', { name: 'Sign in', exact: true }).focus()
    await page.keyboard.press('Enter')
    stage = label + ': issuer form'
    await page.locator('[name=username]').waitFor()
    assert.equal(new URL(page.url()).origin, new URL(authority).origin)
    if (
      new URL(authority).hostname === new URL(origin).hostname &&
      !authority.includes('/realms/')
    ) {
      const preview = /^pr-\d+\.preview\.peoplegator\.dev$/.test(new URL(origin).hostname)
      assert.equal(await page.locator('[name=username]').inputValue(), preview ? 'test' : '')
      assert.equal(await page.locator('[name=password]').inputValue(), preview ? 'test' : '')
    }
    await page.screenshot({ path: `${output}/${label}-issuer-login.png` })
    await page.locator('[name=username]').focus()
    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').getAttribute('name'), 'password')
    if (metadata.authorization_endpoint.endsWith('/token/authorize')) {
      await page.locator('[name=username]').fill(username)
      await page.locator('[name=password]').fill('incorrect')
      await page.getByRole('button', { name: /^sign in$/i }).click()
      await page.getByRole('alert').waitFor()
      await page.screenshot({ path: `${output}/${label}-issuer-failed.png` })
    }
    await page.locator('[name=username]').fill(username)
    await page.locator('[name=password]').fill(password)
    await page.getByRole('button', { name: /^sign in$/i }).click()
    stage = label + ': code callback and docs return'
    await ready()
    assert.equal(page.url(), origin + docsPath)
    await noStoredTokens()
    const me = page
      .locator('.opblock-get')
      .filter({ has: page.locator('[data-path="/api/v1/me"]') })
    if (!(await me.locator('.try-out__btn').count())) await me.locator('.opblock-summary').click()
    await me.locator('.try-out__btn').click()
    let protectedResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/me' && response.request().method() === 'GET',
    )
    await me.locator('button.execute').click()
    assert.equal((await protectedResponse).status(), 200)
    stage = label + ': refresh before Try it out'
    const before = refreshes
    await page.clock.install({ time: Date.now() })
    await page.clock.setFixedTime(new Date(Date.now() + (latestToken.expires_in - 20) * 1000))
    protectedResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/me' && response.request().method() === 'GET',
    )
    await me.locator('button.execute').click()
    assert.equal((await protectedResponse).status(), 200)
    assert.equal(refreshes, before + 1)
    await page.clock.setFixedTime(new Date())
    // Collapse token-bearing Curl output before capturing the overview.
    await me.locator('.opblock-summary').click()
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `${output}/${label}-docs-authorized.png` })
    stage = label + ': application SSO'
    await page.goto(origin + '/people?q=Ada')
    await page.getByText('Ada Novak', { exact: true }).first().waitFor()
    assert.equal(page.url(), origin + '/people?q=Ada')
    assert.equal(await page.getByRole('button', { name: 'Sign out', exact: true }).count(), 0)
    await noStoredTokens()
    await page.screenshot({ path: `${output}/${label}-app-return.png` })
    stage = label + ': docs SSO'
    await page.goto(origin + docsPath)
    await ready()
    await noStoredTokens()
    stage = label + ': manual API-key isolation'
    const manual = await page.evaluate(async () => {
      const token = window.ui.authSelectors.authorized().get('PeopleGatorBearer').get('value')
      window.ui.preauthorizeApiKey('PeopleGatorAPIKey', 'synthetic-check-key')
      const request = await window.peopleGatorDocsAuth.intercept({
        url: location.origin + '/api/v1/me',
        headers: { Authorization: 'Bearer ' + token, 'X-API-Key': 'synthetic-check-key' },
      })
      return {
        headers: request.headers,
        hasBearer: Boolean(window.ui.authSelectors.authorized().get('PeopleGatorBearer')),
      }
    })
    assert.deepEqual(manual.headers, { 'X-API-Key': 'synthetic-check-key' })
    assert.equal(manual.hasBearer, false)
    stage = label + ': provider logout'
    const logout = new URL(metadata.end_session_endpoint)
    logout.search = new URLSearchParams({
      id_token_hint: latestToken.id_token,
      post_logout_redirect_uri: origin + '/login.html',
      client_id: 'people-gator-browser',
    }).toString()
    await page.goto(logout.href)
    await page.locator('[name=username]').waitFor()
    await page.screenshot({ path: `${output}/${label}-signed-out.png` })
    // A tab still carrying its non-secret SSO hint must recover anonymously
    // when the issuer session has ended, without another redirect loop.
    stage = label + ': expired SSO recovery'
    await page.goto(origin + docsPath)
    await ready(false)
    await page.waitForTimeout(300)
    assert.equal(page.url(), origin + docsPath)
    assert.equal(
      await page.evaluate(() =>
        Boolean(window.ui.authSelectors.authorized().get('PeopleGatorBearer')),
      ),
      false,
    )
    await page.locator('button.authorize').first().click()
    await page.getByRole('link', { name: 'Sign in', exact: true }).waitFor()
    await page.screenshot({ path: `${output}/${label}-docs-expired.png` })
    assert.deepEqual(errors, [])
    await context.close()
    console.log(
      `${label}: OIDC/S256 callback, return, Try it out, refresh, app/docs SSO, manual key isolation, logout, expiry recovery and no stored tokens passed`,
    )
  }
} catch {
  console.error('OIDC browser check failed at ' + stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
