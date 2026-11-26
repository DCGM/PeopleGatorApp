import { describe, expect, it } from 'vitest'

import type { TranscriptionLine } from '@/viewmodels/document-workspace.types'
import {
  mentionOrder,
  mentionSelectMode,
  nextMentionSelection,
  pruneMentionSelection,
  selectedMentions,
  uniqueMentionContext,
} from '@/viewmodels/mention-selection'

const box = { left: 0, top: 0, width: 1, height: 1 }
const span = (mention_id: string, line_id: string, start: number, text: string, extra = {}) => ({
  mention_id,
  occurrence: `${mention_id}:${line_id}:${start}`,
  line_id,
  label: 'person' as const,
  text,
  start_index: start,
  end_index: start + text.length,
  linkState: null,
  verifiedBy: null,
  verifiedAt: null,
  ...extra,
})
// Spans out of position order on L1 and a name split over L3–L4.
const lines: TranscriptionLine[] = [
  {
    id: 'l1',
    text: 'Eva met Jan',
    position: box,
    entities: [
      span('jan', 'l1', 8, 'Jan', { entity_id: 'p-jan', linkState: 'verified' }),
      span('eva', 'l1', 0, 'Eva'),
    ],
  },
  { id: 'l2', text: 'nothing', position: box, entities: [] },
  {
    id: 'l3',
    text: 'later Ada',
    position: box,
    entities: [span('ada', 'l3', 6, 'Ada', { entity_id: 'p-ada', linkState: 'automatic' })],
  },
  {
    id: 'l4',
    text: 'Novak left',
    position: box,
    entities: [
      {
        ...span('ada', 'l4', 0, 'Novak', { entity_id: 'p-ada', linkState: 'automatic' }),
        occurrence: 'ada:l3:6',
      },
    ],
  },
]

describe('scan mention selection (#176)', () => {
  it('reads plain, Ctrl/Cmd and Shift activations', () => {
    expect(mentionSelectMode({})).toBe('replace')
    expect(mentionSelectMode({ ctrlKey: true })).toBe('toggle')
    expect(mentionSelectMode({ metaKey: true })).toBe('toggle')
    expect(mentionSelectMode({ shiftKey: true, ctrlKey: true })).toBe('range')
  })

  it('orders mentions by line, then position', () => {
    expect(mentionOrder(lines)).toEqual(['eva', 'jan', 'ada'])
  })

  it('replaces, toggles with a moving anchor, and selects ranges across lines', () => {
    const order = mentionOrder(lines)
    let selection = nextMentionSelection(order, { ids: [], anchor: null }, 'jan', 'replace')
    expect(selection).toEqual({ ids: ['jan'], anchor: 'jan' })
    // Toggle adds, keeps transcription order and moves the anchor.
    selection = nextMentionSelection(order, selection, 'eva', 'toggle')
    expect(selection).toEqual({ ids: ['eva', 'jan'], anchor: 'eva' })
    // Shift from the anchor over the empty line L2 to L3.
    selection = nextMentionSelection(order, selection, 'ada', 'range')
    expect(selection).toEqual({ ids: ['eva', 'jan', 'ada'], anchor: 'eva' })
    // A range backwards from a later anchor.
    selection = nextMentionSelection(order, { ids: ['ada'], anchor: 'ada' }, 'jan', 'range')
    expect(selection).toEqual({ ids: ['jan', 'ada'], anchor: 'ada' })
    // Toggling off still moves the anchor to the clicked mention.
    selection = nextMentionSelection(order, selection, 'ada', 'toggle')
    expect(selection).toEqual({ ids: ['jan'], anchor: 'ada' })
    // Shift without an anchor acts as a plain click.
    expect(nextMentionSelection(order, { ids: [], anchor: null }, 'eva', 'range')).toEqual({
      ids: ['eva'],
      anchor: 'eva',
    })
    expect(nextMentionSelection(order, selection, 'eva', 'replace')).toEqual({
      ids: ['eva'],
      anchor: 'eva',
    })
  })

  it('ranges over the shown mentions only, keeping hidden selected ones on toggle', () => {
    const order = ['eva', 'jan', 'ada', 'zoe']
    // "jan" is on a hidden line or filtered out of the text.
    const shown = ['eva', 'ada', 'zoe']
    const anchored = { ids: ['eva'], anchor: 'eva' }
    expect(nextMentionSelection(order, anchored, 'zoe', 'range', shown)).toEqual({
      ids: ['eva', 'ada', 'zoe'],
      anchor: 'eva',
    })
    const withHidden = { ids: ['jan', 'eva'], anchor: 'eva' }
    expect(nextMentionSelection(order, withHidden, 'ada', 'toggle', shown).ids).toEqual([
      'eva',
      'jan',
      'ada',
    ])
    // An anchor no longer shown hands over to the first selected mention still shown.
    expect(
      nextMentionSelection(order, { ids: ['jan', 'eva'], anchor: 'jan' }, 'zoe', 'range', shown),
    ).toEqual({ ids: ['eva', 'ada', 'zoe'], anchor: 'eva' })
    // With no selected mention shown, Shift starts a new selection.
    expect(
      nextMentionSelection(order, { ids: ['jan'], anchor: 'jan' }, 'zoe', 'range', shown),
    ).toEqual({
      ids: ['zoe'],
      anchor: 'zoe',
    })
  })

  it('drops deleted mentions and moves a missing anchor to the first one kept', () => {
    expect(
      pruneMentionSelection(['eva', 'ada'], { ids: ['jan', 'ada', 'eva'], anchor: 'jan' }),
    ).toEqual({
      ids: ['eva', 'ada'],
      anchor: 'ada',
    })
  })

  it('describes selected mentions with their text, person and state', () => {
    expect(
      selectedMentions(lines, ['ada', 'eva']).map(({ id, text, entityId, state, lineIndex }) => ({
        id,
        text,
        entityId,
        state,
        lineIndex,
      })),
    ).toEqual([
      { id: 'ada', text: 'Ada Novak', entityId: 'p-ada', state: 'automatic', lineIndex: 2 },
      { id: 'eva', text: 'Eva', entityId: null, state: 'unassigned', lineIndex: 0 },
    ])
  })
})

describe('unique mention contexts (#176)', () => {
  const page = (...texts: string[]) => texts.map((text) => ({ text, regionId: 'r' }))

  it('uses the selected line when it is unique on the page', () => {
    const lines = page('Jan wrote.', 'Eva read.')
    expect(uniqueMentionContext(lines, 0, 0, 0, 'Jan')).toBe('Jan wrote.')
  })

  it('adds neighbouring lines until an identical line becomes unique', () => {
    const lines = page('Opening.', 'Jan wrote.', 'Middle.', 'Jan wrote.', 'Closing.')
    // Earlier neighbours first; the second copy needs the line before it too.
    expect(uniqueMentionContext(lines, 1, 1, 0, 'Jan')).toBe('Opening.\nJan wrote.')
    expect(uniqueMentionContext(lines, 3, 3, 0, 'Jan')).toBe('Middle.\nJan wrote.')
    // Matching ignores case and punctuation, as the API does: the lines are equal,
    // so the first needs both, and the second has no context of its own.
    const loose = page('JAN wrote', 'jan, wrote!')
    expect(uniqueMentionContext(loose, 0, 0, 0, 'Jan')).toBe('JAN wrote\njan, wrote!')
    expect(uniqueMentionContext(loose, 1, 1, 0, 'jan')).toBeNull()
  })

  it('skips a neighbour that holds the name before the selection', () => {
    const lines = page('Jan arrived.', 'Jan wrote.', 'End.', 'Jan wrote.')
    // "Jan arrived. Jan wrote." would resolve to the first Jan; the next line is used instead.
    expect(uniqueMentionContext(lines, 1, 1, 0, 'Jan')).toBe('Jan wrote.\nEnd.')
  })

  it('offers no context for identical surroundings or a repeated name before the selection', () => {
    expect(uniqueMentionContext(page('Jan wrote.', 'Jan wrote.'), 1, 1, 0, 'Jan')).toBeNull()
    const repeated = page('Jan met Jan.')
    expect(uniqueMentionContext(repeated, 0, 0, 0, 'Jan')).toBe('Jan met Jan.')
    expect(uniqueMentionContext(repeated, 0, 0, 8, 'Jan')).toBeNull()
  })

  it('keeps contexts inside one OCR region', () => {
    const lines = [
      { text: 'Head.', regionId: 'a' },
      { text: 'Jan wrote.', regionId: 'b' },
      { text: 'Jan wrote.', regionId: 'c' },
    ]
    // The only neighbours are in other regions, so neither copy can be told apart.
    expect(uniqueMentionContext(lines, 1, 1, 0, 'Jan')).toBeNull()
    // A selection across regions is never offered.
    expect(uniqueMentionContext(lines, 0, 1, 0, 'Head Jan')).toBeNull()
  })

  it('covers a two-line selection', () => {
    const lines = page('Written by Ada', 'Novak today.', 'Ada Novak again.')
    expect(uniqueMentionContext(lines, 0, 1, 11, 'Ada Novak')).toBe('Written by Ada\nNovak today.')
  })
})
