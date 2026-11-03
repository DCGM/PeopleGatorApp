// Run against the migrated, twice-seeded local application from this revision.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.DOCUMENT_TABLE_ORIGIN || 'http://127.0.0.1:5211'
const output = process.env.DOCUMENT_TABLE_EVIDENCE || '../docs/evidence/issue111'
const scenario =
  '/documents?library=preview-table-navigation&library=preview-table&library=preview-table-widths&library=preview-table-widths-long-archive-label&library=preview-pagination'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  console.log(`Browser: ${browser.version()}`)
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height }, hasTouch: true })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    let requests = []
    page.on('request', (r) => {
      if (/\/api\/v1\/(documents|search-documents)\?/.test(r.url())) requests.push(new URL(r.url()))
    })
    const region = page.getByRole('region', {
      name: 'Documents table, scroll for more rows and columns',
      exact: true,
    })
    const rows = page.locator('tbody tr')
    const settled = async () => {
      await page.waitForFunction(() => !document.querySelector('main p[role="status"]'))
      await page.waitForTimeout(150)
    }
    const visit = async (query = scenario) => {
      await page.goto(origin + query)
      await rows.first().waitFor()
      await settled()
    }
    const capture = async (state) => page.screenshot({ path: `${output}/${label}-${state}.png` })
    const widths = () =>
      page
        .locator('col')
        .evaluateAll((cols) =>
          Object.fromEntries(cols.map((c) => [c.dataset.column, c.getBoundingClientRect().width])),
        )
    async function geometry() {
      const sizes = Object.values(await widths())
      const actual = await page.locator('table').evaluate((t) => ({
        total: t.getBoundingClientRect().width,
        header: [...t.querySelectorAll('th')].map((c) => c.getBoundingClientRect().width),
        rows: [...t.querySelectorAll('tbody tr')].map((r) =>
          [...r.children].map((c) => c.getBoundingClientRect().width),
        ),
        page: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
      }))
      assert.equal(
        actual.total,
        sizes.reduce((a, b) => a + b, 0),
      )
      assert.deepEqual(actual.header, sizes)
      for (const row of actual.rows) assert.deepEqual(row, sizes)
      assert.ok(actual.page <= actual.viewport, 'no page overflow')
      assert.equal(
        await page
          .locator('[data-slot="scroll-area-scrollbar"][data-orientation="vertical"]')
          .count(),
        1,
      )
      assert.equal(
        await page
          .locator('[data-slot="scroll-area-scrollbar"][data-orientation="horizontal"]')
          .count(),
        1,
      )
    }
    async function toggleColumn(name) {
      await page.getByRole('button', { name: 'Columns', exact: true }).click()
      await page.getByRole('checkbox', { name, exact: true }).click()
      await page.keyboard.press('Escape')
    }
    await visit()
    assert.equal(await rows.count(), 12)
    assert.deepEqual(await page.locator('th').allTextContents(), [
      'First page',
      'Document name',
      'Library',
      'Pages',
      'Linked entities',
      'Annotations',
      'Faces',
      'Mentions',
    ])
    assert.equal(
      await page.getByRole('button', { name: 'Restore column widths', exact: true }).count(),
      0,
    )
    await geometry()
    await region.evaluate((e) => e.scrollIntoView({ block: 'end' }))
    const bounds = await region.boundingBox()
    assert.ok(bounds.y + bounds.height <= height, 'scrollbar reachable after positioning the table')
    const layout = await region.evaluate((e) => ({
      sectionHeight: e.closest('[data-slot="scroll-area"]').parentElement.getBoundingClientRect()
        .height,
      footerBottom: document.querySelector('main footer').getBoundingClientRect().bottom,
      pageHeight: document.documentElement.scrollHeight,
      viewport: innerHeight,
    }))
    if (label === 'desktop') {
      assert.ok(Math.abs(layout.footerBottom - height) <= 1, 'footer reaches viewport bottom')
      assert.ok(layout.pageHeight <= height, 'desktop scroll belongs to the table')
      await page.setViewportSize({ width, height: 1200 })
      await page.waitForTimeout(150)
      const taller = await region.boundingBox()
      assert.ok(
        Math.abs(taller.height - bounds.height - 300) <= 1,
        'table grows with remaining desktop height',
      )
      await page.setViewportSize({ width, height })
      await page.waitForTimeout(150)
    } else {
      assert.ok(
        Math.abs(layout.sectionHeight - height) <= 1,
        'mobile table section fills viewport height',
      )
    }
    await capture('defaults')
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await capture('columns')
    await page.keyboard.press('Escape')
    for (const name of ['NDK', 'Document ID', 'Last modified']) await toggleColumn(name)
    const expanded = await widths()
    await page.reload()
    await rows.first().waitFor()
    await settled()
    assert.deepEqual(await widths(), expanded)
    for (const fraction of [0, 0.5, 1]) {
      await visit()
      requests = []
      await region.evaluate((e, f) => {
        e.scrollLeft = (e.scrollWidth - e.clientWidth) * f
      }, fraction)
      const left = await region.evaluate((e) => e.scrollLeft)
      let release
      if (fraction === 0) {
        const held = new Promise((resolve) => {
          release = resolve
        })
        await page.route('**/api/v1/documents?**', async (route) => {
          if (new URL(route.request().url()).searchParams.has('cursor')) await held
          await route.continue()
        })
      }
      await region.hover()
      await page.mouse.wheel(0, 10000)
      if (fraction === 0) {
        await page.locator('[data-slot="document-loading-row"]').waitFor()
        assert.equal(await rows.count(), 13, 'existing twelve rows plus one loading row')
        await region.evaluate((e) => {
          e.scrollTop = e.scrollHeight
        })
        await capture('loading-more')
        release()
      }
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 19)
      await settled()
      if (fraction === 0) await page.unroute('**/api/v1/documents?**')
      assert.equal(await page.locator('[data-slot="document-loading-row"]').count(), 0)
      assert.equal(requests.filter((u) => u.searchParams.has('cursor')).length, 1)
      assert.equal(await region.evaluate((e) => e.scrollLeft), left)
      const sticky = await region.evaluate((e) => ({
        top: e.getBoundingClientRect().top,
        header: e.querySelector('thead').getBoundingClientRect().top,
        scroll: e.scrollTop,
      }))
      assert.ok(sticky.scroll > 0)
      assert.ok(Math.abs(sticky.top - sticky.header) <= 2)
      await geometry()
      if (fraction === 1) await capture('scrolled')
    }
    await region.evaluate((e) => {
      e.scrollLeft = 0
      e.scrollTop = 0
    })
    if (label === 'mobile') {
      await region.evaluate((e) => e.scrollIntoView({ block: 'end' }))
      const bounds = await region.boundingBox()
      const cdp = await context.newCDPSession(page)
      async function swipe(dx, dy) {
        const x = Math.round(bounds.x + bounds.width - 30)
        const y = Math.round(bounds.y + bounds.height - 30)
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
        for (let step = 1; step <= 10; step++) {
          await cdp.send('Input.dispatchTouchEvent', {
            type: 'touchMove',
            touchPoints: [{ x: x + (dx * step) / 10, y: y + (dy * step) / 10 }],
          })
          await page.waitForTimeout(25)
        }
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
        await page.waitForTimeout(200)
      }
      await swipe(-180, 0)
      assert.ok(await region.evaluate((e) => e.scrollLeft > 0), 'touch horizontal scrolling')
      await swipe(0, -180)
      assert.ok(await region.evaluate((e) => e.scrollTop > 0), 'touch vertical scrolling')
      await region.evaluate((e) => {
        e.scrollLeft = 0
        e.scrollTop = 0
      })
      await cdp.detach()
    }
    await region.focus()
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(300)
    assert.ok(await region.evaluate((e) => e.scrollLeft > 0))
    const handle = page.getByRole('separator', { name: 'Resize Document name column', exact: true })
    await handle.focus()
    await page.keyboard.press('ArrowRight')
    assert.equal((await widths()).name, 330)
    await page.keyboard.press('Enter')
    assert.equal((await widths()).name, 320)
    const sort = page.getByRole('button', { name: /^Sort by Pages:/ })
    for (const [action, direction] of [
      ['sort ascending', 'asc'],
      ['sort descending', 'desc'],
      ['clear sorting', null],
    ]) {
      assert.ok((await sort.getAttribute('aria-label')).endsWith(action))
      await sort.focus()
      await page.keyboard.press('Enter')
      await settled()
      assert.equal(new URL(page.url()).searchParams.get('sort'), direction ? 'page_count' : null)
      assert.equal(requests.at(-1).searchParams.get('sort'), direction ? 'page_count' : 'name')
      assert.equal(requests.at(-1).searchParams.get('sort_direction'), direction || 'asc')
      assert.equal(await page.locator('th[aria-sort]').count(), direction ? 1 : 0)
      assert.deepEqual(await widths(), expanded)
      if (direction) await capture(`sort-${direction}`)
    }
    await page.goBack()
    await settled()
    assert.equal(await page.locator('th[aria-sort="descending"]').innerText(), 'Pages')
    await page.goForward()
    await settled()
    assert.equal(await page.locator('th[aria-sort]').count(), 0)
    if (label === 'mobile')
      await page.getByRole('button', { name: 'Show filters', exact: true }).click()
    await page.getByRole('combobox', { name: 'Sort by', exact: true }).click()
    await page.getByRole('option', { name: 'Pages · Highest first', exact: true }).click()
    await settled()
    assert.equal(await page.locator('th[aria-sort="descending"]').innerText(), 'Pages')
    if (label === 'mobile')
      await page.getByRole('button', { name: 'Hide filters', exact: true }).click()
    await visit(scenario + '&q=Pagination')
    assert.equal(await page.locator('th[aria-sort]').count(), 0)
    for (let i = 0; i < 3; i++) {
      await sort.click()
      await settled()
    }
    assert.equal(new URL(page.url()).searchParams.get('sort'), null)
    assert.equal(requests.at(-1).searchParams.get('sort'), 'relevance')
    await visit()
    await page.locator('td[data-column="name"] a').first().click()
    await page.waitForURL('**/scans?document=*')
    await page.goBack()
    await rows.first().waitFor()
    await settled()
    assert.deepEqual(await widths(), expanded)
    const library = page.locator('td[data-column="library"] a').first()
    const libraryName = await library.textContent()
    await library.click()
    await settled()
    assert.deepEqual(new URL(page.url()).searchParams.getAll('library'), [libraryName])
    await visit()
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await page.getByRole('button', { name: 'Restore defaults', exact: true }).click()
    await page.keyboard.press('Escape')
    const ledger = rows.filter({ hasText: 'Document table ledger' })
    assert.deepEqual(
      await ledger
        .locator('td')
        .allTextContents()
        .then((a) => a.slice(3)),
      ['2', '2', '9', '4', '5'],
    )
    const missing = rows.filter({ hasText: 'Navigation: missing preview' })
    await missing.getByText('No preview', { exact: true }).waitFor()
    assert.ok(await missing.getByRole('link', { name: /Open first page/ }).getAttribute('href'))
    assert.equal(
      await rows
        .filter({ hasText: 'Navigation: no pages' })
        .getByText('No pages', { exact: true })
        .count(),
      1,
    )
    await ledger.getByRole('link', { name: /Open first page/ }).click()
    await page.waitForURL('**/libraries/*/documents/*/pages/*')
    const firstPageEditor = page.url()
    await page.goBack()
    await rows.first().waitFor()
    await settled()
    await ledger.locator('td[data-column="name"] a').click()
    await page.waitForURL('**/libraries/*/documents/*/pages/*')
    assert.equal(
      page.url(),
      firstPageEditor,
      'document name and preview open the same first-page editor',
    )
    await page.waitForFunction(() => !document.querySelector('main p[role="status"]'))
    await page.getByRole('img', { name: /^Scan / }).waitFor()
    await page.waitForFunction(() => {
      const image = document.querySelector('img[alt^="Scan "]')
      return (
        image?.complete &&
        image.naturalWidth > 0 &&
        !document.querySelector('[data-slot="skeleton"]')
      )
    })
    await capture('first-page-editor')
    await page.goBack()
    await rows.first().waitFor()
    await settled()
    await region.evaluate((e) => {
      e.scrollTop = 0
      e.scrollLeft = 0
    })
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await page.waitForTimeout(400)
    await capture('dark')
    await geometry()
    assert.deepEqual(errors, [])
    console.log(
      `${label} ${width}x${height}: geometry, bounded wheel/keyboard scrolling, sticky header, cursor at left/middle/right, sizing, tri-state keyboard sorting, shared sort/history/search default, session reload/navigation, links, counts, missing media and dark theme passed`,
    )
    await context.close()
  }
} finally {
  await browser.close()
}
