// Run against a migrated, twice-seeded local application; see docs/TEST.md.
// BOX_DRAG_SEED_LOG is the output of the second seed CLI run.
import assert from 'node:assert/strict'
import { mkdir, readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.BOX_DRAG_ORIGIN || 'http://127.0.0.1:5173'
const log = await readFile(process.env.BOX_DRAG_SEED_LOG || '/tmp/issue112-seed.log', 'utf8')
const routes = Object.fromEntries(
  [...log.matchAll(/^(scan-box-drag[^:]*): https?:\/\/[^/]+(.+)$/gm)].map((m) => [m[1], m[2]]),
)
assert.ok(routes['scan-box-drag'] && routes['scan-box-drag-selected'], 'seed links exist')
const output = process.env.BOX_DRAG_EVIDENCE || '../docs/evidence/issue-112'
await mkdir(output, { recursive: true })

const results = []
const browser = await chromium.launch({ headless: true })
try {
  for (const [label, width, height, touch] of [
    ['desktop', 1440, 900, false],
    ['mobile', 390, 844, true],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height },
      hasTouch: touch,
      isMobile: touch,
      deviceScaleFactor: 2,
    })
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const cdp = touch ? await context.newCDPSession(page) : null
    const layer = page.locator('.panzoom-layer')
    const viewer = page.locator('section[aria-label="Pan and zoom document page"]')
    const actions = page.locator('[data-detection-actions]')
    const selectedFace = page.locator('[data-region-type="face"][aria-pressed="true"]')
    const transform = () => layer.evaluate((node) => node.style.transform)
    const record = (name, ok) => results.push(`${label}: ${name}: ${ok ? 'pass' : 'FAIL'}`)

    async function open(route) {
      await page.goto(origin + routes[route])
      await page.locator('[data-region-type="face"]').nth(1).waitFor()
      await page.locator('[data-region-type="line"]').nth(1).waitFor()
      await page.waitForFunction(() => document.fonts.status === 'loaded')
      await viewer.scrollIntoViewIfNeeded()
      await page.waitForTimeout(400)
    }
    // Start one zoom step in from the default view. The short mobile viewer instead
    // zooms out and pans up from the blank margin, exposing both OCR lines.
    async function zoomed() {
      await page.getByRole('button', { name: 'Center page' }).click()
      await page.getByRole('button', { name: touch ? 'Zoom out' : 'Zoom in' }).click()
      await page.waitForTimeout(300)
      if (touch) {
        const area = await viewer.boundingBox()
        // A mouse pan: after a CDP touch sequence Chrome sends no click for the next tap.
        await page.mouse.move(area.x + 8, area.y + area.height - 16)
        await page.mouse.down()
        await page.mouse.move(area.x + 8, area.y + area.height - 166, { steps: 8 })
        await page.mouse.up()
        await page.waitForTimeout(300)
      }
    }
    // The first unselected box of a type whose centre is actually exposed to the pointer.
    async function target(type, { selected = false } = {}) {
      const found = await page.evaluate(
        ({ type, selected }) => {
          for (const box of document.querySelectorAll(`[data-region-type="${type}"]`)) {
            if ((box.getAttribute('aria-pressed') === 'true') !== selected) continue
            const rect = box.getBoundingClientRect()
            const x = rect.left + rect.width / 2
            const y = rect.top + rect.height / 2
            if (box.contains(document.elementFromPoint(x, y)))
              return { x, y, id: box.dataset.detectionId ?? box.getAttribute('aria-label') }
          }
          return null
        },
        { type, selected },
      )
      assert.ok(found, `an exposed ${type} box exists`)
      const attribute = type === 'face' ? 'data-detection-id' : 'aria-label'
      return {
        ...found,
        pressed: () =>
          page
            .locator(`[data-region-type="${type}"][${attribute}="${found.id}"]`)
            .getAttribute('aria-pressed'),
      }
    }
    async function touchEvent(type, points) {
      await cdp.send('Input.dispatchTouchEvent', {
        type,
        touchPoints: points.map(([x, y], id) => ({ x, y, id })),
      })
    }
    // Drag from a point by dx/dy in steps; touch uses real touch input.
    async function drag(start, dx, dy, { cancel = false, steps = 8 } = {}) {
      if (touch) {
        await touchEvent('touchStart', [[start.x, start.y]])
        for (let i = 1; i <= steps; i++)
          await touchEvent('touchMove', [[start.x + (dx * i) / steps, start.y + (dy * i) / steps]])
        await touchEvent(cancel ? 'touchCancel' : 'touchEnd', [])
      } else {
        await page.mouse.move(start.x, start.y)
        await page.mouse.down()
        await page.mouse.move(start.x + dx, start.y + dy, { steps })
        await page.mouse.up()
      }
      // Longer than a focus animation frame, so a stray refocus would show.
      await page.waitForTimeout(400)
    }
    // A click, or a tap that Chrome's own tap slop classifies.
    async function press(point, dx = 0, dy = 0) {
      if (touch) {
        await page.touchscreen.tap(point.x, point.y)
        await page.waitForTimeout(400)
      } else await drag(point, dx, dy, { steps: 2 })
    }
    async function pans(name, type, dx, dy, options) {
      await zoomed()
      const box = await target(type)
      const before = await transform()
      await drag(box, dx, dy, options)
      const after = await transform()
      record(`${name} pans`, before !== after)
      record(`${name} selects nothing`, (await box.pressed()) === 'false')
      await page.waitForTimeout(300)
      record(`${name} does not refocus`, (await transform()) === after)
      record(`${name} opens no actions`, (await actions.count()) === 0)
    }

    // 1. Drags from inside OCR-line and face boxes pan without selecting.
    await open('scan-box-drag')
    await pans('line drag', 'line', 90, 60)
    await pans('face drag', 'face', -70, -50)
    await page.screenshot({ path: `${output}/${label}-after-box-drag.png` })
    // The pointer leaves the box during the drag; touch also checks cancellation.
    await pans('drag leaving box', 'face', 0, 240)
    if (touch) await pans('cancelled drag', 'line', 40, 40, { cancel: true })

    // 2. A press under the threshold is still a click/tap. Line 0 starts selected.
    await zoomed()
    const line = await target('line')
    await press(line, 3, 2)
    record('short line press selects', (await line.pressed()) === 'true')
    await zoomed()
    const face = await target('face')
    await press(face)
    record('face click selects', (await face.pressed()) === 'true')
    await actions.first().waitFor()
    record('face click opens actions', (await actions.count()) === 1)

    // 3. Keyboard activation still works.
    const unselected = page.locator('[data-region-type="line"][aria-pressed="false"]').first()
    const keyed = page.locator(
      `[data-region-type="line"][aria-label="${await unselected.getAttribute('aria-label')}"]`,
    )
    await keyed.focus()
    await page.keyboard.press('Enter')
    await page.waitForTimeout(300)
    record('keyboard selects line', (await keyed.getAttribute('aria-pressed')) === 'true')

    // 4. With actions open, dragging from another box keeps them and the selection.
    await open('scan-box-drag-selected')
    await actions.first().waitFor()
    const selectedId = await selectedFace.getAttribute('data-detection-id')
    for (const type of ['face', 'line']) {
      // Automatic focus zooms to the selected face; this view exposes the others.
      await zoomed()
      const box = await target(type)
      const before = await transform()
      await drag(box, 50, 40)
      record(`${type} drag with actions open pans`, before !== (await transform()))
      record(
        `${type} drag with actions open keeps selection`,
        (await selectedFace.getAttribute('data-detection-id')) === selectedId,
      )
      record(`${type} drag with actions open keeps actions`, (await actions.count()) === 1)
    }
    await page.screenshot({ path: `${output}/${label}-actions-after-drag.png` })
    record('action buttons enabled', await actions.getByRole('button').first().isEnabled())

    assert.deepEqual(errors, [])
    await context.close()
  }
} finally {
  await browser.close()
  console.log(results.join('\n'))
}
assert.ok(
  results.every((line) => line.endsWith('pass')),
  'all browser checks pass',
)
