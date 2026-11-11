// Run against the actual migrated/twice-seeded local application.
import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.DOCUMENT_NAV_ORIGIN || 'http://127.0.0.1:5141'
const output = process.env.DOCUMENT_NAV_EVIDENCE || '../docs/evidence/issue141'
const seed = await readFile(process.env.DOCUMENT_NAV_SEED_LOG || '/tmp/issue141-seed-1.log', 'utf8')
const entry = (key) => {
  const line = seed.split('\n').find((line) => line.startsWith(key + ': '))
  assert.ok(line, `seed entry ${key}`)
  const url = new URL(line.slice(key.length + 2))
  return url.pathname + url.search
}
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const capture = async (name) => {
      // Grid presence precedes the local media queries; capture settled thumbnails.
      await page.waitForFunction(() => !document.querySelector(
        '.document-page-gallery [data-slot="loadable-image"][data-state="loading"], tbody [data-slot="loadable-image"][data-state="loading"]',
      ))
      await page.screenshot({ path: `${output}/${label}-${name}.png`, animations: 'disabled' })
    }
    await page.goto(origin + entry('document-browse'))
    const grid = page.locator('[aria-label="Document pages grid"]')
    await grid.waitFor()
    assert.equal(await page.getByRole('link', { name: 'Scans', exact: true }).count(), 0)
    await page.getByRole('button', { name: 'Collapse pages', exact: true }).scrollIntoViewIfNeeded()
    await capture('document-browser')
    const expanded = page.url()
    await grid.getByRole('link').first().click()
    await page.waitForURL((url) => !url.searchParams.has('pages_view'))
    await page.getByRole('region', { name: 'Pan and zoom document page', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Expand pages', exact: true }).scrollIntoViewIfNeeded()
    await capture('page-viewer')
    await page.goBack()
    await grid.waitFor()
    assert.equal(page.url(), expanded)
    await page.reload()
    await grid.waitFor()
    const source = new URL(origin + entry('document-browse')).pathname.split('/').at(-1)
    await page.goto(`${origin}/scans?document=${source}&q=discard&link_state=manual`)
    await grid.waitFor()
    assert.ok(!new URL(page.url()).searchParams.has('q'))
    assert.ok(!new URL(page.url()).searchParams.has('link_state'))
    const canonical = new URL(page.url())
    const [, , library, , document] = canonical.pathname.split('/')
    await page.goto(`${origin}/scans?library=${library}&archive_document=${document}`)
    await grid.waitFor()
    await page.goto(origin + entry('document-browse-unregistered'))
    await grid.waitFor()
    await page.goto(origin + entry('document-browse-empty'))
    await page.getByText('No pages in this document.', { exact: true }).waitFor()
    assert.ok(
      (await page.getByRole('heading', { level: 1 }).textContent()).includes(
        'Navigation: no pages',
      ),
    )
    await capture('empty-document')
    await page.goto(origin + '/documents/00000000-0000-4000-8000-000000000000')
    await page.getByText('Document not found.', { exact: true }).waitFor()
    await capture('missing-document')
    for (const legacy of [
      '/scans',
      '/scans?q=Ada&library=preview-mzk',
      '/scans?document=a&document=b',
    ]) {
      await page.goto(origin + legacy)
      await page.waitForURL(origin + '/documents')
      await page.locator('tbody tr').first().waitFor()
    }
    await capture('documents-navigation')
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    assert.deepEqual(errors, [])
    results.push({
      viewport: label,
      width,
      height,
      checks: [
        'document browser entry',
        'page open/back/reload',
        'source UUID legacy link',
        'archive/library legacy link',
        'orphan pages',
        'empty document',
        'missing document',
        'global/multidocument redirect',
        'no Scans tab or page overflow',
      ],
    })
    await context.close()
  }
} finally {
  await browser.close()
}
await writeFile(`${output}/results.json`, JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
