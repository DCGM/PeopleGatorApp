import { describe, expect, it } from 'vitest'

import type { TranscriptionLine } from '@/viewmodels/document-workspace.types'
import {
  mentionOrder,
  mentionSelectMode,
  nextMentionSelection,
  pruneMentionSelection,
  selectedMentions,
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
