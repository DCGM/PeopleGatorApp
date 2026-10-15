const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const path = require('node:path')

// Capture only a disposable local instance; never submit fixture credentials remotely.
const base = process.env.STAGING_CAPTURE_URL || 'http://127.0.0.1:18116'
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const fixturePassword = process.env.STAGING_CAPTURE_PASSWORD || 'synthetic-local-password-only'
;(async () => {
  const browser = await chromium.launch({ headless: true })
  const results = []
  for (const [name, viewport] of Object.entries({ desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } })) {
    const context = await browser.newContext({ viewport, colorScheme: 'light' })
    const page = await context.newPage()
    await page.goto(base + '/staging-login.html')
    await page.getByRole('heading', { name: 'Sign in to staging' }).waitFor()
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: path.join(__dirname, `login-${name}.png`) })
    await page.getByLabel('Account').focus()
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    assert.equal(await page.getByLabel('Account').inputValue(), 'staging-annotator')
    assert.match(await page.locator('#permissions').textContent(), /browse, annotate/)
    await page.screenshot({ path: path.join(__dirname, `permissions-${name}.png`) })
    await page.getByLabel('Password').fill('incorrect-synthetic-password')
    await page.getByLabel('Password').press('Enter')
    await page.getByRole('status').filter({ hasText: 'Unable to sign in' }).waitFor()
    assert(await page.getByLabel('Password').evaluate((el) => el === document.activeElement))
    await page.getByLabel('Password').fill('')
    await page.screenshot({ path: path.join(__dirname, `error-${name}.png`) })
    await page.getByLabel('Password').fill(fixturePassword)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.waitForURL('**/scans')
    const claims = await page.evaluate(() => JSON.parse(atob(sessionStorage.getItem('people-gator.access-token').split('.')[1])))
    assert.equal(claims.sub, 'staging-annotator')
    assert.equal(claims.scopes, 'people-gator:browse people-gator:annotate')
    await page.goto(base + '/people')
    await page.getByText(/Staging entity /).first().waitFor()
    results.push({ viewport, keyboard: true, overflow: false, failedLogin: true, authenticatedApp: true })
    await context.close()
  }
  for (const [name, viewport] of Object.entries({ desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } })) {
    const context = await browser.newContext({ viewport, colorScheme: 'dark' })
    const page = await context.newPage()
    await page.goto(base + '/staging-login.html')
    await page.screenshot({ path: path.join(__dirname, `login-dark-${name}.png`) })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await context.close()
  }
  // Viewer scope is restricted by the actual backend, independent of the UI.
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(base + '/staging-login.html')
  await page.getByLabel('Password').fill(fixturePassword)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL('**/scans')
  assert.equal(await page.evaluate(() => JSON.parse(atob(sessionStorage.getItem('people-gator.access-token').split('.')[1])).scopes), 'people-gator:browse')
  const denied = await page.evaluate(async () => {
    const token = sessionStorage.getItem('people-gator.access-token')
    const response = await fetch('/api/v1/entities', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Should be denied', entity_type: 'person' }) })
    return response.status
  })
  assert.equal(denied, 403)
  await context.close()
  await browser.close()
  console.log(JSON.stringify({ results, viewerMutationDenied: true }, null, 2))
})().catch((error) => { console.error(error); process.exitCode = 1 })
