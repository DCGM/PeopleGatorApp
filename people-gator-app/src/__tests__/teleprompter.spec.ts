import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import {
  adjacentIncluded,
  contextIndices,
  includedLines,
  minimapLines,
  modeLines,
  nearestIncluded,
  highlightsSpan,
  parseHighlightStates,
  parseLineVisibility,
  passages,
  useTeleprompterLines,
  type HighlightState,
  type LineMode,
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

  it('narrows Annotated and Person lines to annotations in the chosen states', () => {
    const lines = sample()
    const shown = (values: boolean[]) =>
      values.flatMap((value, index) => (value ? [index + 1] : []))
    // Ada: verified on L2, manual on L7, automatic on L9–L10; another identity on L4.
    expect(shown(modeLines(lines, 'annotated', null, ['verified']))).toEqual([2])
    expect(shown(modeLines(lines, 'annotated', null, ['manual', 'automatic']))).toEqual([
      4, 7, 9, 10,
    ])
    expect(shown(modeLines(lines, 'person', 'ada', ['automatic']))).toEqual([9, 10])
    // A matching annotation of another person does not qualify a Person line.
    expect(shown(modeLines(lines, 'person', 'other-ada', ['verified']))).toEqual([])
    expect(shown(modeLines(lines, 'all', null, ['verified']))).toHaveLength(10)
  })

  it('keeps Custom lines when the annotation states change', async () => {
    const mode = ref<LineVisibility>('annotated')
    const states = ref<HighlightState[]>(['verified'])
    const state = useTeleprompterLines(ref(sample()), mode, ref(null), ref('one'), states)
    const shown = () => state.included.value.flatMap((value, index) => (value ? [index + 1] : []))
    expect(shown()).toEqual([2])
    state.reveal([2])
    expect(shown()).toEqual([2, 3])
    states.value = []
    await nextTick()
    expect(mode.value).toBe('custom')
    expect(shown()).toEqual([2, 3])
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
    expect(parseHighlightStates('verified')).toEqual(['verified'])
    expect(parseHighlightStates(['unassigned', 'bogus', 'manual'])).toEqual([
      'manual',
      'unassigned',
    ])
    expect(parseHighlightStates(undefined)).toEqual([])
  })

  it('highlights every span without states, otherwise only the chosen states', () => {
    const automatic = mention('L1', 'ada', 'Ada', 0)
    const verified = mention('L1', 'ada', 'Ada', 0, { linkState: 'verified' })
    const unlinked = mention('L1', '', 'Ada', 0, { entity_id: undefined, linkState: null })
    expect([automatic, verified, unlinked].map((span) => highlightsSpan(span, []))).toEqual([
      true,
      true,
      true,
    ])
    expect(
      [automatic, verified, unlinked].map((span) =>
        highlightsSpan(span, ['verified', 'unassigned']),
      ),
    ).toEqual([false, true, true])
  })

  it('switches to Custom when lines are revealed and keeps it across person changes', async () => {
    const lines = ref(sample())
    const mode = ref<LineVisibility>('person')
    const person = ref<string | null>('ada')
    const page = ref('one')
    const state = useTeleprompterLines(lines, mode, person, page)
    const shown = () => state.included.value.flatMap((value, index) => (value ? [index] : []))
    expect(shown()).toEqual([1, 6, 8, 9])
    state.expand(state.passages.value[0]!, 'after', 1)
    expect(mode.value).toBe('custom')
    expect(state.isCustom.value).toBe(true)
    expect(state.customBase.value).toBe('person')
    expect(shown()).toEqual([1, 2, 6, 8, 9])
    // Another person changes highlights only: the Custom lines stay put.
    person.value = 'other-ada'
    await nextTick()
    expect(shown()).toEqual([1, 2, 6, 8, 9])
    state.reveal([4])
    expect(shown()).toEqual([1, 2, 4, 6, 8, 9])
    // Reset returns to the mode it came from, now for the current person.
    state.reset()
    expect(mode.value).toBe('person')
    expect(shown()).toEqual([3])
  })

  it('leaves Custom when a mode is chosen or the page changes', async () => {
    const mode = ref<LineVisibility>('annotated')
    const page = ref('one')
    const state = useTeleprompterLines(ref(sample()), mode, ref(null), page)
    state.reveal([0])
    expect(mode.value).toBe('custom')
    mode.value = 'person'
    await nextTick()
    expect(state.isCustom.value).toBe(false)
    expect(state.included.value.some(Boolean)).toBe(false)
    mode.value = 'annotated'
    state.reveal([0])
    page.value = 'two'
    await nextTick()
    expect(mode.value).toBe('annotated')
    expect(state.included.value[0]).toBe(false)
    // All shows everything already, so revealing never creates Custom there.
    mode.value = 'all'
    state.reveal([0])
    expect(mode.value).toBe('all')
  })

  it('builds page-scoped minimap bars with highlighted segments only on included lines', () => {
    const lines = sample()
    const included = modeLines(lines, 'person', 'ada')
    const bars = minimapLines(lines, included, ['verified'], 'ada')
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

  it('shows original line numbers and expands short gaps completely', async () => {
    const wrapper = render({
      lineVisibility: 'person',
      included: modeLines(sample(), 'person', 'ada'),
    })
    const numbers = wrapper
      .findAll('[data-line-index]:not([data-hidden]) small')
      .map((label) => label.text())
    expect(numbers).toEqual(['L2', 'L7', 'L9', 'L10'])
    // Hidden lines stay in the DOM, undisplayed, so selections can span them.
    const hidden = wrapper.findAll('[data-line-index][data-hidden]')
    expect(hidden.map((line) => line.attributes('data-line-index'))).toEqual([
      '0',
      '2',
      '3',
      '4',
      '5',
      '7',
    ])
    expect(hidden.every((line) => (line.element as HTMLElement).style.display === 'none')).toBe(
      true,
    )
    const gaps = wrapper.findAll('[data-gap-start]')
    expect(gaps.map((gap) => gap.get('small').text())).toEqual([
      '1 hidden line',
      '4 hidden lines',
      '1 hidden line',
    ])
    // Gaps no longer than one step have a single expand-all control.
    expect(
      gaps.map((gap) => gap.findAll('button').map((button) => button.attributes('aria-label'))),
    ).toEqual([
      ['Show all 1 hidden line, L1'],
      ['Show all 4 hidden lines, L3–L6'],
      ['Show all 1 hidden line, L8'],
    ])
    // Nothing is hidden after the final passage, so it has no trailing controls.
    expect(wrapper.find('[data-gap-start="10"]').exists()).toBe(false)
    for (const label of ['Show all 1 hidden line, L1', 'Show all 4 hidden lines, L3–L6']) {
      await wrapper.get(`[aria-label="${label}"]`).trigger('click')
    }
    expect(wrapper.emitted('expand')).toEqual([
      [{ start: 1, end: 1 }, 'before', 1],
      [{ start: 1, end: 1 }, 'after', 4],
    ])
  })

  it('expands long gaps a step below the passage above or above the passage below', async () => {
    const transcription = Array.from({ length: 20 }, (_, index) => ({
      id: `L${index + 1}`,
      text: `Line ${index + 1}`,
      position,
      entities: [],
    }))
    // Visible: L2 and L15. Hidden: L1, L3–L14 (12 lines) and L16–L20 (5 lines).
    const included = transcription.map((_, index) => index === 1 || index === 14)
    const wrapper = render({ transcription, included, selectedLineIndex: 1 })
    const gaps = wrapper.findAll('[data-gap-start]')
    expect(
      gaps.map((gap) => gap.findAll('button').map((button) => button.attributes('aria-label'))),
    ).toEqual([
      ['Show all 1 hidden line, L1'],
      ['Show 5 lines below L2', 'Show 5 lines above L15'],
      ['Show all 5 hidden lines, L16–L20'],
    ])
    expect(gaps[1]!.get('small').text()).toBe('12 hidden lines')
    // Each action is a full-width row with short visible text.
    expect(gaps[1]!.findAll('button').map((button) => button.find('span.truncate').text())).toEqual(
      ['5 lines below L2', '5 lines above L15'],
    )
    expect(gaps[0]!.get('button span.truncate').text()).toBe('Show all')
    expect(gaps[1]!.findAll('button').every((button) => button.classes('w-full'))).toBe(true)
    await wrapper.get('[aria-label="Show 5 lines below L2"]').trigger('click')
    await wrapper.get('[aria-label="Show 5 lines above L15"]').trigger('click')
    await wrapper.get('[aria-label="Show all 5 hidden lines, L16–L20"]').trigger('click')
    expect(wrapper.emitted('expand')).toEqual([
      [{ start: 1, end: 1 }, 'after', 5],
      [{ start: 14, end: 14 }, 'before', 5],
      [{ start: 14, end: 14 }, 'after', 5],
    ])
  })

  it.each([
    ['person', null, [], 'Select a person to see their lines.'],
    ['person', 'nobody', [], 'No lines for this person. Select another person or switch to All.'],
    [
      'person',
      'nobody',
      ['verified'],
      'No matching lines for this person. Change the annotation states or switch to All.',
    ],
    ['annotated', null, [], 'No annotated lines. Switch to All.'],
    [
      'annotated',
      null,
      ['unassigned'],
      'No lines with these annotations. Change the annotation states or switch to All.',
    ],
  ])('keeps %s mode empty with a short message', (mode, person, states, message) => {
    const transcription = sample().map((line) => ({ ...line, entities: [] }))
    const wrapper = render({
      transcription,
      relatedEntityId: person,
      lineVisibility: mode,
      annotationHighlight: states,
      included: modeLines(transcription, mode as LineMode, person, states as HighlightState[]),
      isTranslationOpen: true,
    })
    expect(wrapper.text()).toContain(message)
    expect(wrapper.find('[data-line-index]:not([data-hidden])').exists()).toBe(false)
    // Settings stay available, and no stale translation is shown.
    expect(wrapper.find('[aria-label="Teleprompter settings"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Translate teleprompter text"]').exists()).toBe(false)
  })

  it('highlights only the chosen states within the lines it is given', async () => {
    const included = modeLines(sample(), 'annotated', null)
    const wrapper = render({ lineVisibility: 'annotated', included })
    const lineCount = wrapper.findAll('[data-line-index]:not([data-hidden])').length
    expect(wrapper.findAll('mark')).toHaveLength(5)
    await wrapper.setProps({ annotationHighlight: ['verified'] })
    expect(wrapper.findAll('[data-line-index]:not([data-hidden])')).toHaveLength(lineCount)
    expect(wrapper.findAll('mark').map((mark) => mark.text())).toEqual(['Ada Novak'])
    expect(wrapper.text()).toContain('Ada Novak returned.')
    // Several states combine; All (none selected) highlights everything again.
    await wrapper.setProps({ annotationHighlight: ['verified', 'manual'] })
    expect(wrapper.findAll('mark').map((mark) => mark.text())).toEqual(['Ada Novak', 'Ada Novak'])
    await wrapper.setProps({ annotationHighlight: [] })
    expect(wrapper.findAll('mark')).toHaveLength(5)
  })

  it('selects one occurrence in the scan colors, even when a mention record repeats', async () => {
    // One mention record resolved twice (L1, and across L2–L3), as span resolution does.
    const occurrence = (line: string, start: number) => ({
      mention_id: 'm',
      occurrence: `m:${line}:${start}`,
    })
    const transcription: TranscriptionLine[] = [
      {
        id: 'L1',
        text: 'Ada Novak',
        position,
        entities: [mention('L1', 'ada', 'Ada Novak', 0, occurrence('L1', 0))],
      },
      {
        id: 'L2',
        text: 'Then Ada',
        position,
        entities: [mention('L2', 'ada', 'Ada', 5, occurrence('L2', 5))],
      },
      {
        id: 'L3',
        text: 'Novak left',
        position,
        entities: [
          mention('L3', 'ada', 'Novak', 0, { ...occurrence('L2', 5), firstFragment: false }),
        ],
      },
    ]
    expect(transcriptionEntityKey(transcription[0]!.entities![0]!)).toBe('m:L1:0')
    const wrapper = render({ transcription, selectedLineIndex: 0, relatedEntityId: 'ada' })
    const states = () => wrapper.findAll('mark').map((mark) => mark.attributes('data-selection'))
    expect(states()).toEqual(['mentioned', 'mentioned', 'mentioned'])
    expect(wrapper.findAll('mark')[0]!.classes()).toEqual(
      expect.arrayContaining(['bg-orange-500/15', 'outline-orange-500']),
    )
    await wrapper.setProps({ selectedEntityKey: 'm:L2:5' })
    // Only that occurrence, with both of its line fragments, is selected.
    expect(states()).toEqual(['mentioned', 'selectedMentioned', 'selectedMentioned'])
    await wrapper.setProps({ relatedEntityId: null })
    expect(states()).toEqual(['default', 'selected', 'selected'])
    expect(wrapper.findAll('mark')[1]!.classes()).toEqual(
      expect.arrayContaining(['bg-accent/20', 'outline-accent']),
    )
    // Unselected, unhighlighted mentions override the browser's yellow mark background.
    expect(wrapper.findAll('mark')[0]!.classes()).toContain('bg-transparent')
  })

  it('uses the scan toolbar link-state toggle group, plus Unassigned and All', async () => {
    const wrapper = render()
    const group = wrapper.get('[aria-label="Annotation state controls"]')
    expect(
      group
        .findAll('[aria-label="Annotation states"] button')
        .map((item) => item.attributes('aria-label')),
    ).toEqual(['Automatic', 'Manual', 'Verified', 'Unassigned'])
    const all = group.findAll('button').find((button) => button.text() === 'All')!
    expect(all.attributes('aria-pressed')).toBe('true')
    await group.get('[aria-label="Verified"]').trigger('click')
    await group.get('[aria-label="Unassigned"]').trigger('click')
    expect(wrapper.emitted('update:annotationHighlight')).toEqual([
      [['verified']],
      [['verified', 'unassigned']],
    ])
    await wrapper.setProps({ annotationHighlight: ['verified'] })
    expect(all.attributes('aria-pressed')).toBe('false')
    await all.trigger('click')
    const emitted = wrapper.emitted('update:annotationHighlight')!
    expect(emitted[emitted.length - 1]).toEqual([[]])
  })

  it('switches line visibility and shows Custom only while it is active', async () => {
    const wrapper = render()
    const lines = () =>
      wrapper.findAll('[aria-label="Lines"] button').map((button) => button.text())
    expect(lines()).toEqual(['All', 'Annotated', 'Person'])
    expect(wrapper.findAll('button').some((button) => button.text() === 'Reset')).toBe(false)
    await wrapper.get('[role="toolbar"] button[value="annotated"]').trigger('click')
    expect(wrapper.emitted('update:lineVisibility')).toEqual([['annotated']])
    await wrapper.setProps({ lineVisibility: 'custom' })
    expect(lines()).toEqual(['All', 'Annotated', 'Person', 'Custom'])
    // Every option has an icon and an accessible name; labels collapse to icons
    // when the settings row is narrow, except Custom, which stays labeled.
    const items = wrapper.findAll('[aria-label="Lines"] button')
    expect(items.map((item) => item.attributes('aria-label'))).toEqual([
      'All',
      'Annotated',
      'Person',
      'Custom',
    ])
    expect(items.every((item) => item.find('svg').exists())).toBe(true)
    expect(items.slice(0, 3).every((item) => item.get('span').classes('hidden'))).toBe(true)
    expect(items[3]!.find('span.hidden').exists()).toBe(false)
    expect(
      wrapper.get('[aria-label="Lines"] button[value="custom"]').attributes('data-state'),
    ).toBe('on')
    // Choosing a mode leaves Custom.
    await wrapper.get('[role="toolbar"] button[value="person"]').trigger('click')
    const emitted = wrapper.emitted('update:lineVisibility')!
    expect(emitted[emitted.length - 1]).toEqual(['person'])
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

  it('selects across a collapsed gap, tints it and copies its hidden lines in order', async () => {
    const wrapper = render({
      lineVisibility: 'person',
      included: modeLines(sample(), 'person', 'ada'),
    })
    // Visible: L2, L7, L9–L10. Select from the start of L2 to "Ada" in L7.
    const from = wrapper.get('[data-line-index="1"] [data-line-text]').element
    const to = wrapper.get('[data-line-index="6"] [data-line-text]').element
    const range = document.createRange()
    range.setStart(from, 0)
    range.setEnd(to.querySelector('mark')!.firstChild!, 3)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    document.dispatchEvent(new Event('selectionchange'))
    await new Promise((resolve) => requestAnimationFrame(resolve))
    await nextTick()
    // The native selection is kept, not pulled back to the gap.
    expect(selection.rangeCount).toBe(1)
    expect(selection.getRangeAt(0).endContainer).toBe(to.querySelector('mark')!.firstChild)
    expect(
      wrapper
        .findAll('[data-gap-start][data-selected]')
        .map((gap) => gap.attributes('data-gap-start')),
    ).toEqual(['2'])
    const data = new Map<string, string>()
    const event = new Event('copy', { bubbles: true, cancelable: true }) as ClipboardEvent
    Object.defineProperty(event, 'clipboardData', {
      value: { setData: (type: string, value: string) => data.set(type, value) },
    })
    wrapper.get('[aria-label="Transcription teleprompter"]').element.dispatchEvent(event)
    expect(data.get('text/plain')).toBe(
      [
        'Ada Novak signed it.',
        'Plain context line.',
        'Ada Novak of another family.',
        'More context.',
        'Even more context.',
        'Ada',
      ].join('\n'),
    )
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

  it('moves the cursor a non-overlapping page with Page Up/Down, or to the view edge', async () => {
    // Every displayed line is 20px tall; the viewport shows three lines (60px).
    const included = sample().map((_, index) => index !== 5)
    const wrapper = render({ included, selectedLineIndex: 0 })
    const scroller = wrapper.get('[aria-label="Transcription teleprompter"]').element as HTMLElement
    const lines = [
      ...scroller.querySelectorAll<HTMLElement>('[data-line-index]:not([data-hidden])'),
    ]
    lines.forEach((line, row) => {
      Object.defineProperty(line, 'offsetTop', { get: () => row * 20 })
      Object.defineProperty(line, 'offsetHeight', { get: () => 20 })
    })
    let scrollTop = 0
    Object.defineProperty(scroller, 'scrollTop', {
      get: () => scrollTop,
      set: (value: number) => (scrollTop = value),
    })
    Object.defineProperty(scroller, 'clientHeight', { get: () => 60 })
    Object.defineProperty(scroller, 'scrollHeight', { get: () => lines.length * 20 })
    // Let the initial reveal of the selected line settle first.
    await flushPromises()
    // Like the page, feed each new cursor back as the selected line.
    const press = async (key: string) => {
      await wrapper.get('[aria-label="Transcription teleprompter"]').trigger('keydown', { key })
      const emitted = wrapper.emitted('select-line')!
      const index = emitted[emitted.length - 1]![0] as number
      await wrapper.setProps({ selectedLineIndex: index })
      await flushPromises()
      return index
    }
    // L1–L3 in view: the next view starts at L4, which becomes the cursor.
    expect(await press('PageDown')).toBe(3)
    expect(scroller.scrollTop).toBe(60)
    // L4, L5, L7 in view (hidden L6 is skipped); the next view starts at L8.
    expect(await press('PageDown')).toBe(7)
    expect(scroller.scrollTop).toBe(120)
    // At the end the view cannot move: the cursor goes to its last line.
    expect(await press('PageDown')).toBe(9)
    expect(scroller.scrollTop).toBe(120)
    // The previous view ends just above L8: L4, L5, L7, with the cursor on L4.
    expect(await press('PageUp')).toBe(3)
    expect(scroller.scrollTop).toBe(60)
    // The previous view is L1–L3, with the cursor on L1.
    expect(await press('PageUp')).toBe(0)
    expect(scroller.scrollTop).toBe(0)
    // At the beginning the view cannot move: the cursor goes to its first line.
    await wrapper.setProps({ selectedLineIndex: 2 })
    expect(await press('PageUp')).toBe(0)
    expect(scroller.scrollTop).toBe(0)
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
  it('pages through tall wrapped lines in both directions without selection snapping', async () => {
    const wrapper = render({ selectedLineIndex: 0 })
    const scroller = wrapper.get('[aria-label="Transcription teleprompter"]').element as HTMLElement
    const lines = [...scroller.querySelectorAll<HTMLElement>('[data-line-index]')]
    // L2 is 200px high; all others are 20px. A 60px viewport starts with
    // L1 and the first 40px of L2. Selecting L2 must not reveal its far edge.
    lines.forEach((line, index) => {
      Object.defineProperty(line, 'offsetTop', { get: () => index < 2 ? index * 20 : 220 + (index - 2) * 20 })
      Object.defineProperty(line, 'offsetHeight', { get: () => index === 1 ? 200 : 20 })
    })
    Object.defineProperty(scroller, 'clientHeight', { get: () => 60 })
    Object.defineProperty(scroller, 'scrollHeight', { get: () => 380, configurable: true })
    await flushPromises()
    const press = async (key: string) => {
      await wrapper.get('[aria-label="Transcription teleprompter"]').trigger('keydown', { key })
      const emitted = wrapper.emitted('select-line')
      const index = emitted?.[emitted.length - 1]?.[0] as number | undefined
      if (index !== undefined) await wrapper.setProps({ selectedLineIndex: index })
      await flushPromises()
    }
    scroller.scrollTop = 0
    for (const expected of [60, 120, 180]) {
      await press('PageDown')
      expect(scroller.scrollTop).toBe(expected)
    }
    expect(wrapper.props('selectedLineIndex')).toBe(1)
    for (const expected of [120, 60, 0]) {
      await press('PageUp')
      expect(scroller.scrollTop).toBe(expected)
    }
    // The same behavior applies when the oversized line is the final line.
    await wrapper.setProps({ included: sample().map((_, index) => index < 2) })
    Object.defineProperty(scroller, 'scrollHeight', { get: () => 220, configurable: true })
    for (const expected of [60, 120, 160, 160]) {
      await press('PageDown')
      expect(scroller.scrollTop).toBe(expected)
    }
  })

})
