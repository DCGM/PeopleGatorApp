// Run against an isolated migrated and twice-seeded synthetic instance.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.DOCUMENT_CREATION_ORIGIN || 'http://127.0.0.1:5128'
const output = process.env.DOCUMENT_CREATION_EVIDENCE || '../docs/evidence/issue128'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  for (const [label, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const headers = () => page.locator('th[data-column]').evaluateAll(elements => elements.map(element => element.dataset.column))
    const region = page.getByRole('region', { name: 'Documents table, scroll for more rows and columns', exact: true })
    const capture = async state => page.screenshot({ path: `${output}/${label}-${state}.png` })
    const add = async name => {
      await page.getByRole('button', { name: 'Add column', exact: true }).click()
      await page.getByRole('menuitem', { name, exact: true }).click()
      await page.getByRole('menu').waitFor({ state: 'detached' })
    }
    const remove = async id => {
      await page.locator(`[data-column-menu="${id}"]`).click()
      await page.getByRole('menuitem', { name: 'Remove column', exact: true }).click()
      await page.getByRole('menu').waitFor({ state: 'detached' })
    }
    await page.goto(origin + '/documents?library=preview-creation&sort=name')
    await page.locator('tbody tr').first().waitFor()
    assert.equal(await page.locator('tbody tr').count(), 3)
    assert.ok(!(await headers()).includes('created'))
    assert.ok(!(await headers()).includes('created_by'))
    // Use real controls, retaining the name so each row can be identified.
    for (const id of await headers()) if (id !== 'name') await remove(id)
    await page.getByRole('button', { name: 'Add column', exact: true }).click()
    assert.equal(await page.getByRole('menuitem', { name: 'Created', exact: true }).count(), 1)
    assert.equal(await page.getByRole('menuitem', { name: 'Created by', exact: true }).count(), 1)
    await page.waitForTimeout(300)
    await capture('add-columns')
    await page.keyboard.press('Escape')
    await add('Created')
    await add('Created by')
    assert.deepEqual(await headers(), ['name', 'created', 'created_by'])
    assert.deepEqual(await page.locator('td[data-column="created_by"]').allTextContents(), [
      'Preview face importer (Preview face importer)', 'Unknown', 'Preview reviewer',
    ])
    const dates = await page.locator('td[data-column="created"]').allTextContents()
    assert.ok(dates[0] !== 'Unknown' && dates[2] !== 'Unknown')
    assert.equal(dates[1], 'Unknown')
    assert.equal(await page.locator('[aria-label^="Sort by Created"]').count(), 0)
    // Keyboard reordering and restored order/visibility across reload.
    await page.locator('[data-move-column="created_by"]').focus()
    await page.keyboard.press('ArrowLeft')
    assert.deepEqual(await headers(), ['name', 'created_by', 'created'])
    await page.reload()
    await page.locator('tbody tr').first().waitFor()
    assert.deepEqual(await headers(), ['name', 'created_by', 'created'])
    await page.locator('[data-move-column="created_by"]').focus()
    await page.keyboard.press('ArrowRight')
    await remove('created_by')
    assert.ok(!(await headers()).includes('created_by'))
    await add('Created by')
    assert.deepEqual(await headers(), ['name', 'created', 'created_by'])
    // Keep the focus indicator and popup transitions out of the data captures.
    await page.locator('input').first().focus()
    if (label === 'desktop') {
      await region.evaluate(element => { element.scrollLeft = 0 })
      await capture('creation')
    } else {
      await page.locator('th[data-column="created"]').evaluate(element => element.scrollIntoView({ inline: 'start', block: 'nearest' }))
      await capture('creation')
      await page.locator('th[data-column="created_by"]').evaluate(element => element.scrollIntoView({ inline: 'start', block: 'nearest' }))
      await capture('creator')
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width)
    assert.deepEqual(errors, [])
    console.log(`${label} ${width}x${height}: default visibility, Add column, labels/dates/Unknown, keyboard move, remove/re-add, reload persistence and no page overflow passed`)
    await context.close()
  }
} finally {
  await browser.close()
}
