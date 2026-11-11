// Run against this revision's real, migrated/twice-seeded synthetic application.
import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.PANEL_LAYOUT_ORIGIN || 'http://localhost:5139'
const seed = JSON.parse(
  await readFile(
    process.env.PANEL_LAYOUT_SEED || '../people-gator-api/.cache/issue139-review-seed.json',
    'utf8',
  ),
)
const output = process.env.PANEL_LAYOUT_EVIDENCE || '../docs/evidence/issue139'
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
try {
  for (const [label, width, height] of [
    ['desktop', 1440, 900],
    ['mobile', 390, 844],
  ]) {
    const wide = label === 'desktop'
    const page = await browser.newPage({ viewport: { width, height } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const url = new URL(seed.filter_examples['page-panel-layout'], origin).href
    const button = (name) => page.getByRole('button', { name, exact: true })
    const transcription = page.locator('#transcription-panel')
    const people = page.locator('#people-panel')
    const settle = async () => {
      await page.waitForFunction(() =>
        [...document.querySelectorAll('.workspace-gallery img')].every((img) => img.complete),
      )
      await page.waitForTimeout(160)
    }
    const capture = async (state) => {
      await page.evaluate(() => window.scrollTo(0, 0))
      await settle()
      await page.screenshot({ path: `${output}/${label}-${state}.png`, animations: 'disabled' })
    }
    await page.goto(url)
    await button('Hide transcription panel').waitFor()
    await page.getByText('25 occurrences', { exact: true }).first().waitFor()
    await settle()
    const initial = await transcription.boundingBox()
    if (wide) {
      const leftHide = await button('Hide transcription panel').boundingBox()
      assert(
        initial.x + initial.width - leftHide.x - leftHide.width < 32,
        'transcription hide belongs beside viewer',
      )
      const sidebar = await people.boundingBox()
      const rightHide = await button('Hide people panel').boundingBox()
      assert(rightHide.x - sidebar.x < 24, 'People hide belongs beside viewer')
    } else {
      assert.equal(await button('Hide people panel').count(), 0)
    }
    await capture('panels-open')
    await page.locator('.panzoom-layer').evaluate((node) => (node.dataset.retained = 'yes'))
    await button('Hide transcription panel').focus()
    await page.keyboard.press('Enter')
    await settle()
    assert.equal(await transcription.isVisible(), false)
    assert.equal(
      await button('Open transcription panel').evaluate((node) => node === document.activeElement),
      true,
    )
    if (!wide) {
      const bar = button('Open transcription panel').locator('..')
      assert.match(await bar.innerText(), /Transcription/)
      assert((await bar.boundingBox()).height < 60, 'mobile collapse leaves one short bar')
      assert.equal(
        await page
          .locator('header.viewer-tools')
          .getByRole('button', { name: 'Open transcription panel' })
          .count(),
        0,
      )
    }
    await capture('left-hidden')
    if (wide) {
      await button('Hide people panel').click()
      await settle()
      assert.equal(await people.isVisible(), false)
      assert(Math.abs((await page.locator('.workspace-viewer').boundingBox()).width - width) < 2)
      await capture('both-hidden')
      await button('Open transcription panel').click()
      await capture('right-hidden')
      await button('Open people panel').click()
    } else {
      assert.equal(await people.isVisible(), true)
      await people.scrollIntoViewIfNeeded()
      await settle()
      await page.screenshot({ path: `${output}/mobile-people-visible.png`, animations: 'disabled' })
      await button('Open transcription panel').click()
    }
    await settle()
    const restored = await transcription.boundingBox()
    assert(
      Math.abs(
        (wide ? restored.width : restored.height) - (wide ? initial.width : initial.height),
      ) < 2,
    )
    assert.equal(await page.locator('.panzoom-layer').getAttribute('data-retained'), 'yes')
    assert.equal(page.url(), url)
    await capture('reopened')
    const resize = page.getByRole('separator', {
      name: wide ? 'Resize sidebar' : 'Resize transcription panel',
      exact: true,
    })
    await resize.focus()
    await page.keyboard.press(wide ? 'ArrowLeft' : 'ArrowDown')
    await settle()
    await capture('resized')
    if (wide) {
      const saved = await page.evaluate(() => localStorage.getItem('document-sidebar-width-v1'))
      assert(saved && Number(saved) >= 400)
      await button('Hide people panel').click()
      await button('Search people by this face').click()
      const search = page.getByRole('textbox', { name: 'Search people', exact: true })
      await search.waitFor()
      await settle()
      assert.equal(await search.evaluate((node) => node === document.activeElement), true)
      assert.equal(await people.isVisible(), true)
      await button('Hide people panel').click()
      await page.setViewportSize({ width: 390, height: 844 })
      await settle()
      assert.equal(await people.isVisible(), true)
      assert.equal(await button('Hide people panel').count(), 0)
      assert.equal(await button('Open people panel').count(), 0)
      await page.setViewportSize({ width, height })
      await settle()
      assert.equal(await people.isVisible(), false)
      await button('Open people panel').click()
      await settle()
      assert.equal(
        await page.evaluate(() => localStorage.getItem('document-sidebar-width-v1')),
        saved,
      )
    }
    // Expanded pages must leave all applicable reopen controls reachable.
    await button('Hide transcription panel').click()
    if (wide) await button('Hide people panel').click()
    await button('Expand pages').click()
    await page.locator('[aria-label="Document pages grid"]').waitFor()
    await capture('expanded')
    await button('Open transcription panel').click()
    if (wide) await button('Open people panel').click()
    await button('Collapse pages').focus()
    await page.keyboard.press('Enter')
    await settle()
    assert.equal(await page.locator('.workspace-viewer').isVisible(), true)
    assert.equal(await page.locator('.panzoom-layer').getAttribute('data-retained'), 'yes')
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    if (!wide) await people.scrollIntoViewIfNeeded()
    await settle()
    await page.screenshot({ path: `${output}/${label}-dark-reopened.png`, animations: 'disabled' })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true,
    )
    assert.deepEqual(errors, [])
    console.log(
      `${label}: viewer-adjacent hide, responsive collapse, focus/state/size retention, action reveal, expanded pages and dark layout passed`,
    )
    await page.close()
  }
} finally {
  await browser.close()
}
