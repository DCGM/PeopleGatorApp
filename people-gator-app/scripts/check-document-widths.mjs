// Run against the migrated, twice-seeded local application; see docs/TEST.md.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.DOCUMENT_WIDTHS_ORIGIN || 'http://127.0.0.1:5193'
const output = process.env.DOCUMENT_WIDTHS_EVIDENCE || '/tmp/issue93-evidence'
const scenario =
  '/documents?library=preview-table-widths&library=preview-table-widths-long-archive-label&library=preview-pagination&library=preview-table&sort=name'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height }, hasTouch: true })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    let requests = []
    page.on('request', (request) => {
      if (/\/api\/v1\/(documents|search-documents)(\?|$)/.test(request.url()))
        requests.push(request.url())
    })
    const table = page.locator('table')
    const region = page.getByRole('region', { name: 'Table, scroll for more columns' })
    const rows = page.locator('tbody tr')
    async function settled() {
      await page.waitForFunction(() => !document.querySelector('main p[role="status"]'))
      await page.waitForTimeout(150)
    }
    async function widths() {
      return table
        .locator('col')
        .evaluateAll((cols) =>
          Object.fromEntries(
            cols.map((col) => [col.dataset.column, col.getBoundingClientRect().width]),
          ),
        )
    }
    async function check(expected) {
      assert.deepEqual(await widths(), expected)
      const geometry = await table.evaluate((element) => {
        const columns = Array.from(element.querySelectorAll('col')).map(
          (col) => col.getBoundingClientRect().width,
        )
        return {
          total: element.getBoundingClientRect().width,
          sum: columns.reduce((a, b) => a + b, 0),
          headers: Array.from(element.querySelectorAll('th')).map((cell) => [
            cell.getBoundingClientRect().width,
            parseFloat(cell.style.width),
          ]),
          cells: Array.from(element.querySelectorAll('tbody tr')).map((row) =>
            Array.from(row.children).map((cell) => cell.getBoundingClientRect().width),
          ),
          page: document.documentElement.scrollWidth,
          viewport: document.documentElement.clientWidth,
        }
      })
      assert.equal(geometry.total, geometry.sum)
      assert.ok(geometry.page <= geometry.viewport, 'overflow must stay inside the table region')
      for (const [actual, model] of geometry.headers)
        assert.equal(actual, model, 'group/leaf header sizing')
      for (const cells of geometry.cells) assert.deepEqual(cells, Object.values(expected))
    }
    async function capture(state) {
      await page.screenshot({ path: `${output}/after-${label}-${state}.png` })
    }
    async function sortByName() {
      const response = page.waitForResponse(
        (r) => /\/api\/v1\/documents\?/.test(r.url()) && r.status() === 200,
      )
      await page.getByRole('button', { name: 'Sort by Document name', exact: true }).click()
      await response
      await settled()
    }
    async function toggleColumn(name) {
      await page.getByRole('button', { name: 'Columns', exact: true }).click()
      await page.getByRole('checkbox', { name, exact: true }).click()
      await page.keyboard.press('Escape')
    }
    await page.goto(origin + scenario)
    await rows.first().waitFor()
    await settled()
    const defaults = await widths()
    await check(defaults)
    await capture('ascending')
    await sortByName()
    await check(defaults)
    const longCell = rows.first().locator('[data-column="name"]')
    const wrapping = await longCell.evaluate((cell) => ({
      height: cell.getBoundingClientRect().height,
      width: cell.clientWidth,
      scroll: cell.scrollWidth,
      text: cell.textContent,
    }))
    assert.ok(
      wrapping.height > 80 && wrapping.text.length > 150,
      'full long title wraps to multiple lines',
    )
    assert.ok(wrapping.scroll <= wrapping.width, 'unbroken title must wrap inside the column')
    await capture('descending')

    // Pointer sizing belongs only to the header, with no sort/filter requests.
    const handle = page.getByRole('separator', { name: 'Resize Document name column', exact: true })
    const beforeResize = requests.length
    const sortUrl = page.url()
    const box = await handle.boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2, { steps: 8 })
    await page.mouse.up()
    assert.equal((await widths()).name, 400)
    assert.equal(page.url(), sortUrl)
    assert.equal(requests.length, beforeResize)
    await handle.focus()
    await page.keyboard.press('ArrowRight')
    assert.equal((await widths()).name, 410)
    await page.keyboard.press('Home')
    await page.keyboard.press('ArrowLeft')
    assert.equal((await widths()).name, 200)
    await page.keyboard.press('End')
    await page.keyboard.press('ArrowRight')
    assert.equal((await widths()).name, 720)
    await page.keyboard.press('Enter')
    assert.equal((await widths()).name, 320)
    // Dispatch actual TouchEvents into TanStack's touch start/move/end path.
    await handle.evaluate((element) => {
      const box = element.getBoundingClientRect()
      const dispatch = (target, type, x) => {
        const touch = new Touch({
          identifier: 1,
          target: element,
          clientX: x,
          clientY: box.y + box.height / 2,
        })
        target.dispatchEvent(
          new TouchEvent(type, {
            bubbles: true,
            cancelable: true,
            touches: type === 'touchend' ? [] : [touch],
            changedTouches: [touch],
          }),
        )
      }
      const start = Math.round(box.x)
      dispatch(element, 'touchstart', start)
      dispatch(document, 'touchmove', start + 50)
      dispatch(document, 'touchend', start + 50)
    })
    assert.equal((await widths()).name, 370)
    const resized = await widths()
    await check(resized)
    await sortByName()
    await check(resized)
    await toggleColumn('Document name')
    assert.equal((await widths()).name, undefined)
    await toggleColumn('Document name')
    await check(resized)
    await page.getByRole('button', { name: 'Restore column widths', exact: true }).click()
    await check(defaults)

    for (const field of [
      'First page',
      'Modified by',
      'API key',
      'Faces: Total',
      'Faces: Manual',
      'Text mentions: Total',
    ])
      await toggleColumn(field)
    const expanded = await widths()
    // Let local thumbnail media finish; neither success nor no-preview changes geometry.
    await settled()
    await check(expanded)
    await sortByName()
    await handle.focus()
    await page.keyboard.press('ArrowRight')
    await capture('resized-media')
    await page.getByRole('button', { name: 'Restore column widths', exact: true }).click()
    await check(expanded)

    // Sentinel is outside horizontal overflow; test real opaque cursor loading at
    // both middle and far-right positions, with one cursor request per batch.
    for (const fraction of [0.5, 1]) {
      await page.goto(origin + scenario)
      await rows.first().waitFor()
      await settled()
      const original = await widths()
      await region.evaluate((element, fraction) => {
        element.scrollLeft = (element.scrollWidth - element.clientWidth) * fraction
      }, fraction)
      const left = await region.evaluate((element) => element.scrollLeft)
      requests = []
      await page.locator('footer').scrollIntoViewIfNeeded()
      await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 17)
      await settled()
      await check(original)
      assert.equal(await region.evaluate((element) => element.scrollLeft), left)
      const cursors = requests.filter((url) => new URL(url).searchParams.has('cursor'))
      assert.equal(cursors.length, 1, 'one automatic cursor request')
      // Shared sort keeps horizontal position; cache may satisfy the return order.
      await page
        .getByRole('button', { name: 'Sort by Document name', exact: true })
        .evaluate((element) => element.click())
      await settled()
      await check(original)
      assert.equal(await region.evaluate((element) => element.scrollLeft), left)
    }
    await page.goto(origin + scenario)
    await rows.first().waitFor()
    await settled()
    // Hold a real request to observe the empty loading table, then release it.
    let release
    const held = new Promise((resolve) => {
      release = resolve
    })
    await page.route('**/api/v1/documents?**', async (route) => {
      await held
      await route.continue()
    })
    await page.getByRole('button', { name: 'Sort by Document name', exact: true }).click()
    await page.locator('main p[role="status"]').waitFor()
    await check(defaults)
    release()
    await settled()
    await page.unroute('**/api/v1/documents?**')
    await check(defaults)
    // Search empty results and restore via the actual search input/URL state.
    const search = page.getByRole('textbox', { name: 'Search documents', exact: true })
    await search.fill('zzzzNoSyntheticDocumentMatches')
    await page.getByText('No documents match your search and filters.', { exact: true }).waitFor()
    await check(defaults)
    await search.fill('')
    await rows.first().waitFor()
    await settled()
    await check(defaults)
    // The shared server sort control and URL/history use the same geometry.
    if (label === 'mobile')
      await page.getByRole('button', { name: 'Show filters', exact: true }).click()
    await page.getByRole('combobox', { name: 'Sort by', exact: true }).click()
    await page.getByRole('option', { name: 'Pages · Highest first', exact: true }).click()
    await settled()
    assert.equal(new URL(page.url()).searchParams.get('sort'), 'page_count')
    await check(defaults)
    await page.getByRole('combobox', { name: 'Sort by', exact: true }).click()
    await page.getByRole('option', { name: 'Pages · Lowest first', exact: true }).click()
    await settled()
    await check(defaults)
    if (label === 'mobile')
      await page.getByRole('button', { name: 'Hide filters', exact: true }).click()
    // A failed replacement query keeps the same column model, then recovers.
    await page.route('**/api/v1/documents?**', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: '{"detail":"Synthetic browser failure"}',
      }),
    )
    await page
      .getByRole('button', { name: 'Sort by Last modified', exact: true })
      .evaluate((element) => element.click())
    await page.getByText('Could not load documents.', { exact: true }).waitFor()
    await check(defaults)
    await page.unroute('**/api/v1/documents?**')
    await page.getByRole('button', { name: 'Retry documents', exact: true }).click()
    await rows.first().waitFor()
    await settled()
    await check(defaults)
    await page.goBack()
    await settled()
    await check(defaults)
    await region.focus()
    const beforeKeyboardScroll = await region.evaluate((element) => element.scrollLeft)
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(300)
    assert.ok(
      (await region.evaluate((element) => element.scrollLeft)) > beforeKeyboardScroll,
      'keyboard scroll access',
    )
    await region.evaluate((element) => {
      element.scrollLeft = element.scrollWidth - element.clientWidth
    })
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    // Wait for standard color transitions before measuring/capturing the theme.
    await page.waitForTimeout(500)
    const contrast = await table.evaluate((element) => {
      const luminance = (color) => {
        const channels = color
          .match(/[\d.]+/g)
          .slice(0, 3)
          .map(Number)
          .map((v) => {
            const s = v / 255
            return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
          })
        return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
      }
      const background = luminance(getComputedStyle(document.body).backgroundColor)
      return Array.from(element.querySelectorAll('td, th, th button')).map((cell) => {
        const foreground = luminance(getComputedStyle(cell).color)
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
      })
    })
    assert.ok(
      contrast.every((ratio) => ratio >= 4.5),
      'dark table text and header controls must remain legible',
    )
    await capture('dark')
    await region.evaluate((element) => {
      element.scrollLeft = 0
    })
    await capture('dark-titles')
    assert.deepEqual(errors, [])
    console.log(
      `${label} ${width}x${height}: stable geometry, wrapping, pointer/touch/keyboard resizing, bounds/reset, grouped headers, media, visibility, shared sorting/history, loading/empty/error recovery, keyboard scrolling and cursor loading passed`,
    )
    await context.close()
  }
} finally {
  await browser.close()
}
