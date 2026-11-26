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
 * it removes it; a range spans the anchor and the clicked mention inclusively,
 * including mentions on the lines in between, and keeps the anchor.
 */
export function nextMentionSelection(
  order: readonly string[],
  current: MentionSelection,
  clicked: string,
  mode: MentionSelectMode,
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
  const from = current.anchor ? order.indexOf(current.anchor) : -1
  const to = order.indexOf(clicked)
  if (mode === 'range' && from >= 0 && to >= 0) {
    const [start, end] = from <= to ? [from, to] : [to, from]
    return { ids: order.slice(start, end + 1), anchor: current.anchor }
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
