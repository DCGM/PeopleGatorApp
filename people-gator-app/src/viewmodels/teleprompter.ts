import { computed, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import type { TranscriptionEntitySpan, TranscriptionLine } from './document-workspace.types'

/** Which original lines the teleprompter shows (issue #36). */
export type LineVisibility = 'all' | 'annotated' | 'person'
export const LINE_VISIBILITIES: readonly LineVisibility[] = ['all', 'annotated', 'person']
export const lineVisibilityLabels: Record<LineVisibility, string> = {
  all: 'All',
  annotated: 'Annotated',
  person: 'Person',
}

/** Which annotations are highlighted; never changes which lines are shown. */
export type AnnotationHighlight = 'all' | 'automatic' | 'manual' | 'verified' | 'unassigned'
export const ANNOTATION_HIGHLIGHTS: readonly AnnotationHighlight[] = [
  'all',
  'automatic',
  'manual',
  'verified',
  'unassigned',
]
export const annotationHighlightLabels: Record<AnnotationHighlight, string> = {
  all: 'All',
  automatic: 'Automatic',
  manual: 'Manual',
  verified: 'Verified',
  unassigned: 'Unassigned',
}

/** Lines revealed per expand action; shorter gaps expand completely in one action. */
export const EXPAND_STEP = 5

export function parseLineVisibility(value: unknown): LineVisibility {
  return LINE_VISIBILITIES.includes(value as LineVisibility) ? (value as LineVisibility) : 'all'
}

export function parseAnnotationHighlight(value: unknown): AnnotationHighlight {
  return ANNOTATION_HIGHLIGHTS.includes(value as AnnotationHighlight)
    ? (value as AnnotationHighlight)
    : 'all'
}

export function highlightsSpan(span: TranscriptionEntitySpan, highlight: AnnotationHighlight) {
  if (highlight === 'all') return true
  if (highlight === 'unassigned') return !span.entity_id
  return Boolean(span.entity_id) && span.linkState === highlight
}

/**
 * Lines allowed by the visibility mode alone. Person mode matches linked
 * identity IDs, so every fragment of a multiline mention qualifies, and stays
 * empty without a selected person rather than falling back to full text.
 */
export function modeLines(
  lines: readonly TranscriptionLine[],
  mode: LineVisibility,
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

export type MinimapSegment = { start: number; width: number; key: string; related: boolean }
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
  highlight: AnnotationHighlight,
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
        })),
    }
  })
}

/**
 * Teleprompter line state: the mode's lines plus manually revealed context.
 * A new page, person or mode starts fresh, without previous expansions.
 */
export function useTeleprompterLines(
  transcription: MaybeRefOrGetter<readonly TranscriptionLine[]>,
  mode: MaybeRefOrGetter<LineVisibility>,
  personId: MaybeRefOrGetter<string | null>,
  pageKey: MaybeRefOrGetter<string>,
) {
  const revealed = shallowRef<ReadonlySet<number>>(new Set())
  const base = computed(() => modeLines(toValue(transcription), toValue(mode), toValue(personId)))
  const included = computed(() => includedLines(base.value, revealed.value))
  const visiblePassages = computed(() => passages(included.value))
  const hasExpansions = computed(() => [...revealed.value].some((index) => !base.value[index]))

  function reveal(indices: readonly number[]) {
    if (!indices.length) return
    revealed.value = new Set([...revealed.value, ...indices])
  }
  function expand(passage: Passage, direction: 'before' | 'after', count: number) {
    reveal(contextIndices(passage, direction, count, toValue(transcription).length))
  }
  function reset() {
    revealed.value = new Set()
  }
  watch(() => [toValue(pageKey), toValue(personId), toValue(mode)], reset, { flush: 'sync' })

  return { base, included, passages: visiblePassages, hasExpansions, expand, reveal, reset }
}
