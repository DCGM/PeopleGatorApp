// Run against this revision's migrated, twice-seeded synthetic instance.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.PAGE_STRIP_ORIGIN || 'http://127.0.0.1:5131'
const output = process.env.PAGE_STRIP_EVIDENCE || '../docs/evidence/issue131'
const root = '/libraries/preview-page-strip/documents/ac6cd0ec-bfc4-50ad-9a0c-f0059f2d6fe3/pages/'
const first = 'f5e304eb-38a6-5465-8dc0-4c78fda0f397'
let person
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
try {
  console.log(`Chromium ${browser.version()}`)
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const capture = async (state) => {
      await page.waitForFunction(
        () =>
          !document.querySelector(
            '.document-page-gallery [data-slot=loadable-image][data-state=loading]',
          ),
      )
      await page.screenshot({ animations: 'disabled', path: `${output}/${label}-${state}.png` })
    }
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(origin + root + first)
    const strip = page.getByRole('navigation', { name: 'Document pages' })
    await strip.locator('ol a').first().waitFor()
    await page.waitForFunction(() =>
      document.querySelector('.document-page-gallery h2')?.textContent.includes('18 pages'),
    )
    await capture('highlights')
    assert.equal(await strip.locator('ol a[aria-label*="unassigned"]').count(), 2)
    if (label === 'mobile') {
      const toggle = strip.getByRole('button', { name: 'Show filters', exact: true })
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false')
      await toggle.focus()
      await page.keyboard.press('Enter')
      await strip.getByRole('button', { name: 'Filter pages by person' }).waitFor()
    }
    await strip.getByRole('button', { name: 'Filter pages by person' }).click()
    const search = page.getByPlaceholder('Search people…', { exact: true })
    await search.fill('Nora Page')
    const option = page.getByRole('option', { name: 'Nora Page', exact: true })
    await option.waitFor()
    await option.click()
    await page.locator('[data-slot="combobox-list"]').waitFor({ state: 'detached' })
    await page.waitForURL((url) => Boolean(url.searchParams.get('gallery_person')))
    person = new URL(page.url()).searchParams.get('gallery_person')
    await page.waitForFunction(() =>
      document.querySelector('.document-page-gallery h2')?.textContent.includes('15 pages'),
    )
    assert.equal(
      await strip.locator('ol a[aria-current=page]').count(),
      0,
      'excluded current scan stays open',
    )
    assert.equal(new URL(page.url()).pathname, root + first)
    await strip.getByRole('button', { name: 'Remove Person: Nora Page' }).waitFor()
    await capture('person-filter')
    if (label === 'mobile') {
      await strip.getByRole('button', { name: 'Hide filters', exact: true }).click()
      await capture('person-collapsed')
      assert.equal(
        await strip.getByRole('button', { name: 'Remove Person: Nora Page' }).isVisible(),
        true,
      )
    }
    // The second matching page is mention-only; navigate there and keep filter state.
    const mentionOnly = strip.locator('ol a').nth(1)
    const mentionTarget = await mentionOnly.getAttribute('href')
    assert.ok(mentionTarget.includes(`gallery_person=${person}`))
    await mentionOnly.click()
    await page.waitForURL((url) => url.pathname !== root + first)
    assert.equal(new URL(page.url()).searchParams.get('gallery_person'), person)
    await page.reload()
    await strip.locator('ol a').first().waitFor()
    await strip.getByRole('button', { name: 'Remove Person: Nora Page' }).click()
    await page.waitForFunction(() =>
      document.querySelector('.document-page-gallery h2')?.textContent.includes('18 pages'),
    )
    await page.goBack()
    await page.waitForFunction(() =>
      document.querySelector('.document-page-gallery h2')?.textContent.includes('15 pages'),
    )
    // A valid but unknown entity must produce an empty strip, not all pages.
    await page.goto(origin + root + first + '?gallery_person=00000000-0000-4000-8000-000000000099')
    await strip.getByText('No matching pages.', { exact: true }).waitFor()
    await capture('empty')
    assert.equal(await strip.locator('ol a').count(), 0)
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    )
    // Unknown-person tag remains usable even with mobile controls collapsed.
    await strip.getByRole('button', { name: /Remove Person:/ }).click()
    await page.waitForFunction(() =>
      document.querySelector('.document-page-gallery h2')?.textContent.includes('18 pages'),
    )
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await capture('dark')
    assert.deepEqual(errors, [])
    console.log(
      `${label}: highlights, person search, mention-only navigation, URL/history, empty selection, mobile controls, no overflow passed`,
    )
    await context.close()
  }
} finally {
  await browser.close()
}
