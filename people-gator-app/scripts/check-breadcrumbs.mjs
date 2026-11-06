// Run against a migrated, twice-seeded disposable app. BREADCRUMB_SEED_LOG is
// the output of the second real seed CLI run, containing its scenario URLs.
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { readFile, mkdir } from 'node:fs/promises'

const origin = process.env.BREADCRUMB_ORIGIN || 'http://127.0.0.1:5115'
const log = await readFile(
  process.env.BREADCRUMB_SEED_LOG || '/tmp/issue114-seed-second.log',
  'utf8',
)
const routes = Object.fromEntries(
  [...log.matchAll(/^breadcrumb-([^:]+): https?:\/\/[^/]+(.+)$/gm)].map((m) => [m[1], m[2]]),
)
const output = process.env.BREADCRUMB_EVIDENCE || '../docs/evidence/issue114'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const crumbs = page.locator('[aria-label="Breadcrumb"] a')
    async function check(state) {
      assert.ok(routes[state], 'seed scenario exists: ' + state)
      await page.goto(origin + routes[state])
      const parts = routes[state].split('/')
      const [library, documentId, pageId] = [parts[2], parts[4], parts[6]]
      const documentLabel =
        state === 'unnamed' || state === 'unregistered'
          ? documentId
          : state === 'long-name'
            ? 'Z — A deliberately long synthetic catalogue title for document column width review with uninterrupted ArchiveReference0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            : 'Page gallery navigation'
      const pageLabel = 'Page ' + (state === 'missing-number' ? pageId : '1')
      await page.waitForFunction(
        ({ documentLabel, pageLabel }) => {
          const links = document.querySelectorAll('[aria-label="Breadcrumb"] a')
          return (
            links[2]?.textContent.trim() === documentLabel &&
            links[3]?.textContent.trim() === pageLabel
          )
        },
        { documentLabel, pageLabel },
      )
      assert.equal(await crumbs.nth(2).getAttribute('title'), documentLabel)
      assert.equal(await crumbs.nth(3).getAttribute('title'), pageLabel)
      assert.equal(
        await crumbs.nth(2).getAttribute('href'),
        '/scans?library=' + library + '&archive_document=' + documentId,
      )
      assert.equal(await crumbs.nth(3).getAttribute('href'), routes[state])
      await page.waitForFunction(() => document.fonts.status === 'loaded')
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        'no viewport overflow',
      )
      for (const name of ['PeopleGator', 'Scans', 'Documents', 'People']) {
        assert.ok(
          await page.getByRole('link', { name, exact: true }).first().isVisible(),
          name + ' navigation remains visible',
        )
      }
      // Full document labels stay accessible even where their visible text truncates.
      await crumbs.nth(2).focus()
      assert.equal(await crumbs.nth(2).evaluate((el) => el === document.activeElement), true)
      if (state !== 'missing-number') {
        assert.ok(
          await crumbs.nth(3).evaluate((el) => el.scrollWidth <= el.clientWidth),
          'numbered crumb fits',
        )
      }
      await page.waitForTimeout(400)
      await page.screenshot({ path: output + '/' + label + '-' + state + '.png' })
    }
    for (const state of ['named', 'missing-number', 'unnamed', 'unregistered', 'long-name'])
      await check(state)
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: output + '/' + label + '-long-name-dark.png' })
    await page.evaluate(() => document.documentElement.classList.remove('dark'))
    // Real browser history restores the matching record's labels.
    await page.goBack()
    await crumbs
      .nth(2)
      .filter({ hasText: routes.unregistered.split('/')[4] })
      .waitFor()
    await page.goForward()
    await crumbs.nth(2).filter({ hasText: 'Z — A deliberately long' }).waitFor()
    // Activate the document breadcrumb with the keyboard and verify its scope.
    await crumbs.nth(2).focus()
    await page.keyboard.press('Enter')
    await page.waitForURL(
      '**/scans?library=preview-table-widths-long-archive-label&archive_document=*',
    )

    // A real numbering edit updates the existing top bar without navigation.
    await page.goto(origin + routes.named + '?panel=statistics')
    const number = page.getByRole('textbox', { name: 'Page number', exact: true })
    await number.fill('42')
    await number.locator('..').getByRole('button', { name: 'Save', exact: true }).click()
    await crumbs.nth(3).filter({ hasText: 'Page 42' }).waitFor()
    await number.fill('1')
    await number.locator('..').getByRole('button', { name: 'Save', exact: true }).click()
    await crumbs.nth(3).filter({ hasText: 'Page 1' }).waitFor()
    const nextPage = page.locator('.document-page-gallery li a').nth(1)
    await nextPage.click()
    await crumbs.nth(3).filter({ hasText: 'Page 2' }).waitFor()
    assert.equal(
      await crumbs
        .nth(2)
        .textContent()
        .then((text) => text.trim()),
      'Page gallery navigation',
    )
    await page.goBack()
    await crumbs.nth(3).filter({ hasText: 'Page 1' }).waitFor()

    // A person profile names its last crumb, and a real rename updates it.
    assert.ok(routes.person, 'seed scenario exists: person')
    await page.goto(origin + routes.person)
    const personCrumb = crumbs.nth(2)
    await personCrumb.filter({ hasText: 'Ada Novak' }).waitFor()
    assert.equal(await personCrumb.getAttribute('title'), 'Ada Novak')
    assert.equal(await personCrumb.getAttribute('href'), routes.person)
    assert.equal(await crumbs.nth(1).getAttribute('href'), '/people')
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.waitForTimeout(400)
    await page.screenshot({ path: output + '/' + label + '-person.png' })
    async function rename(name) {
      await page.getByRole('button', { name: 'Edit name', exact: true }).click()
      const heading = page.locator('h1[contenteditable="plaintext-only"]')
      await heading.focus()
      await page.keyboard.press('ControlOrMeta+A')
      await page.keyboard.type(name)
      await page.getByRole('button', { name: 'Save name', exact: true }).click()
      await personCrumb.filter({ hasText: name }).waitFor()
    }
    await page.getByRole('tab', { name: 'Details' }).click()
    await rename('Ada Renamed')
    await rename('Ada Novak')
    assert.deepEqual(errors, [])
    await context.close()
    console.log(
      label +
        ': metadata, full titles, navigation, history, keyboard, number edits, person names and overflow passed',
    )
  }
} finally {
  await browser.close()
}
