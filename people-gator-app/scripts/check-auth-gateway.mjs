// Real issuer + twice-seeded resource API + Vite. See docs/AUTHENTICATION.md.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.AUTH_GATEWAY_ORIGIN || 'http://localhost:5189'
const output = process.env.AUTH_GATEWAY_EVIDENCE || '/tmp/issue89-evidence'
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
    page.on('pageerror', (e) => errors.push(e.message))
    await page.goto(origin + '/people?q=Ada')
    await page.waitForURL('**/login.html?**')
    assert.equal(new URL(page.url()).searchParams.get('return'), '/people?q=Ada')
    await page.getByLabel('Username').waitFor()
    await page.screenshot({ path: `${output}/${label}-login.png` })
    // Keyboard reaches the fields and submit control in natural order.
    await page.getByLabel('Username').focus()
    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').getAttribute('id'), 'password')
    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').textContent(), 'Sign in')
    await page.getByLabel('Username').fill('test')
    await page.getByLabel('Password').fill('incorrect')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.getByRole('alert').waitFor()
    await page.getByLabel('Username').fill('')
    await page.getByLabel('Password').fill('')
    await page.screenshot({ path: `${output}/${label}-failed.png` })
    await page.getByLabel('Username').fill('test')
    await page.getByLabel('Password').fill('test')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.waitForURL(origin + '/people?q=Ada')
    await page.getByText('Ada Novak', { exact: true }).first().waitFor()
    assert.equal(await page.getByRole('button', { name: 'Sign out', exact: true }).count(), 0)
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    )
    await page.screenshot({ path: `${output}/${label}-signed-in.png` })
    const oldRefresh = await page.evaluate(() =>
      sessionStorage.getItem('people-gator.refresh-token'),
    )
    await page.evaluate(() => sessionStorage.removeItem('people-gator.access-token'))
    await page.reload()
    await page.getByText('Ada Novak', { exact: true }).first().waitFor()
    const newRefresh = await page.evaluate(() =>
      sessionStorage.getItem('people-gator.refresh-token'),
    )
    assert.notEqual(oldRefresh, newRefresh)
    // Simulate an expired/restarted refresh session and recover through the gateway.
    await page.evaluate(() => {
      sessionStorage.removeItem('people-gator.access-token')
      sessionStorage.setItem('people-gator.refresh-token', 'expired')
    })
    await page.reload()
    await page.waitForURL('**/login.html?**')
    await page.getByRole('alert').waitFor()
    await page.screenshot({ path: `${output}/${label}-expired.png` })
    await page.getByLabel('Username').fill('test')
    await page.getByLabel('Password').fill('test')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.waitForURL(origin + '/people?q=Ada')
    await page.getByText('Ada Novak', { exact: true }).first().waitFor()
    assert.deepEqual(errors, [])
    await context.close()
    console.log(`${label}: login, failure, return, refresh, expiry recovery and keyboard passed`)
  }
} finally {
  await browser.close()
}
