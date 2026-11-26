import type { HighlightState } from '@/viewmodels/teleprompter'
import { spanHighlightState } from '@/viewmodels/teleprompter'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'

/**
 * How a click or Enter/Space changes the scan's mention selection (#176):
 * plain replaces it, Ctrl/Cmd toggles one mention, Shift selects a range.
 */
export type MentionSelectMode = 'replace' | 'toggle' | 'range'

export function mentionSelectMode(event: {
  ctrlKey?: boolean
  metaKey?: boolean
  shiftKey?: boolean
}): MentionSelectMode {
  if (event.shiftKey) return 'range'
  if (event.ctrlKey || event.metaKey) return 'toggle'
  return 'replace'
}

/** Distinct mention IDs in transcription order: by line, then position. */
export function mentionOrder(lines: readonly TranscriptionLine[]) {
  const order: string[] = []
  const seen = new Set<string>()
  for (const line of lines)
    for (const span of [...(line.entities ?? [])].sort((a, b) => a.start_index - b.start_index))
      if (span.mention_id && !seen.has(span.mention_id)) {
        seen.add(span.mention_id)
        order.push(span.mention_id)
      }
  return order
}

export type MentionSelection = { ids: string[]; anchor: string | null }

/**
 * The next selection. Toggle moves the anchor to the clicked mention, even when
 * it removes it; a range selects every shown mention from the anchor to the
 * clicked one in text order, across lines, and keeps the anchor.
 */
export function nextMentionSelection(
  order: readonly string[],
  current: MentionSelection,
  clicked: string,
  mode: MentionSelectMode,
  /** Mentions shown in the text, in reading order; a range covers only these. */
  shown: readonly string[] = order,
): MentionSelection {
  const inOrder = (ids: Iterable<string>) => {
    const chosen = new Set(ids)
    return order.filter((id) => chosen.has(id))
  }
  if (mode === 'toggle') {
    const ids = new Set(current.ids)
    if (ids.has(clicked)) ids.delete(clicked)
    else ids.add(clicked)
    return { ids: inOrder(ids), anchor: clicked }
  }
  // An anchor no longer shown hands over to the first selected mention still shown.
  const anchor =
    current.anchor && shown.includes(current.anchor)
      ? current.anchor
      : (shown.find((id) => current.ids.includes(id)) ?? null)
  const from = anchor ? shown.indexOf(anchor) : -1
  const to = shown.indexOf(clicked)
  if (mode === 'range' && from >= 0 && to >= 0) {
    const [start, end] = from <= to ? [from, to] : [to, from]
    return { ids: inOrder(shown.slice(start, end + 1)), anchor }
  }
  return { ids: [clicked], anchor: clicked }
}

/** Keep only mentions that are still on the page, in transcription order. */
export function pruneMentionSelection(
  order: readonly string[],
  current: MentionSelection,
): MentionSelection {
  const present = new Set(order)
  const ids = current.ids.filter((id) => present.has(id))
  return {
    ids: order.filter((id) => ids.includes(id)),
    anchor: current.anchor && present.has(current.anchor) ? current.anchor : (ids[0] ?? null),
  }
}

export type SelectedMention = {
  id: string
  /** The mention's words on the page, joining a multiline occurrence. */
  text: string
  entityId: string | null
  state: HighlightState
  lineIndex: number
  span: TranscriptionEntitySpan
}

/** The selected mentions with their first occurrence on the page. */
export function selectedMentions(
  lines: readonly TranscriptionLine[],
  ids: readonly string[],
): SelectedMention[] {
  const wanted = new Set(ids)
  const found = new Map<string, SelectedMention>()
  lines.forEach((line, lineIndex) => {
    for (const span of line.entities ?? []) {
      const id = span.mention_id
      if (!id || !wanted.has(id)) continue
      const existing = found.get(id)
      if (!existing) {
        found.set(id, {
          id,
          text: span.text.trim(),
          entityId: span.entity_id ?? null,
          state: spanHighlightState(span),
          lineIndex,
          span,
        })
      } else if (span.occurrence === existing.span.occurrence && span !== existing.span) {
        existing.text = `${existing.text} ${span.text.trim()}`
      }
    }
  })
  return ids.flatMap((id) => found.get(id) ?? [])
}

// --- Unique mention contexts (#176) -----------------------------------------

/** Words as the API matches them: letters and digits joined by apostrophes or hyphens. */
const WORD = /[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu

type Word = { text: string; start: number; end: number }

function words(value: string): Word[] {
  return [...value.matchAll(WORD)].map((match) => ({
    text: match[0].normalize('NFKC').toLowerCase(),
    start: match.index,
    end: match.index + match[0].length,
  }))
}

type ContextLine = { text: string; regionId?: string }

function sameWords(left: readonly string[], right: readonly string[]) {
  return left.length === right.length && left.every((word, index) => word === right[index])
}

/**
 * The context for a mention selected from `startChar` on line `first` through
 * line `last`, or null when no context locates it exactly once.
 *
 * The API places a mention where its context equals exactly one line or run of
 * consecutive lines in one OCR region, at the first exact match of its name
 * there. Starting with the selected lines, neighbouring lines are added (fewest
 * first, earlier lines first) until the context occurs once on the page and
 * its first exact name match is the selected one. Identical surroundings, or a
 * name repeated before the selection in its own line, have no such context.
 */
export function uniqueMentionContext(
  lines: readonly ContextLine[],
  first: number,
  last: number,
  startChar: number,
  name: string,
): string | null {
  const region = lines[first]?.regionId
  if (lines.slice(first, last + 1).some((line) => line.regionId !== region)) return null
  const lineWords = lines.map((line) => words(line.text).map((word) => word.text))
  const nameWords = words(name).map((word) => word.text)
  if (!nameWords.length) return null
  const selectedInFirst = words(lines[first]!.text).findIndex((word) => word.end > startChar)
  if (selectedInFirst < 0) return null

  // How many places on the page equal these words, as the API looks for them.
  function locations(target: readonly string[]) {
    let count = 0
    for (let start = 0; start < lines.length; start += 1) {
      if (!lineWords[start]!.length) continue
      const collected: string[] = []
      for (let index = start; index < lines.length; index += 1) {
        if (lines[index]!.regionId !== lines[start]!.regionId) break
        collected.push(...lineWords[index]!)
        if (collected.length >= target.length) break
      }
      if (sameWords(collected, target)) count += 1
    }
    return count
  }

  for (let extra = 0; extra < lines.length; extra += 1) {
    for (let before = extra; before >= 0; before -= 1) {
      const start = first - before
      const end = last + extra - before
      if (start < 0 || end >= lines.length) continue
      if (lines.slice(start, end + 1).some((line) => line.regionId !== region)) continue
      const run = lineWords.slice(start, end + 1).flat()
      if (locations(run) !== 1) continue
      const selected =
        lineWords.slice(start, first).reduce((sum, line) => sum + line.length, 0) + selectedInFirst
      const firstMatch = run.findIndex((_word, index) =>
        sameWords(run.slice(index, index + nameWords.length), nameWords),
      )
      if (firstMatch !== selected) continue
      return lines
        .slice(start, end + 1)
        .map((line) => line.text)
        .join('\n')
    }
  }
  return null
}
