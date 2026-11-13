import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.CREATION_FILTER_ORIGIN || 'http://127.0.0.1:5128'
const output = process.env.CREATION_FILTER_EVIDENCE || '../docs/evidence/issue128/creation-filters'
const seed = await readFile(
  process.env.CREATION_FILTER_SEED_LOG || '/tmp/issue128-creation-filter-seed2.log',
  'utf8',
)
const links = Object.fromEntries(
  seed.split('\n').flatMap((line) => {
    const match = line.match(/^([^:]+): (https?:\/\/\S+)$/)
    if (!match) return []
    const url = new URL(match[2])
    return [[match[1], url.pathname + url.search]]
  }),
)
const append = (url, params) => url + (url.includes('?') ? '&' : '?') + new URLSearchParams(params)
const scenarios = [
  ['documents', links['documents-created-by'], 'documents', '/api/v1/documents'],
  ['people', links['people-created-by'], 'Search people panel', '/api/v1/search-entities'],
  ['person-faces', links['faces-created-by'], 'Person evidence panel', '/api/v1/faces'],
  [
    'person-mentions',
    links['mentions-created-by'],
    'Person evidence panel',
    '/api/v1/text-mentions',
  ],
]
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
let activePage
try {
  for (const [viewport, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    activePage = page
    page.setDefaultTimeout(15000)
    const errors = [],
      requests = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) requests.push(new URL(request.url()))
    })
    for (const [name, url, label, endpoint] of scenarios) {
      assert.ok(url, `Missing seed scenario ${name}`)
      requests.length = 0
      await page.goto(origin + url)
      let panel
      if (label === 'documents') {
        if (viewport === 'mobile') {
          assert.equal(
            await page.getByRole('button', { name: 'Created by', exact: true }).count(),
            0,
          )
          await page.getByRole('button', { name: 'Show filters', exact: true }).click()
          panel = page.getByRole('dialog', { name: 'Filters', exact: true })
        } else panel = page.getByRole('complementary', { name: 'Document filters' })
      } else panel = page.locator(`[aria-label="${label}"]`).first()
      await panel.waitFor()
      if (viewport === 'mobile' && label !== 'documents') {
        await panel.scrollIntoViewIfNeeded()
        assert.equal(
          await panel.getByRole('button', { name: 'Created by', exact: true }).count(),
          0,
        )
        const toggle = panel.getByRole('button', { name: 'Show filters', exact: true })
        await toggle.click()
        await page.waitForTimeout(100)
      }
      for (const field of ['Created by', 'Created via key', 'Created from', 'Created to'])
        await panel.getByRole('button', { name: field, exact: true }).waitFor({ state: 'visible' })
      await page.waitForTimeout(500)
      assert.ok(
        requests.some(
          (request) =>
            request.pathname === endpoint &&
            [...request.searchParams.keys()].some((key) => key.startsWith('filter.created')),
        ),
        `${name}: creation criteria reached ${endpoint}`,
      )
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
        true,
        `${name}: no page overflow`,
      )
      await page.screenshot({ path: `${output}/${viewport}-${name}.png`, fullPage: false })
      if (name === 'people') {
        await panel.getByRole('button', { name: 'Created from', exact: true }).click()
        const time = page.getByLabel('Created from time', { exact: true })
        await time.waitFor({ state: 'visible' })
        await page.screenshot({ path: `${output}/${viewport}-date-picker.png` })
        const previous = new URL(page.url()).searchParams.get('created_from')
        await time.fill('12:00:00.000')
        await page.waitForFunction(
          (value) => new URL(location.href).searchParams.get('created_from') !== value,
          previous,
        )
        await page.keyboard.press('Escape')
      }
      // Exercise actual creator selection, rather than URL restoration alone.
      if (name === 'documents') {
        await panel.getByRole('button', { name: 'Created by', exact: true }).click()
        await page.getByRole('option').filter({ hasText: 'Preview reviewer' }).waitFor()
        await page.screenshot({ path: `${output}/${viewport}-creator-picker.png` })
        await page.getByRole('option').filter({ hasText: 'Preview reviewer' }).click()
        await page.keyboard.press('Escape')
        await page.waitForFunction(() => !new URL(location.href).searchParams.has('created_by'))
        await panel.getByRole('button', { name: 'Created via key', exact: true }).click()
        await page.getByRole('option').filter({ hasText: 'preview-seed-importer' }).click()
        await page.keyboard.press('Escape')
        await page.waitForFunction(() => new URL(location.href).searchParams.has('created_key'))
        await page.waitForFunction(() =>
          [...document.querySelectorAll('tbody td[data-column="name"]')].some((cell) =>
            cell.textContent.includes('Creation: API key registration'),
          ),
        )
        if (viewport === 'mobile') {
          await page.getByRole('listbox').waitFor({ state: 'detached' })
          await page.keyboard.press('Escape')
          await panel.waitFor({ state: 'detached' })
        }
        await page.getByRole('button', { name: /^Remove Created via key:/ }).click()
        await page.waitForFunction(() => !new URL(location.href).searchParams.has('created_key'))
      }
      console.log(
        `${viewport} ${name}: controls, URL restoration, backend parameters and no horizontal overflow passed`,
      )
    }
    assert.deepEqual(errors, [], 'No browser errors')
    await context.close()
  }
} catch (error) {
  if (activePage && !activePage.isClosed())
    await activePage.screenshot({ path: output + '/failure.png' })
  throw error
} finally {
  await browser.close()
}
