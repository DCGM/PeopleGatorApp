// Run against this revision's migrated, twice-seeded synthetic instance.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const origin = process.env.PAGE_STRIP_ORIGIN || 'http://127.0.0.1:5132'
const api = process.env.PAGE_STRIP_API || 'http://127.0.0.1:8131'
const output = process.env.PAGE_STRIP_EVIDENCE || '../docs/evidence/issue131'
const root = '/libraries/preview-page-strip/documents/ac6cd0ec-bfc4-50ad-9a0c-f0059f2d6fe3/pages/'
const first = 'f5e304eb-38a6-5465-8dc0-4c78fda0f397'
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
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const strip = page.getByRole('navigation', { name: 'Document pages', exact: true })
    const header = strip.locator('.gallery-header')
    const settled = async () => {
      await strip.locator('ol a').first().waitFor()
      await page.waitForFunction(
        () =>
          !document.querySelector(
            '.document-page-gallery [data-slot=loadable-image][data-state=loading], .document-page-gallery [data-page-thumbnail][aria-busy=true]',
          ),
      )
    }
    const capture = async (state) => {
      await strip.scrollIntoViewIfNeeded()
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ animations: 'disabled', path: `${output}/${label}-${state}.png` })
    }
    const listResponse = (entity) =>
      page.waitForResponse((r) => {
        const url = new URL(r.url())
        return (
          url.pathname === '/api/v1/pages' &&
          (entity
            ? url.searchParams.get('filter.entity_id') === entity
            : !url.searchParams.has('filter.entity_id'))
        )
      })
    await page.goto(origin + root + first)
    await settled()
    const headerHeight = (await header.boundingBox()).height
    const stripHeight = (await strip.boundingBox()).height
    assert.equal(
      await strip
        .getByRole('button', { name: 'Select a person in the right panel to filter pages' })
        .isDisabled(),
      true,
    )
    assert.ok((await header.innerText()).includes('Page strip review practice'))
    assert.ok((await header.innerText()).includes('1/18'))
    assert.equal(await strip.locator('.search-filter-panel,.active-filters').count(), 0)
    assert.equal(
      await strip.locator('[data-page-thumbnail] [data-slot=badge]').count(),
      0,
      'no ambiguous per-page statistics',
    )
    assert.equal(await strip.locator('[data-page-thumbnail][data-person-match=true]').count(), 0)
    await capture('highlights')

    // Identity comes exclusively from the viewer's right-panel preview selection.
    await page.getByRole('button', { name: 'Preview Nora Page on this page', exact: true }).click()
    await page.waitForURL((url) => Boolean(url.searchParams.get('selectedPerson')))
    const person = new URL(page.url()).searchParams.get('selectedPerson')
    const toggle = strip.getByRole('button', { name: 'Nora Page only', exact: true })
    await toggle.waitFor()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'false')
    // Highlight matches even with the person-only filter OFF. Nonmatching pages stay visible.
    await page.waitForFunction(
      () =>
        document.querySelectorAll('.document-page-gallery [data-person-match=true]').length === 9,
    )
    await settled()
    assert.equal(await strip.locator('ol a').count(), 12)
    const borderWidths = await strip
      .locator('a:not([aria-current=page]) [data-person-match=true]')
      .evaluateAll((frames) => frames.map((frame) => getComputedStyle(frame).borderTopWidth))
    assert.ok(
      borderWidths.every((width) => width === '0px'),
      'person matches have no inner border',
    )
    assert.ok(
      await strip
        .locator('ol a')
        .nth(2)
        .getAttribute('aria-label')
        .then((text) => text.includes('appears on this page')),
      'mention-only page is highlighted',
    )
    await capture('person-highlights')
    const filtered = listResponse(person)
    await toggle.focus()
    await page.keyboard.press('Space')
    assert.equal((await (await filtered).json()).total_count, 15)
    await page.waitForURL((url) => url.searchParams.get('gallery_person_only') === 'on')
    await settled()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true')
    assert.equal(await strip.locator('ol a[aria-current=page]').count(), 0)
    assert.equal(new URL(page.url()).pathname, root + first)
    assert.equal(
      (await header.boundingBox()).height,
      headerHeight,
      'header never grows when filtering',
    )
    assert.ok((await header.innerText()).includes('1/18'), 'position remains document scoped')
    await capture('person-filter')

    // A different right-panel selection changes the active scope without another selector.
    await page.getByRole('button', { name: 'Preview Otto Page on this page', exact: true }).click()
    await strip.getByRole('button', { name: 'Otto Page only', exact: true }).waitFor()
    await settled()
    assert.equal(await strip.locator('ol a').count(), 1)
    assert.equal(
      (await strip.boundingBox()).height,
      stripHeight,
      'assigned-only results retain strip height',
    )
    await page.getByRole('button', { name: 'Preview Nora Page on this page', exact: true }).click()
    await toggle.waitFor()
    await settled()
    const mentionOnly = strip.locator('ol a').nth(1)
    const target = await mentionOnly.getAttribute('href')
    assert.ok(target.includes(`selectedPerson=${person}`))
    assert.ok(target.includes('gallery_person_only=on'))
    await mentionOnly.click()
    await page.waitForURL((url) => url.pathname !== root + first)
    await page.reload()
    await settled()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true')
    const unfiltered = listResponse(null)
    await toggle.click()
    assert.equal((await (await unfiltered).json()).total_count, 18)
    await page.goBack()
    await page.waitForURL((url) => url.searchParams.get('gallery_person_only') === 'on')
    await settled()

    // The compact sort control retains the person scope and header geometry.
    const sort = strip.getByRole('combobox', { name: 'Sort pages', exact: true })
    await sort.click()
    await page.getByRole('option', { name: 'Page number · Highest first', exact: true }).click()
    await page.waitForURL((url) => url.searchParams.get('gallery_dir') === 'desc')
    await settled()
    assert.equal(new URL(page.url()).searchParams.get('selectedPerson'), person)
    assert.equal((await header.boundingBox()).height, headerHeight)
    await sort.click()
    await page.getByRole('option', { name: 'Page number · Lowest first', exact: true }).click()
    await page.waitForURL((url) => !url.searchParams.has('gallery_dir'))
    await settled()

    // Long real synthetic names keep the same one-line header geometry.
    const login = await page.request.post(api + '/token/login', {
      form: {
        username: 'test',
        password: 'test',
        scope: 'people-gator:browse people-gator:annotate',
      },
    })
    assert.ok(login.ok())
    const token = (await login.json()).access_token
    const headers = { Authorization: `Bearer ${token}` }
    const longName =
      'Nora Page with a very long synthetic catalogue identity for compact header review'
    try {
      assert.ok(
        (
          await page.request.patch(`${api}/api/v1/entities/${person}`, {
            headers,
            data: { name: longName },
          })
        ).ok(),
      )
      await page.reload()
      await settled()
      await strip.getByRole('button', { name: `${longName} only`, exact: true }).waitFor()
      assert.equal((await header.boundingBox()).height, headerHeight)
      await capture('long-name')
    } finally {
      assert.ok(
        (
          await page.request.patch(`${api}/api/v1/entities/${person}`, {
            headers,
            data: { name: 'Nora Page' },
          })
        ).ok(),
      )
    }

    // Current assigned page: retain the double frame, with no unnecessary face counter.
    const currentAssignedPath = await strip.locator('ol a').first().getAttribute('href')
    await page.goto(origin + currentAssignedPath)
    await settled()
    const currentFrame = strip.locator('a[aria-current=page] [data-page-thumbnail]')
    assert.equal(
      await currentFrame.evaluate((frame) => getComputedStyle(frame).borderTopWidth),
      '2px',
    )
    assert.equal(await currentFrame.locator('[data-slot=badge]').count(), 0)
    await capture('current-assigned')
    await strip.screenshot({
      animations: 'disabled',
      path: `${output}/${label}-current-assigned-strip.png`,
    })

    // Earlier saved links restore the same right-panel identity and migrate on toggle.
    await page.goto(origin + root + first + '?gallery_person=' + person)
    await settled()
    await toggle.waitFor()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true')
    await toggle.click()
    await page.waitForURL(
      (url) =>
        !url.searchParams.has('gallery_person') &&
        url.searchParams.get('selectedPerson') === person,
    )
    await settled()

    await page.goto(
      origin +
        root +
        first +
        '?selectedPerson=00000000-0000-4000-8000-000000000099&gallery_person_only=on',
    )
    await strip.getByText('No matching pages.', { exact: true }).waitFor()
    assert.equal((await header.boundingBox()).height, headerHeight)
    assert.equal(
      (await strip.boundingBox()).height,
      stripHeight,
      'empty results retain strip height',
    )
    await capture('empty')
    await strip.getByRole('button', { name: 'Selected person only', exact: true }).click()
    await settled()
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await capture('dark')
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    )
    assert.deepEqual(errors, [])
    console.log(
      `${label}: no annotation counters, orange border states, unfiltered person highlights, sidebar-only person selection, keyboard toggle, face/mention matches, fixed header height, sorting, URL/history, legacy links, unknown person, long names and dark mode passed`,
    )
    await context.close()
  }
} finally {
  await browser.close()
}
