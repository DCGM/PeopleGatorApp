import { computed, ref, shallowRef, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'

import type { EntityLinkState } from '@/client'
import type { TranscriptionEntitySpan, TranscriptionLine } from './document-workspace.types'

/**
 * Which original lines the teleprompter shows (issue #36). Revealing lines
 * outside the Annotated or Person window switches to Custom, an explicit line
 * set that no longer follows the selected person.
 */
export type LineVisibility = 'all' | 'annotated' | 'person' | 'custom'
export type LineMode = Exclude<LineVisibility, 'custom'>
/** The modes a reader chooses directly; Custom only results from revealing lines. */
export const LINE_VISIBILITIES: readonly LineMode[] = ['all', 'annotated', 'person']
export const lineVisibilityLabels: Record<LineVisibility, string> = {
  all: 'All',
  annotated: 'Annotated',
  person: 'Person',
  custom: 'Custom',
}

/**
 * Annotation states to highlight; an empty list highlights every annotation.
 * Highlighting never changes which lines are shown.
 */
export type HighlightState = EntityLinkState | 'unassigned'
export const HIGHLIGHT_STATES: readonly HighlightState[] = [
  'automatic',
  'manual',
  'verified',
  'unassigned',
]

/** Lines revealed per expand action; shorter gaps expand completely in one action. */
export const EXPAND_STEP = 5

export function parseLineVisibility(value: unknown): LineMode {
  return LINE_VISIBILITIES.includes(value as LineMode) ? (value as LineMode) : 'all'
}

export function parseHighlightStates(value: unknown): HighlightState[] {
  const values = Array.isArray(value) ? value : [value]
  return HIGHLIGHT_STATES.filter((state) => values.includes(state))
}

/** An unlinked span, or a link without a recorded state, counts as unassigned. */
export function spanHighlightState(span: TranscriptionEntitySpan): HighlightState {
  return span.entity_id ? (span.linkState ?? 'unassigned') : 'unassigned'
}

export function highlightsSpan(span: TranscriptionEntitySpan, states: readonly HighlightState[]) {
  return !states.length || states.includes(spanHighlightState(span))
}

/**
 * Lines allowed by the visibility mode alone. Person mode matches linked
 * identity IDs, so every fragment of a multiline mention qualifies, and stays
 * empty without a selected person rather than falling back to full text.
 */
export function modeLines(
  lines: readonly TranscriptionLine[],
  mode: LineMode,
  personId: string | null,
): boolean[] {
  if (mode === 'all') return lines.map(() => true)
  if (mode === 'annotated') return lines.map((line) => Boolean(line.entities?.length))
  if (!personId) return lines.map(() => false)
  return lines.map((line) => line.entities?.some((span) => span.entity_id === personId) ?? false)
}

/** Mode lines plus manually revealed context, in original order. */
export function includedLines(base: readonly boolean[], revealed: ReadonlySet<number>) {
  return base.map((included, index) => included || revealed.has(index))
}

export type Passage = { start: number; end: number }

/** Maximal runs of included lines; `end` is inclusive. */
export function passages(included: readonly boolean[]): Passage[] {
  const result: Passage[] = []
  let start = -1
  included.forEach((value, index) => {
    if (value && start < 0) start = index
    if (!value && start >= 0) {
      result.push({ start, end: index - 1 })
      start = -1
    }
  })
  if (start >= 0) result.push({ start, end: included.length - 1 })
  return result
}

/** Original indices revealed by expanding a passage; overlaps merge naturally. */
export function contextIndices(
  passage: Passage,
  direction: 'before' | 'after',
  count: number,
  lineCount: number,
) {
  const indices: number[] = []
  if (direction === 'before') {
    for (let index = Math.max(0, passage.start - count); index < passage.start; index += 1)
      indices.push(index)
  } else {
    for (
      let index = passage.end + 1;
      index <= Math.min(lineCount - 1, passage.end + count);
      index += 1
    )
      indices.push(index)
  }
  return indices
}

/**
 * The included line closest to `index`. Equally near lines resolve to the
 * preceding one, keeping the reader's place earlier in the reading order.
 */
export function nearestIncluded(included: readonly boolean[], index: number): number | null {
  if (included[index]) return index
  for (let distance = 1; distance < included.length; distance += 1) {
    if (included[index - distance]) return index - distance
    if (included[index + distance]) return index + distance
  }
  return null
}

/** The next or previous included line, or null at the boundary. */
export function adjacentIncluded(
  included: readonly boolean[],
  index: number,
  direction: 'next' | 'previous',
): number | null {
  const step = direction === 'next' ? 1 : -1
  for (
    let candidate = index + step;
    candidate >= 0 && candidate < included.length;
    candidate += step
  )
    if (included[candidate]) return candidate
  return null
}

export type MinimapSegment = {
  start: number
  width: number
  key: string
  related: boolean
  state: HighlightState
}
export type MinimapLine = {
  index: number
  width: number
  included: boolean
  segments: MinimapSegment[]
}

/**
 * Page-scoped minimap bars: widths follow text length relative to the longest
 * line; colored segments approximate highlighted annotations' positions.
 */
export function minimapLines(
  lines: readonly TranscriptionLine[],
  included: readonly boolean[],
  highlight: readonly HighlightState[],
  relatedEntityId: string | null,
): MinimapLine[] {
  const longest = Math.max(1, ...lines.map((line) => line.text.length))
  return lines.map((line, index) => {
    const length = Math.max(1, line.text.length)
    const width = length / longest
    return {
      index,
      width,
      included: included[index] ?? false,
      segments: (line.entities ?? [])
        .filter((span) => highlightsSpan(span, highlight))
        .map((span) => ({
          key: `${span.mention_id ?? span.entity_id ?? ''}:${span.start_index}`,
          start: (span.start_index / length) * width,
          width: (Math.max(1, span.end_index - span.start_index) / length) * width,
          related: Boolean(span.entity_id && span.entity_id === relatedEntityId),
          state: spanHighlightState(span),
        })),
    }
  })
}

/**
 * Teleprompter line state. Revealing lines outside the Annotated or Person
 * window switches to Custom, keeping exactly the lines shown; a Custom view no
 * longer follows the selected person, so changing person never collapses or
 * jumps the text. Choosing a mode discards it; a new page returns to the mode
 * it came from.
 */
export function useTeleprompterLines(
  transcription: MaybeRefOrGetter<readonly TranscriptionLine[]>,
  mode: Ref<LineVisibility>,
  personId: MaybeRefOrGetter<string | null>,
  pageKey: MaybeRefOrGetter<string>,
) {
  const custom = shallowRef<ReadonlySet<number> | null>(null)
  /** The mode a Custom view was created from, restored by reset and in the URL. */
  const customBase = ref<LineMode>('annotated')
  const included = computed(() => {
    const lines = toValue(transcription)
    if (mode.value !== 'custom') return modeLines(lines, mode.value, toValue(personId))
    const selected = custom.value ?? new Set<number>()
    return lines.map((_, index) => selected.has(index))
  })
  const visiblePassages = computed(() => passages(included.value))
  const isCustom = computed(() => mode.value === 'custom')

  function reveal(indices: readonly number[]) {
    if (!indices.length || mode.value === 'all') return
    const next = new Set(indices)
    included.value.forEach((value, index) => value && next.add(index))
    if (mode.value !== 'custom') customBase.value = mode.value
    custom.value = next
    mode.value = 'custom'
  }
  function expand(passage: Passage, direction: 'before' | 'after', count: number) {
    reveal(contextIndices(passage, direction, count, toValue(transcription).length))
  }
  function reset() {
    if (mode.value === 'custom') mode.value = customBase.value
  }
  watch(
    mode,
    (value) => {
      if (value !== 'custom') custom.value = null
    },
    { flush: 'sync' },
  )
  // Custom line sets are page-specific.
  watch(() => toValue(pageKey), reset, { flush: 'sync' })

  return { included, passages: visiblePassages, isCustom, customBase, expand, reveal, reset }
}
