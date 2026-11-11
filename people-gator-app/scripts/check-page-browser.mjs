// Exercise this revision's real, migrated/twice-seeded synthetic application.
import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.PAGE_BROWSER_ORIGIN || 'http://127.0.0.1:5140'
const seed = JSON.parse(
  await readFile(
    process.env.PAGE_BROWSER_SEED || '../people-gator-api/.cache/seed-report.json',
    'utf8',
  ),
)
const output = process.env.PAGE_BROWSER_EVIDENCE || '../docs/evidence/issue140'
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const gallery = page.getByRole('navigation', { name: 'Document pages', exact: true })
    const settled = async () => {
      await gallery.locator('ol a').first().waitFor()
      await page.waitForFunction(
        () =>
          !document.querySelector(
            '.document-page-gallery [data-slot="loadable-image"][data-state="loading"], .document-page-gallery [data-page-thumbnail][aria-busy="true"]',
          ),
      )
    }
    const capture = async (state) => {
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `${output}/${label}-${state}.png`, animations: 'disabled' })
    }
    await page.goto(origin + seed.filter_examples['page-strip-current-assigned'])
    await settled()
    await capture('compact')
    const viewer = page.locator('.workspace-viewer')
    await gallery.getByRole('button', { name: 'Expand pages', exact: true }).click()
    await page.waitForURL((url) => url.searchParams.get('pages_view') === 'expanded')
    assert.equal(await viewer.isVisible(), false)
    assert.equal(await gallery.getAttribute('data-expanded'), 'true')
    assert.equal(
      await gallery.getByRole('button', { name: 'Collapse pages' }).getAttribute('aria-expanded'),
      'true',
    )
    await settled()
    const viewport = gallery.getByLabel('Document pages grid', { exact: true })
    const layout = await gallery.locator('ol a').evaluateAll((links) =>
      links.slice(0, 5).map((link) => ({
        left: link.getBoundingClientRect().left,
        top: link.getBoundingClientRect().top,
      })),
    )
    assert.ok(
      layout[1].left > layout[0].left && Math.abs(layout[1].top - layout[0].top) < 1,
      'row-first grid starts left-to-right',
    )
    const bounds = await viewport.boundingBox()
    assert.ok(bounds.height > 250, 'expanded grid fills available viewer height')
    assert.ok(
      await gallery
        .locator('a[aria-current="page"] [data-page-thumbnail]')
        .evaluate((node) => getComputedStyle(node).borderTopWidth === '2px'),
    )
    assert.ok(
      await gallery
        .locator('a:not([aria-current="page"]) [data-person-match="true"]')
        .first()
        .evaluate((node) => getComputedStyle(node).borderTopWidth === '0px'),
    )
    assert.ok(
      await gallery.locator('[data-page-thumbnail]').evaluateAll((frames) => {
        const viewport = frames[0]
          .closest('[data-slot=scroll-area-viewport]')
          .getBoundingClientRect()
        return frames.every((frame) => frame.getBoundingClientRect().right <= viewport.right - 8)
      }),
      'thumbnail outlines stay clear of the vertical scrollbar',
    )
    await capture('expanded')
    await page.reload()
    await settled()
    assert.equal(await viewer.isVisible(), false)
    await gallery.getByRole('button', { name: 'Collapse pages', exact: true }).focus()
    await page.keyboard.press('Enter')
    await page.waitForURL((url) => !url.searchParams.has('pages_view'))
    assert.equal(await viewer.isVisible(), true)
    await page.goBack()
    await page.waitForURL((url) => url.searchParams.get('pages_view') === 'expanded')
    await settled()
    await viewport.evaluate((node) => node.scrollTo({ top: node.scrollHeight }))
    await page.waitForFunction(
      () => document.querySelectorAll('.document-page-gallery ol a').length === 18,
    )
    assert.equal(await gallery.locator('ol a').count(), 18, 'scroll reaches all cursor batches')
    await page.goto(origin + seed.filter_examples['document-page-browser-person'])
    await settled()
    assert.equal(await viewer.isVisible(), false)
    assert.equal(
      await gallery.locator('a[aria-current="page"]').count(),
      0,
      'excluded current page stays open',
    )
    assert.ok((await gallery.locator('[data-person-match="true"]').count()) > 0)
    await capture('person-only')
    await viewport.evaluate((node) => node.scrollTo({ top: node.scrollHeight }))
    await page.waitForFunction(
      () => document.querySelectorAll('.document-page-gallery ol a').length === 15,
    )
    const target = gallery.locator('ol a').first()
    const href = await target.getAttribute('href')
    assert.ok(href.includes('gallery_person_only=on') && href.includes('selectedPerson='))
    assert.ok(!href.includes('pages_view='), 'opening a page returns to viewer')
    await target.click()
    await page.waitForURL((url) => !url.searchParams.has('pages_view'))
    await settled()
    assert.equal(await viewer.isVisible(), true)
    assert.equal(new URL(page.url()).searchParams.get('gallery_person_only'), 'on')
    await page.goBack()
    await page.waitForURL((url) => url.searchParams.get('pages_view') === 'expanded')
    await settled()
    await page.goto(origin + seed.filter_examples['document-page-browser-missing-media'])
    await page.waitForURL(
      (url) =>
        url.pathname.startsWith('/libraries/') && url.searchParams.get('pages_view') === 'expanded',
    )
    await settled()
    await gallery
      .locator('a[aria-current="page"]')
      .getByText('No preview', { exact: true })
      .waitFor()
    await capture('missing-media')
    await page.goto(
      origin +
        seed.filter_examples['document-page-browser'] +
        '&selectedPerson=' +
        seed.entities.ada +
        '&gallery_person_only=on',
    )
    await gallery.getByRole('status').filter({ hasText: 'No matching pages.' }).waitFor()
    assert.equal(await gallery.locator('ol a').count(), 0)
    await capture('empty')
    await gallery.getByRole('button', { name: 'Collapse pages', exact: true }).click()
    await page.waitForURL((url) => !url.searchParams.has('pages_view'))
    assert.equal(await viewer.isVisible(), true)
    await page.goto(origin + seed.filter_examples['document-page-browser'])
    await settled()
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await capture('dark')
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      'no page horizontal overflow',
    )
    assert.deepEqual(errors, [])
    console.log(
      `${label}: expanded row order, bounded vertical scroll, all pages, highlights, person filter, page navigation, URL reload/history, source redirect, missing media, keyboard, dark and overflow passed`,
    )
    await context.close()
  }
} finally {
  await browser.close()
}
