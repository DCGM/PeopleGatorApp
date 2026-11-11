// Run against this revision's migrated, twice-seeded synthetic application.
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { chromium } from 'playwright'

const origin = process.env.DOCUMENT_TABLE_ORIGIN || 'http://127.0.0.1:5142'
const output = process.env.DOCUMENT_TABLE_EVIDENCE || '../docs/evidence/issue142'
const scenario =
  '/documents?library=preview-table-widths&library=preview-table-widths-long-archive-label&library=preview-pagination&library=preview-table&sort=name'
await mkdir(output, { recursive: true })
const results = []
for (const [label, width, height] of [
  ['desktop', 1440, 900],
  ['mobile', 390, 844],
]) {
  const profile = await mkdtemp(join(tmpdir(), 'issue142-browser-'))
  let context
  try {
    const launch = () =>
      chromium.launchPersistentContext(profile, {
        headless: true,
        viewport: { width, height },
        hasTouch: label === 'mobile',
      })
    context = await launch()
    let page = await context.newPage()
    const visit = async (target) => {
      await target.goto(origin + scenario)
      await target.locator('tbody tr').first().waitFor()
      await target
        .getByRole('separator', { name: 'Resize Document name column', exact: true })
        .waitFor()
    }
    const layout = (target) =>
      target.locator('table').evaluate((table) => ({
        ids: [...table.querySelectorAll('thead th[data-column]')].map(
          (cell) => cell.dataset.column,
        ),
        widths: Object.fromEntries(
          [...table.querySelectorAll('col[data-column]')].map((col) => [
            col.dataset.column,
            col.style.width,
          ]),
        ),
      }))
    const capture = async (state) => {
      await page.locator('thead th[data-column]').first().scrollIntoViewIfNeeded()
      await page.screenshot({ path: `${output}/${label}-${state}.png` })
    }
    await visit(page)
    await capture('defaults')
    const original = await layout(page)
    await page.locator('[data-move-column="name"]').press('ArrowLeft')
    const resize = page.getByRole('separator', { name: 'Resize Document name column', exact: true })
    await resize.press('Shift+ArrowRight')
    await resize.press('Shift+ArrowRight')
    await resize.press('Shift+ArrowRight')
    await page.locator('[data-column-menu="ndk"]').click()
    await page.getByRole('menuitem', { name: 'Remove column', exact: true }).click()
    await page.getByRole('button', { name: 'Add column', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Document ID', exact: true }).click()
    const saved = await layout(page)
    assert.equal(saved.ids[0], 'name')
    assert.ok(!saved.ids.includes('ndk'))
    assert.ok(saved.ids.includes('document_id'))
    assert.equal(saved.widths.name, '440px')
    await capture('customized')
    await page.reload()
    await page.locator('tbody tr').first().waitFor()
    assert.deepEqual(await layout(page), saved, 'same-tab reload restores full layout')
    const tab = await context.newPage()
    await visit(tab)
    assert.deepEqual(
      await layout(tab),
      saved,
      'new tab restores layout without session preferences',
    )
    await tab.close()
    await context.close()
    context = await launch()
    page = await context.newPage()
    await visit(page)
    assert.deepEqual(await layout(page), saved, 'browser restart restores full layout')
    await capture('restored')
    await page.getByRole('button', { name: 'Add column', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Restore default columns', exact: true }).click()
    assert.deepEqual(await layout(page), original, 'default reset includes widths')
    await page.reload()
    await page.locator('tbody tr').first().waitFor()
    assert.deepEqual(await layout(page), original, 'default reset remains after reload')
    await capture('reset')
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
      'no page overflow',
    )
    results.push({
      viewport: label,
      width,
      height,
      restoredWidth: saved.widths.name,
      checks: [
        'keyboard reorder/resize',
        'add/remove',
        'reload',
        'new tab',
        'browser restart',
        'full reset',
        'no page overflow',
      ],
    })
  } finally {
    await context?.close()
    await rm(profile, { recursive: true, force: true })
  }
}
await writeFile(`${output}/results.json`, JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
