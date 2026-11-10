// Run against this revision's migrated, twice-seeded synthetic application.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.SOURCE_TAG_ORIGIN || 'http://127.0.0.1:5138'
const output = process.env.SOURCE_TAG_EVIDENCE || '../docs/evidence/issue138'
const path =
  '/libraries/preview-mzk/documents/d2df066b-d238-5b4a-ae7e-97986273df7f/pages/782fe729-546b-530b-9c73-afbbe8f237b4'
const face = '55c52330-25ed-4d0d-97a7-68a050363a5d'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height },
      hasTouch: label === 'mobile',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const card = (name) =>
      page.getByRole('button', { name: `Preview ${name} on this page`, exact: true }).locator('..')
    const visit = async (query) => {
      await page.goto(origin + path + '?' + query)
      await card('Hana Sidebar').waitFor()
      await page.waitForFunction(() => !document.querySelector('[data-source="unknown"]'))
    }
    const capture = async (state) => {
      await card('Hana Sidebar').scrollIntoViewIfNeeded()
      await page.screenshot({ path: `${output}/${label}-${state}.png` })
    }
    await visit('people_scope=all&candidate_sort=context')
    for (const [name, source] of [
      ['Hana Sidebar', 'page'],
      ['Tomas Lettered', 'page'],
      ['Rosa Elsewhere', 'document'],
      ['Karel Crowd', 'document'],
      ['Ada Novak', 'database'],
    ]) {
      assert.equal(await card(name).locator('[data-source]').getAttribute('data-source'), source)
      assert.equal(await card(name).locator('[aria-label="Similarity scores"]').count(), 0)
    }
    const hana = card('Hana Sidebar')
    assert.ok(
      !(await hana.getAttribute('class')).split(' ').includes('ring-secondary'),
      'page context never outlines the whole card',
    )
    assert.ok(
      (await hana.locator('[data-source="page"]').getAttribute('class')).includes('ring-secondary'),
    )
    const media = hana.locator('[data-slot="item-media"]')
    const portraitBox = await media.locator('[data-slot="avatar"]').boundingBox()
    const tagBox = await media.locator('[data-source]').boundingBox()
    assert.ok(tagBox.y >= portraitBox.y + portraitBox.height, 'source is below portrait')
    await capture('contexts')
    await page
      .getByRole('button', { name: 'Preview Hana Sidebar on this page', exact: true })
      .click()
    assert.equal(
      await page
        .getByRole('button', { name: 'Preview Hana Sidebar on this page', exact: true })
        .getAttribute('aria-pressed'),
      'true',
    )
    await capture('selected')
    for (const [mode, query] of [
      ['text', 'candidate_text=Hana'],
      ['face', `candidate_face=${face}`],
      ['combined', `candidate_text=Hana&candidate_face=${face}`],
    ]) {
      await visit(`people_scope=all&candidate_sort=relevance&${query}`)
      const scores = card('Hana Sidebar').locator('[aria-label="Similarity scores"]')
      await scores.waitFor()
      assert.equal(
        await scores.locator('[aria-label^="Text search score"]').count(),
        mode === 'face' ? 0 : 1,
      )
      assert.equal(
        await scores.locator('[aria-label^="Face similarity"]').count(),
        mode === 'text' ? 0 : 1,
      )
      if (mode !== 'text')
        assert.match(await scores.locator('[aria-label^="Face similarity"]').textContent(), /%/)
      const sourceBox = await card('Hana Sidebar').locator('[data-source]').boundingBox()
      const scoreBox = await scores.boundingBox()
      assert.ok(scoreBox.y >= sourceBox.y + sourceBox.height, 'scores are below source')
      await capture(mode)
    }
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.reload()
    await card('Hana Sidebar').waitFor()
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await capture('dark')
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
      'no page overflow',
    )
    assert.deepEqual(errors, [])
    results.push({
      viewport: label,
      width,
      height,
      checks: [
        'face and mention page membership',
        'sibling document membership',
        'outside-document membership',
        'portrait/tag/score order',
        'selection independent of context',
        'text/face/combined scores',
        'dark mode',
        'no overflow or browser errors',
      ],
    })
    await context.close()
  }
} finally {
  await browser.close()
}
await writeFile(`${output}/results.json`, JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
