import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import {
  adjacentIncluded,
  contextIndices,
  includedLines,
  minimapLines,
  modeLines,
  nearestIncluded,
  parseAnnotationHighlight,
  parseLineVisibility,
  passages,
  useTeleprompterLines,
  type LineVisibility,
} from '@/viewmodels/teleprompter'

const position = { left: 0, top: 0, width: 1, height: 1 }
function mention(
  lineId: string,
  entityId: string,
  text: string,
  start: number,
  extra: Partial<TranscriptionEntitySpan> = {},
): TranscriptionEntitySpan {
  return {
    mention_id: `${entityId}-${lineId}-${start}`,
    entity_id: entityId,
    label: 'person',
    text,
    line_id: lineId,
    start_index: start,
    end_index: start + text.length,
    linkState: 'automatic',
    ...extra,
  }
}

/** Ada on L2 and L7, a same-name identity on L4, and a two-line Ada mention on L9–L10. */
function sample(): TranscriptionLine[] {
  const texts = [
    'The ledger opens.',
    'Ada Novak signed it.',
    'Plain context line.',
    'Ada Novak of another family.',
    'More context.',
    'Even more context.',
    'Ada Novak returned.',
    'Unrelated note.',
    'Written by Ada',
    'Novak at dusk.',
  ]
  const lines: TranscriptionLine[] = texts.map((text, index) => ({
    id: `L${index + 1}`,
    text,
    position,
    entities: [],
  }))
  lines[1]!.entities = [mention('L2', 'ada', 'Ada Novak', 0, { linkState: 'verified' })]
  lines[3]!.entities = [mention('L4', 'other-ada', 'Ada Novak', 0)]
  lines[6]!.entities = [mention('L7', 'ada', 'Ada Novak', 0, { linkState: 'manual' })]
  lines[8]!.entities = [mention('L9', 'ada', 'Ada', 11, { mention_id: 'multi' })]
  lines[9]!.entities = [
    mention('L10', 'ada', 'Novak', 0, { mention_id: 'multi', firstFragment: false }),
  ]
  return lines
}

describe('teleprompter line visibility', () => {
  it('matches the selected identity by ID, keeping original lines and multiline fragments', () => {
    const lines = sample()
    const ada = modeLines(lines, 'person', 'ada')
    expect(ada.flatMap((value, index) => (value ? [index + 1] : []))).toEqual([2, 7, 9, 10])
    expect(passages(ada)).toEqual([
      { start: 1, end: 1 },
      { start: 6, end: 6 },
      { start: 8, end: 9 },
    ])
    expect(modeLines(lines, 'annotated', null).filter(Boolean)).toHaveLength(5)
    expect(modeLines(lines, 'all', null).every(Boolean)).toBe(true)
  })

  it('keeps Person mode empty without a selected person or matches', () => {
    expect(modeLines(sample(), 'person', null).some(Boolean)).toBe(false)
    expect(modeLines(sample(), 'person', 'nobody').some(Boolean)).toBe(false)
  })

  it('reveals context in either direction, clamped, and merges overlaps', () => {
    const base = modeLines(sample(), 'person', 'ada')
    const first = passages(base)[0]!
    expect(contextIndices(first, 'after', 1, 10)).toEqual([2])
    expect(contextIndices(first, 'before', 5, 10)).toEqual([0])
    const second = passages(base)[1]!
    const revealed = new Set([
      ...contextIndices(first, 'after', 5, 10),
      ...contextIndices(second, 'before', 5, 10),
    ])
    // L3–L7 revealed from both sides merge with L2 and L7 into one passage.
    expect(passages(includedLines(base, revealed))).toEqual([
      { start: 1, end: 6 },
      { start: 8, end: 9 },
    ])
  })

  it('finds nearest and adjacent included lines, preferring the earlier tie', () => {
    const included = [false, true, false, true, false]
    expect(nearestIncluded(included, 2)).toBe(1)
    expect(nearestIncluded(included, 4)).toBe(3)
    expect(nearestIncluded([false, false], 0)).toBeNull()
    expect(adjacentIncluded(included, 1, 'next')).toBe(3)
    expect(adjacentIncluded(included, 3, 'next')).toBeNull()
    expect(adjacentIncluded(included, 1, 'previous')).toBeNull()
  })

  it('parses unknown URL values to the defaults', () => {
    expect(parseLineVisibility('person')).toBe('person')
    expect(parseLineVisibility('bogus')).toBe('all')
    expect(parseAnnotationHighlight('verified')).toBe('verified')
    expect(parseAnnotationHighlight(undefined)).toBe('all')
  })

  it('starts fresh when the page, person or mode changes', async () => {
    const lines = ref(sample())
    const mode = ref<LineVisibility>('person')
    const person = ref<string | null>('ada')
    const page = ref('one')
    const state = useTeleprompterLines(lines, mode, person, page)
    state.expand(state.passages.value[0]!, 'after', 1)
    expect(state.hasExpansions.value).toBe(true)
    expect(state.included.value[2]).toBe(true)
    for (const change of [
      () => (person.value = 'other-ada'),
      () => (mode.value = 'annotated'),
      () => (page.value = 'two'),
    ]) {
      state.reveal([2])
      change()
      await nextTick()
      expect(state.hasExpansions.value).toBe(false)
    }
    state.reveal([2])
    state.reset()
    expect(state.included.value[2]).toBe(false)
  })

  it('builds page-scoped minimap bars with highlighted segments only on included lines', () => {
    const lines = sample()
    const included = modeLines(lines, 'person', 'ada')
    const bars = minimapLines(lines, included, 'verified', 'ada')
    expect(bars).toHaveLength(10)
    expect(bars.filter((bar) => bar.included).map((bar) => bar.index)).toEqual([1, 6, 8, 9])
    expect(bars[1]!.segments).toHaveLength(1)
    expect(bars[1]!.segments[0]!.related).toBe(true)
    // Verified highlighting drops the manual mention's segment, never its line.
    expect(bars[6]!.included).toBe(true)
    expect(bars[6]!.segments).toHaveLength(0)
  })
})

describe('DocumentTeleprompter', () => {
  const cleanup: Array<() => void> = []
  afterEach(() => cleanup.splice(0).forEach((fn) => fn()))

  function render(props: Record<string, unknown> = {}) {
    const wrapper = mount(DocumentTeleprompter, {
      attachTo: document.body,
      props: {
        transcription: sample(),
        selectedLineIndex: 1,
        selectedEntityKey: null,
        relatedEntityId: 'ada',
        ...props,
      },
    })
    cleanup.push(() => wrapper.unmount())
    return wrapper
  }

  it('shows original line numbers with collapsed-gap controls only where lines remain', () => {
    const wrapper = render({
      lineVisibility: 'person',
      included: modeLines(sample(), 'person', 'ada'),
    })
    const numbers = wrapper.findAll('[data-line-index] small').map((label) => label.text())
    expect(numbers).toEqual(['L2', 'L7', 'L9', 'L10'])
    const gaps = wrapper.findAll('[data-gap-start]')
    expect(gaps.map((gap) => gap.get('small').text())).toEqual(['1 hidden', '4 hidden', '1 hidden'])
    expect(
      gaps.map((gap) => gap.findAll('button').map((button) => button.attributes('aria-label'))),
    ).toEqual([
      ['Show 1 more line before L2', 'Show 5 more lines before L2'],
      [
        'Show 1 more line after L2',
        'Show 5 more lines after L2',
        'Show 1 more line before L7',
        'Show 5 more lines before L7',
      ],
      [
        'Show 1 more line after L7',
        'Show 5 more lines after L7',
        'Show 1 more line before L9',
        'Show 5 more lines before L9',
      ],
    ])
    // Nothing is hidden after the final passage, so it has no trailing controls.
    expect(wrapper.find('[data-gap-start="10"]').exists()).toBe(false)
  })

  it('emits expansion for the passage and direction of each control', async () => {
    const wrapper = render({
      lineVisibility: 'person',
      included: modeLines(sample(), 'person', 'ada'),
    })
    await wrapper.get('[aria-label="Show 5 more lines before L7"]').trigger('click')
    await wrapper.get('[aria-label="Show 1 more line after L2"]').trigger('click')
    expect(wrapper.emitted('expand')).toEqual([
      [{ start: 6, end: 6 }, 'before', 5],
      [{ start: 1, end: 1 }, 'after', 1],
    ])
  })

  it.each([
    ['person', null, 'Select a person to see their lines.'],
    ['person', 'nobody', 'No lines for this person. Select another person or switch to All.'],
    ['annotated', null, 'No annotated lines. Switch to All.'],
  ])('keeps %s mode empty with a short message', (mode, person, message) => {
    const transcription = sample().map((line) => ({ ...line, entities: [] }))
    const wrapper = render({
      transcription,
      relatedEntityId: person,
      lineVisibility: mode,
      included: modeLines(transcription, mode as LineVisibility, person),
      isTranslationOpen: true,
    })
    expect(wrapper.text()).toContain(message)
    expect(wrapper.find('[data-line-index]').exists()).toBe(false)
    // Settings stay available, and no stale translation is shown.
    expect(wrapper.find('[aria-label="Teleprompter settings"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Translate teleprompter text"]').exists()).toBe(false)
  })

  it('changes highlighted annotations without changing the visible lines', async () => {
    const included = modeLines(sample(), 'annotated', null)
    const wrapper = render({ lineVisibility: 'annotated', included })
    const lineCount = wrapper.findAll('[data-line-index]').length
    expect(wrapper.findAll('mark')).toHaveLength(5)
    await wrapper.setProps({ annotationHighlight: 'verified' })
    expect(wrapper.findAll('[data-line-index]')).toHaveLength(lineCount)
    expect(wrapper.findAll('mark').map((mark) => mark.text())).toEqual(['Ada Novak'])
    expect(wrapper.text()).toContain('Ada Novak returned.')
  })

  it('switches line visibility and offers Reset only for manual expansions', async () => {
    const wrapper = render()
    expect(wrapper.findAll('button').some((button) => button.text() === 'Reset')).toBe(false)
    await wrapper.get('[role="toolbar"] button[value="annotated"]').trigger('click')
    expect(wrapper.emitted('update:lineVisibility')).toEqual([['annotated']])
    await wrapper.setProps({ hasExpansions: true })
    const reset = wrapper.findAll('button').find((button) => button.text() === 'Reset')!
    await reset.trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('copies selected text with line breaks, excluding numbers and badges', () => {
    const wrapper = render()
    const lines = wrapper.findAll('[data-line-text]').map((line) => line.element)
    const range = document.createRange()
    range.setStart(lines[1]!.firstChild!, 0)
    range.setEnd(lines[2]!, lines[2]!.childNodes.length)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    const data = new Map<string, string>()
    const event = new Event('copy', { bubbles: true, cancelable: true }) as ClipboardEvent
    Object.defineProperty(event, 'clipboardData', {
      value: { setData: (type: string, value: string) => data.set(type, value) },
    })
    wrapper.get('[aria-label="Transcription teleprompter"]').element.dispatchEvent(event)
    expect(data.get('text/plain')).toBe('Ada Novak signed it.\nPlain context line.')
    expect(event.defaultPrevented).toBe(true)
    selection.removeAllRanges()
  })

  it('clears a text selection when its lines become hidden', async () => {
    const wrapper = render()
    const line = wrapper.findAll('[data-line-text]')[2]!.element
    const range = document.createRange()
    range.selectNodeContents(line)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    await wrapper.setProps({ included: modeLines(sample(), 'person', 'ada') })
    expect(selection.rangeCount).toBe(0)
  })

  it('does not change the selected line while a text selection is active', async () => {
    const wrapper = render()
    const range = document.createRange()
    range.selectNodeContents(wrapper.findAll('[data-line-text]')[3]!.element)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    await wrapper.findAll('[data-line-index]')[3]!.trigger('click')
    expect(wrapper.emitted('select-line')).toBeUndefined()
    window.getSelection()!.removeAllRanges()
    await wrapper.findAll('[data-line-index]')[3]!.trigger('click')
    expect(wrapper.emitted('select-line')).toEqual([[3]])
  })

  it('grays hidden lines in the minimap and keeps wheel scrolling native', () => {
    const wrapper = render({ included: modeLines(sample(), 'person', 'ada') })
    const bars = wrapper.findAll('[data-minimap-line]')
    expect(bars).toHaveLength(10)
    expect(bars.map((bar) => bar.attributes('data-included'))).toEqual([
      'false',
      'true',
      'false',
      'false',
      'false',
      'false',
      'true',
      'false',
      'true',
      'true',
    ])
    const wheel = new WheelEvent('wheel', { deltaY: 120, cancelable: true, bubbles: true })
    wrapper.get('[aria-label="Transcription teleprompter"]').element.dispatchEvent(wheel)
    expect(wheel.defaultPrevented).toBe(false)
    expect(wrapper.emitted('select-line')).toBeUndefined()
  })

  it('scrolls the text from wheel input over the minimap, which replaces its scrollbar', () => {
    const wrapper = render()
    const text = wrapper.get('[aria-label="Transcription teleprompter"]')
    expect(text.classes()).toContain('teleprompter-scroll')
    const wheel = new WheelEvent('wheel', { deltaY: 90, cancelable: true, bubbles: true })
    wrapper.get('[data-teleprompter-minimap]').element.dispatchEvent(wheel)
    expect(wheel.defaultPrevented).toBe(true)
    expect(text.element.scrollTop).toBe(90)
    expect(wrapper.emitted('select-line')).toBeUndefined()
  })
})
