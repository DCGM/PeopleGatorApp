<script setup lang="ts">
import PanelBar from './PanelBar.vue'
import AnnotationStateToggles from './AnnotationStateToggles.vue'
import TeleprompterMinimap from './TeleprompterMinimap.vue'
import { linkTooltip, mentionStateClasses } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cardInUse, movedIntoNestedLayer, useHoverCard } from '@/composables/hover-card'
import {
  AlignJustify,
  ArrowDownFromLine,
  ArrowUpFromLine,
  Highlighter,
  ListPlus,
  TextCursor,
  UnfoldVertical,
  UserRound,
  X,
} from '@lucide/vue'

import type { Language } from '@/client/types.gen'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import {
  mentionSelectMode,
  uniqueMentionContext,
  type MentionSelectMode,
} from '@/viewmodels/mention-selection'
import {
  EXPAND_STEP,
  LINE_VISIBILITIES,
  highlightsSpan,
  lineVisibilityLabels,
  minimapLines,
  passages as toPassages,
  spanHighlightState,
  type HighlightState,
  type LineMode,
  type LineVisibility,
  type Passage,
} from '@/viewmodels/teleprompter'

type TranscriptionSegment = {
  text: string
  entity?: TranscriptionEntitySpan
}

type Gap = { start: number; end: number; before?: Passage; after?: Passage }
type GapAction = {
  icon: typeof UnfoldVertical
  /** Short visible text; the accessible label repeats it with context. */
  text: string
  label: string
  passage: Passage
  direction: 'before' | 'after'
  count: number
}

const props = withDefaults(
  defineProps<{
    transcription: TranscriptionLine[]
    selectedLineIndex: number
    selectedEntityKey: string | null
    relatedEntityId: string | null
    /** Linked identity names, shown when hovering or focusing a mention. */
    entityNames?: ReadonlyMap<string, string>
    /** Original lines currently available in the text; defaults to all. */
    included?: boolean[]
    isTranslationOpen?: boolean
    selectedLanguage?: Language
    currentTranslation?: string
    translationLoading?: boolean
    /** Name mentions selected for the person card, by mention ID (#176). */
    selectedMentionIds?: readonly string[]
    /** Offer Create mention for selected plain text. */
    canCreateMention?: boolean
    /** Offer Change mention for selected text that overlaps a mention. */
    canChangeMention?: boolean
    /** Offer Merge mentions for selected text that overlaps several (it deletes all but one). */
    canMergeMentions?: boolean
  }>(),
  { included: undefined, selectedMentionIds: () => [] },
)

const lineVisibility = defineModel<LineVisibility>('lineVisibility', { default: 'all' })
const annotationHighlight = defineModel<HighlightState[]>('annotationHighlight', {
  default: () => [],
})

const emit = defineEmits<{
  'select-line': [index: number]
  'select-entity': [
    index: number,
    entity: TranscriptionEntitySpan,
    mode: MentionSelectMode,
    /** Mention IDs as shown in the text, in reading order, for Shift ranges. */
    shown: string[],
  ]
  'clear-mentions': []
  /** The mention whose card is shown on hover or focus, without selecting it (#203). */
  'preview-mention': [mentionId: string | null]
  'create-mention': [mention: { lineIndex: number; name: string; context: string }]
  'change-mention': [mention: { mentionId: string; name: string; context: string }]
  /** Several overlapped mentions become one covering the selected words. */
  'merge-mentions': [mention: { mentionIds: string[]; name: string; context: string }]
  expand: [passage: Passage, direction: 'before' | 'after', count: number]
}>()

// Like the highlight toggles: icon and label when the settings row is wide, icon only otherwise.
const lineVisibilityIcons = {
  all: AlignJustify,
  annotated: Highlighter,
  person: UserRound,
  custom: ListPlus,
} satisfies Record<LineVisibility, typeof AlignJustify>

const hoveredEntityKey = ref<string | null>(null)
const bodyElement = ref<HTMLElement | null>(null)
/** The mention whose person card is shown on hover or focus, before any selection (#203). */
const hoverCard = useHoverCard<{
  entity: TranscriptionEntitySpan
  index: number
  element: HTMLElement
}>()

function mentionName(entity: TranscriptionEntitySpan) {
  if (!entity.entity_id) return undefined
  return props.entityNames?.get(entity.entity_id) ?? 'Unknown person'
}

function mentionClasses(entity: TranscriptionEntitySpan) {
  return [
    // A text underline spans the letters only, unaffected by the padding below.
    'underline decoration-2 underline-offset-1',
    // Room for the text inside the selection lines. The negative margin cancels
    // the side padding, so a tag is exactly as wide as the plain text: nothing
    // shifts on select/unselect or when a filter turns text into a tag.
    '-mx-0.5 px-0.5',
    mentionStateClasses[spanHighlightState(entity)],
    mentionSelectionClasses[mentionSelectionState(entity)],
  ]
}

function mentionLabel(entity: TranscriptionEntitySpan) {
  const name = mentionName(entity)
  return `${entityText(entity)}: ${name ? `${name}, ` : ''}${linkTooltip(entity)}`
}

/** Focus from a press is followed by its click; only keyboard focus opens the card. */
function keyboardFocused(element: HTMLElement) {
  try {
    return element.matches(':focus-visible')
  } catch {
    return true
  }
}

function showMentionCard(event: Event, index: number, entity: TranscriptionEntitySpan) {
  hoveredEntityKey.value = entityKey(entity)
  const element = event.currentTarget as HTMLElement | null
  // A selected mention already shows its card.
  if (!element || !entity.mention_id || isSelectedMention(entity)) return hoverCard.close()
  if (event instanceof MouseEvent) {
    // Not while dragging a text selection or adding mentions with a modifier.
    if (event.buttons || event.shiftKey || event.ctrlKey || event.metaKey) return
  } else if (!keyboardFocused(element)) return
  if (cardInUse(mentionCardElement())) return
  hoverCard.open({ entity, index, element }, !(event instanceof MouseEvent))
}

function hideMentionCard() {
  hoveredEntityKey.value = null
  hoverCard.close()
}
const scrollElement = ref<HTMLElement | null>(null)
const translationElement = ref<HTMLElement | null>(null)
const isTranslationExpanded = ref(false)
const viewport = ref<{ first: number; last: number } | null>(null)

const includedLines = computed(() => props.included ?? props.transcription.map(() => true))
const visiblePassages = computed(() => toPassages(includedLines.value))
const lineCount = computed(() => props.transcription.length)

/** Passages in reading order with the collapsed gaps around them. */
const blocks = computed(() => {
  const items: Array<
    { kind: 'passage'; passage: Passage; key: string } | { kind: 'gap'; gap: Gap; key: string }
  > = []
  let cursor = 0
  let previous: Passage | undefined
  for (const passage of visiblePassages.value) {
    if (passage.start > cursor)
      items.push({
        kind: 'gap',
        gap: { start: cursor, end: passage.start - 1, before: previous, after: passage },
        key: `gap-${cursor}`,
      })
    items.push({ kind: 'passage', passage, key: `passage-${passage.start}` })
    cursor = passage.end + 1
    previous = passage
  }
  if (previous && cursor < lineCount.value)
    items.push({
      kind: 'gap',
      gap: { start: cursor, end: lineCount.value - 1, before: previous },
      key: `gap-${cursor}`,
    })
  return items
})

/** Each collapsed gap by its first hidden line; the band renders just before it. */
const gapsByStart = computed(
  () =>
    new Map(
      blocks.value.flatMap((block) => (block.kind === 'gap' ? [[block.gap.start, block.gap]] : [])),
    ),
)

function lineCountText(count: number) {
  return `${count} hidden ${count === 1 ? 'line' : 'lines'}`
}

/**
 * GitHub-style gap expansion: reveal lines below the passage above and above
 * the passage below, or the whole gap at once when it is no longer than a step.
 */
function gapActions(gap: Gap): GapAction[] {
  const size = gap.end - gap.start + 1
  if (size <= EXPAND_STEP) {
    const range = size === 1 ? `L${gap.start + 1}` : `L${gap.start + 1}–L${gap.end + 1}`
    return [
      {
        icon: UnfoldVertical,
        text: 'Show all',
        label: `Show all ${lineCountText(size)}, ${range}`,
        passage: (gap.before ?? gap.after)!,
        direction: gap.before ? 'after' : 'before',
        count: size,
      },
    ]
  }
  return [
    ...(gap.before
      ? [{
          icon: ArrowDownFromLine,
          text: `${EXPAND_STEP} lines below L${gap.before.end + 1}`,
          label: `Show ${EXPAND_STEP} lines below L${gap.before.end + 1}`,
          passage: gap.before,
          direction: 'after' as const,
          count: EXPAND_STEP,
        }]
      : []),
    ...(gap.after
      ? [{
          icon: ArrowUpFromLine,
          text: `${EXPAND_STEP} lines above L${gap.after.start + 1}`,
          label: `Show ${EXPAND_STEP} lines above L${gap.after.start + 1}`,
          passage: gap.after,
          direction: 'before' as const,
          count: EXPAND_STEP,
        }]
      : []),
  ]
}

const emptyMessage = computed(() => {
  if (visiblePassages.value.length) return ''
  if (!lineCount.value) return 'No transcription.'
  const filtered = annotationHighlight.value.length > 0
  if (lineVisibility.value === 'person') {
    if (!props.relatedEntityId) return 'Select a person to see their lines.'
    return filtered
      ? 'No matching lines for this person. Change the annotation states or switch to All.'
      : 'No lines for this person. Select another person or switch to All.'
  }
  if (lineVisibility.value === 'annotated')
    return filtered
      ? 'No lines with these annotations. Change the annotation states or switch to All.'
      : 'No annotated lines. Switch to All.'
  return 'No transcription.'
})

/**
 * The selected person's other mentions are outlined, except while mentions are
 * selected for editing: then only the selected mentions are marked, so the
 * selection is never mistaken for every mention of that person (#176).
 */
const highlightedPersonId = computed(() =>
  props.selectedMentionIds.length ? null : props.relatedEntityId,
)

const minimap = computed(() =>
  minimapLines(
    props.transcription,
    includedLines.value,
    annotationHighlight.value,
    highlightedPersonId.value,
  ),
)

function entityKey(entity: TranscriptionEntitySpan) {
  return transcriptionEntityKey(entity)
}

// Joined once per transcription instead of scanning every line for each mark.
const entityTexts = computed(() => {
  const texts = new Map<string, string[]>()
  for (const line of props.transcription)
    for (const fragment of line.entities ?? []) {
      if (!fragment.entity_id) continue
      const key = entityKey(fragment)
      texts.set(key, [...(texts.get(key) ?? []), fragment.text.trim()])
    }
  return texts
})

function entityText(entity: TranscriptionEntitySpan) {
  if (!entity.entity_id) return entity.text
  return entityTexts.value.get(entityKey(entity))?.join(' ') ?? entity.text
}

/**
 * The scan overlay's selection scheme: the selected mention is blue, mentions
 * of the selected person are orange, and a mention that is both has the
 * selected blue fill and blue inner line inside an orange outer line. Outlines
 * and inset rings leave the text layout and the link-state underline unchanged.
 */
const mentionSelectionClasses = {
  selected: 'bg-accent/20 outline-1 outline-accent',
  selectedMentioned: 'bg-accent/20 inset-ring-1 inset-ring-accent outline-1 outline-orange-500',
  mentioned: 'bg-orange-500/15 outline-1 outline-orange-500 hover:bg-orange-500/30',
  hovered: 'bg-accent/10 outline-1 outline-accent/70',
  // Transparent overrides the browser's yellow default for mark elements.
  default: 'bg-transparent hover:bg-accent/10',
} as const

const selectedMentions = computed(() => new Set(props.selectedMentionIds))
function isSelectedMention(entity: TranscriptionEntitySpan) {
  return (
    props.selectedEntityKey === entityKey(entity) ||
    Boolean(entity.mention_id && selectedMentions.value.has(entity.mention_id))
  )
}

function mentionSelectionState(entity: TranscriptionEntitySpan) {
  const key = entityKey(entity)
  const mentioned = Boolean(entity.entity_id) && highlightedPersonId.value === entity.entity_id
  if (isSelectedMention(entity)) return mentioned ? 'selectedMentioned' : 'selected'
  if (mentioned) return 'mentioned'
  // All fragments of a multiline mention respond to hovering any one of them.
  return hoveredEntityKey.value === key ? 'hovered' : 'default'
}

function lineSegments(line: TranscriptionLine): TranscriptionSegment[] {
  const entities = [...(line.entities ?? [])]
    .filter((entity) => entity.line_id === line.id && line.text.slice(entity.start_index, entity.end_index) === entity.text)
    .sort((left, right) => left.start_index - right.start_index)

  const segments: TranscriptionSegment[] = []
  let cursor = 0

  for (const entity of entities) {
    if (entity.start_index < cursor) continue
    if (entity.start_index > cursor) segments.push({ text: line.text.slice(cursor, entity.start_index) })
    segments.push({ text: entity.text, entity })
    cursor = entity.end_index
  }

  if (cursor < line.text.length) segments.push({ text: line.text.slice(cursor) })
  return segments
}

// Segmentation depends only on the transcription, not on selection or hover.
const segments = computed(() => props.transcription.map(lineSegments))

function isHighlighted(entity: TranscriptionEntitySpan) {
  return highlightsSpan(entity, annotationHighlight.value)
}

function setLineVisibility(value: unknown) {
  if (typeof value === 'string' && LINE_VISIBILITIES.includes(value as LineMode))
    lineVisibility.value = value as LineMode
}

function lineElement(index: number) {
  return (
    scrollElement.value?.querySelector<HTMLElement>(
      `[data-line-index="${index}"]:not([data-hidden])`,
    ) ?? null
  )
}

function textSelection() {
  const selection = typeof window === 'undefined' ? null : window.getSelection()
  const scroller = scrollElement.value
  if (!selection || selection.isCollapsed || !selection.rangeCount || !scroller) return null
  const range = selection.getRangeAt(0)
  if (!range.intersectsNode(scroller)) return null
  // A drag past the text (for example over the minimap) can spill into the rest
  // of the page; only the part inside the transcription counts here.
  const bounds = document.createRange()
  bounds.selectNodeContents(scroller)
  const clipped = range.cloneRange()
  if (clipped.compareBoundaryPoints(Range.START_TO_START, bounds) < 0)
    clipped.setStart(bounds.startContainer, bounds.startOffset)
  if (clipped.compareBoundaryPoints(Range.END_TO_END, bounds) > 0)
    clipped.setEnd(bounds.endContainer, bounds.endOffset)
  return clipped.collapsed ? null : { selection, range: clipped }
}

function selectLine(index: number) {
  // Finishing a drag selection must not also move the selected line.
  if (textSelection()) return
  if (index !== props.selectedLineIndex) emit('select-line', index)
  // Clicking text outside the mentions clears them, as an empty scan click does for faces.
  else if (props.selectedMentionIds.length) emit('clear-mentions')
}

/** A click in the text pane outside every line clears the mentions too. */
function clearOutsideLines(event: MouseEvent) {
  if (!props.selectedMentionIds.length || textSelection()) return
  if ((event.target as Element).closest('[data-line-index], .teleprompter-gap')) return
  emit('clear-mentions')
}

/**
 * Click and Enter/Space select mentions as faces are selected: plain replaces
 * the selection, Ctrl/Cmd toggles one mention and Shift selects a range (#176).
 * A plain keyboard activation moves focus into the person card.
 */
function activateEntity(
  index: number,
  entity: TranscriptionEntitySpan,
  event: MouseEvent | KeyboardEvent,
) {
  if (event instanceof MouseEvent && textSelection()) return
  const mode = mentionSelectMode(event)
  emit('select-entity', index, entity, mode, shownMentionOrder())
  if (mode === 'replace' && event instanceof KeyboardEvent) focusMentionCard()
}

/** Mentions shown in the text (displayed lines, current highlights), in reading order. */
function shownMentionOrder() {
  const ids: string[] = []
  for (const mark of scrollElement.value?.querySelectorAll<HTMLElement>('mark[data-mention-id]') ?? []) {
    const id = mark.dataset.mentionId
    if (id && !mark.closest('[data-hidden]') && !ids.includes(id)) ids.push(id)
  }
  return ids
}

/** Shift/Ctrl-click must not extend or start a native text selection. */
function keepTextSelection(event: MouseEvent) {
  if (event.shiftKey || event.ctrlKey || event.metaKey) event.preventDefault()
}

/**
 * The selected mentions' person card floats above or below the anchor mention,
 * like the face card on the scan (#176): the last clicked mention, else the
 * first selected one still shown.
 */
/** A value safe inside a double-quoted attribute selector. */
function quoted(value: string) {
  return value.replace(/["\\]/g, '\\$&')
}
const cardAnchor = ref<HTMLElement | null>(null)
function updateCardAnchor() {
  const scroller = scrollElement.value
  const visible = (element: HTMLElement | null | undefined) =>
    element && !element.closest('[data-hidden]') ? element : null
  const key = props.selectedEntityKey
  // A card opened on hover stays at the hovered fragment once its mention is selected.
  const hovered = hoverCard.target.value?.element
  cardAnchor.value =
    (props.selectedMentionIds.length &&
      ((key && hovered?.isConnected && hovered.dataset.occurrence === key && visible(hovered)) ||
        (key &&
        visible(scroller?.querySelector<HTMLElement>(`mark[data-occurrence="${quoted(key)}"]`))) ||
        visible(
          [...(scroller?.querySelectorAll<HTMLElement>('mark[aria-pressed="true"]') ?? [])].find(
            (mark) => !mark.closest('[data-hidden]'),
          ),
        ))) ||
    null
}
watch(
  () => [props.selectedEntityKey, props.selectedMentionIds, props.transcription, includedLines.value],
  () => void nextTick(updateCardAnchor),
  { flush: 'post', immediate: true },
)
defineSlots<{ 'mention-card'?: () => unknown; 'panel-actions'?: () => unknown }>()

/** The hovered mention's card replaces the selection's card until the pointer leaves. */
const preview = computed(() => {
  const hovered = hoverCard.target.value
  return hovered && !isSelectedMention(hovered.entity) ? hovered : null
})
watch(
  () => preview.value?.entity.mention_id ?? null,
  (id) => emit('preview-mention', id),
)
// Another selection, or changed text, takes over from a hovered card.
watch(
  () => [props.selectedMentionIds, props.selectedEntityKey, props.transcription],
  () => {
    const hovered = hoverCard.target.value
    if (hovered && (!isSelectedMention(hovered.entity) || !hovered.element.isConnected))
      hoverCard.close(true)
  },
)
// Selecting the hovered mention keeps its card in place, so a press inside it completes.
const shownCardAnchor = computed(() => {
  if (preview.value) return preview.value.element
  const hovered = hoverCard.target.value
  return hovered && entityKey(hovered.entity) === props.selectedEntityKey
    ? hovered.element
    : cardAnchor.value
})
/** Using the previewed card selects its mention, so the card's actions apply to it. */
function selectPreview() {
  const hovered = preview.value
  if (hovered) emit('select-entity', hovered.index, hovered.entity, 'replace', shownMentionOrder())
}
function leaveCard(event: MouseEvent) {
  if (movedIntoNestedLayer(event, event.currentTarget as Element)) selectPreview()
  else hoverCard.close()
}

/**
 * The card may cover nearby mentions. While Ctrl, Cmd or Shift is held, it
 * fades and lets clicks through, so those mentions can still be added.
 */
const selectingMore = ref(false)
function trackModifiers(event: KeyboardEvent) {
  selectingMore.value = event.shiftKey || event.ctrlKey || event.metaKey
}
function releaseModifiers() {
  selectingMore.value = false
}

function mentionCardElement() {
  return document.querySelector<HTMLElement>('[data-mention-card]')
}
/** Move focus into the card once it is shown, as a keyboard face selection does. */
function focusMentionCard() {
  void nextTick(() =>
    requestAnimationFrame(() => mentionCardElement()?.focus({ preventScroll: true })),
  )
}

function clearMentions() {
  const key = props.selectedEntityKey
  const fromCard = mentionCardElement()?.contains(document.activeElement)
  emit('clear-mentions')
  // Return focus from the card to the mention it was opened from.
  if (fromCard)
    scrollElement.value
      ?.querySelector<HTMLElement>(`[data-occurrence="${quoted(key ?? '')}"]`)
      ?.focus({ preventScroll: true })
}

const SELECTION_ACTION_HEIGHT = 24
type SelectionAction = {
  kind: 'create' | 'change' | 'merge'
  lineIndex: number
  name: string
  context: string
  mentionId?: string
  /** Overlapped mentions, in text order, when merging. */
  mentionIds?: string[]
  left: number
  top: number
}
/** Create, Change or Merge mentions for text selected in the transcription. */
const selectionAction = ref<SelectionAction | null>(null)
const WORD_CHARACTER = /[\p{L}\p{N}]/u

/** The selection's character offset within one line's text element. */
function lineOffset(element: HTMLElement, container: Node, offset: number) {
  const before = document.createRange()
  before.selectNodeContents(element)
  before.setEnd(container, offset)
  return before.toString().length
}

/**
 * Create or Change mention for text selected within one line or across
 * consecutive lines. The selection grows to whole words; the context is the
 * selected lines' text, which locates the mention exactly once (#176).
 */
function measureSelectionAction(): SelectionAction | null {
  if (!props.canCreateMention && !props.canChangeMention && !props.canMergeMentions) return null
  const current = textSelection()
  const body = bodyElement.value
  if (!current || !body) return null
  const { range } = current
  const elements = [
    ...(scrollElement.value?.querySelectorAll<HTMLElement>('[data-line-text]') ?? []),
  ].filter((element) => range.intersectsNode(element))
  const first = elements[0]
  const last = elements[elements.length - 1]
  if (!first || !last) return null
  if (!first.contains(range.startContainer) || !last.contains(range.endContainer)) return null
  const indices = elements.map((element) =>
    Number(element.closest<HTMLElement>('[data-line-index]')?.dataset.lineIndex),
  )
  // Consecutive, shown lines only: a selection across a collapsed gap offers nothing.
  if (
    indices.some((index, position) => position > 0 && index !== indices[position - 1]! + 1) ||
    indices.some((index) => !includedLines.value[index])
  )
    return null
  const lines = indices.map((index) => props.transcription[index])
  if (lines.some((line) => !line)) return null
  const firstLine = lines[0]!
  const lastLine = lines[lines.length - 1]!
  let start = lineOffset(first, range.startContainer, range.startOffset)
  let end = lineOffset(last, range.endContainer, range.endOffset)
  if (start > firstLine.text.length || end > lastLine.text.length) return null
  // Trim spaces, then cover whole words at both ends.
  const single = lines.length === 1
  while (start < (single ? end : firstLine.text.length) && /\s/.test(firstLine.text[start]!))
    start += 1
  while (end > (single ? start : 0) && /\s/.test(lastLine.text[end - 1]!)) end -= 1
  if (single && start === end) return null
  while (start > 0 && WORD_CHARACTER.test(firstLine.text[start - 1]!)) start -= 1
  while (end < lastLine.text.length && WORD_CHARACTER.test(lastLine.text[end]!)) end += 1
  const parts = single
    ? [firstLine.text.slice(start, end)]
    : [
        firstLine.text.slice(start),
        ...lines.slice(1, -1).map((line) => line!.text),
        lastLine.text.slice(0, end),
      ]
  const name = parts
    .map((part) => part.trim())
    .filter(Boolean)
    .join(' ')
  if (!name) return null
  // Mentions whose fragments overlap the selected characters on any line.
  const overlapping = lines.flatMap((line, position) => {
    const from = position === 0 ? start : 0
    const to = position === lines.length - 1 ? end : line!.text.length
    return (line!.entities ?? []).filter(
      (span) => span.mention_id && span.start_index < to && span.end_index > from,
    )
  })
  const overlappedIds = [
    ...new Set(overlapping.flatMap((span) => (span.mention_id ? [span.mention_id] : []))),
  ]
  const target = overlapping[0]
  // Several overlapped mentions merge into one covering the selection.
  if (overlappedIds.length > 1) {
    if (!props.canMergeMentions) return null
  } else if (target) {
    // Exactly the mention's own words: nothing to change.
    const fragments = props.transcription.flatMap((line, index) =>
      (line.entities ?? [])
        .filter((span) => entityKey(span) === entityKey(target))
        .map((span) => ({ index, span })),
    )
    const head = fragments[0]
    const tail = fragments[fragments.length - 1]
    const unchanged =
      head !== undefined &&
      tail !== undefined &&
      head.index === indices[0] &&
      tail?.index === indices[indices.length - 1] &&
      head.span.start_index === start &&
      tail.span.end_index === end
    if (!props.canChangeMention || unchanged) return null
  } else if (!props.canCreateMention) return null
  // The context grows to neighbouring lines until it locates this mention once.
  const context = uniqueMentionContext(props.transcription, indices[0]!, indices[indices.length - 1]!, start, name)
  if (context === null) return null
  const bounds = body.getBoundingClientRect()
  // Older engines (and jsdom) lack Range geometry; the line still places the action.
  const rect =
    typeof range.getBoundingClientRect === 'function'
      ? range.getBoundingClientRect()
      : first.getBoundingClientRect()
  const above = rect.top - bounds.top - SELECTION_ACTION_HEIGHT - 4
  return {
    kind: overlappedIds.length > 1 ? 'merge' : target ? 'change' : 'create',
    lineIndex: indices[0]!,
    name,
    context,
    mentionId: target?.mention_id,
    mentionIds: overlappedIds.length > 1 ? overlappedIds : undefined,
    left: Math.max(0, rect.left - bounds.left),
    top: above >= 0 ? above : rect.bottom - bounds.top + 4,
  }
}

function applySelectionAction() {
  const action = selectionAction.value
  if (!action) return
  if (action.kind === 'merge' && action.mentionIds)
    emit('merge-mentions', { mentionIds: action.mentionIds, name: action.name, context: action.context })
  else if (action.kind === 'change' && action.mentionId)
    emit('change-mention', { mentionId: action.mentionId, name: action.name, context: action.context })
  else emit('create-mention', { lineIndex: action.lineIndex, name: action.name, context: action.context })
  window.getSelection()?.removeAllRanges()
  selectionAction.value = null
}

/** Whether a range covers a whole element, such as a collapsed gap band. */
function coversElement(range: Range, element: Element) {
  const bounds = document.createRange()
  bounds.selectNode(element)
  return (
    range.compareBoundaryPoints(Range.START_TO_START, bounds) <= 0 &&
    range.compareBoundaryPoints(Range.END_TO_END, bounds) >= 0
  )
}

/**
 * Text of the selection, one row per line, without numbers, badges or
 * controls. Hidden lines stay in the DOM, so a selection across a collapsed
 * gap spans them natively and copies them in reading order.
 */
function copiedText(range: Range) {
  const parts: string[] = []
  for (const element of scrollElement.value?.querySelectorAll<HTMLElement>('[data-line-text]') ?? []) {
    if (!range.intersectsNode(element)) continue
    const part = document.createRange()
    part.selectNodeContents(element)
    if (range.compareBoundaryPoints(Range.START_TO_START, part) > 0)
      part.setStart(range.startContainer, range.startOffset)
    if (range.compareBoundaryPoints(Range.END_TO_END, part) < 0)
      part.setEnd(range.endContainer, range.endOffset)
    const fragment = part.cloneContents()
    fragment.querySelectorAll('[data-copy-exclude]').forEach((node) => node.remove())
    parts.push(fragment.textContent ?? '')
  }
  return parts.join('\n')
}

function handleCopy(event: ClipboardEvent) {
  const current = textSelection()
  if (!current || !event.clipboardData) return
  event.clipboardData.setData('text/plain', copiedText(current.range))
  event.preventDefault()
}

/** Collapsed gaps inside the current text selection, tinted to show they are included. */
const selectedGaps = ref<ReadonlySet<number>>(new Set())
let selectionFrame: number | undefined
function measureSelectedGaps() {
  selectionFrame = undefined
  selectionAction.value = measureSelectionAction()
  const current = textSelection()
  const next = new Set<number>()
  if (current)
    for (const gap of scrollElement.value?.querySelectorAll<HTMLElement>('[data-gap-start]') ?? [])
      if (coversElement(current.range, gap)) next.add(Number(gap.dataset.gapStart))
  const previous = selectedGaps.value
  if (next.size !== previous.size || [...next].some((start) => !previous.has(start)))
    selectedGaps.value = next
}
function scheduleSelectedGaps() {
  if (selectionFrame === undefined && typeof requestAnimationFrame !== 'undefined')
    selectionFrame = requestAnimationFrame(measureSelectedGaps)
}

/** After explicit selection, scroll just enough to bring the selected line into view. */
let revealPending = true
let pagedSelection: number | null = null
function revealSelectedLine() {
  const scroller = scrollElement.value
  const line = lineElement(props.selectedLineIndex)
  if (!scroller || !line) return
  revealPending = false
  const top = line.offsetTop
  const bottom = top + line.offsetHeight
  if (top < scroller.scrollTop) scroller.scrollTop = top
  else if (bottom > scroller.scrollTop + scroller.clientHeight)
    scroller.scrollTop = bottom - scroller.clientHeight
}

function centerOn(element: HTMLElement) {
  const scroller = scrollElement.value
  if (!scroller) return
  scroller.scrollTop = element.offsetTop + element.offsetHeight / 2 - scroller.clientHeight / 2
}

/**
 * Minimap navigation only scrolls: an included target is centered, and a
 * hidden target centers its collapsed gap between the nearest passages.
 */
function navigateTo(index: number) {
  const target =
    lineElement(index) ??
    [...(scrollElement.value?.querySelectorAll<HTMLElement>('[data-gap-start]') ?? [])].find(
      (gap) => Number(gap.dataset.gapStart) <= index && index <= Number(gap.dataset.gapEnd),
    )
  if (target) centerOn(target)
}

/** Displayed lines fully inside the viewport, or partly when none fit completely. */
function linesInView(lines: HTMLElement[], top: number, bottom: number) {
  const full = lines.filter(
    (line) => line.offsetTop >= top - 1 && line.offsetTop + line.offsetHeight <= bottom + 1,
  )
  return full.length
    ? full
    : lines.filter((line) => line.offsetTop + line.offsetHeight > top && line.offsetTop < bottom)
}

/**
 * Page Up/Down move the cursor (the selected line) like an editor. When the
 * text can scroll, show the next or previous non-overlapping view and select
 * its first line; at the end or beginning, select the last or first line of
 * the current view instead. Only displayed lines take part.
 */
function scrollPage(direction: 'next' | 'previous') {
  const scroller = scrollElement.value
  const lines = [
    ...(scroller?.querySelectorAll<HTMLElement>('[data-line-index]:not([data-hidden])') ?? []),
  ]
  if (!scroller || !lines.length) return
  const top = scroller.scrollTop
  const view = linesInView(lines, top, top + scroller.clientHeight)
  const first = view[0] ?? lines[0]!
  const last = view[view.length - 1] ?? first
  const maximum = scroller.scrollHeight - scroller.clientHeight
  let target: HTMLElement
  // An OCR line may wrap over several screenfuls, especially on a phone. Page
  // through its visual text before advancing to the next original line.
  const edge = direction === 'next' ? top + scroller.clientHeight : top
  const crossing = lines.find((line) =>
    line.offsetHeight > scroller.clientHeight &&
    line.offsetTop < edge - 1 && line.offsetTop + line.offsetHeight > edge + 1,
  )
  if (crossing) {
    const step = direction === 'next' ? scroller.clientHeight : -scroller.clientHeight
    scroller.scrollTop = Math.max(0, Math.min(maximum, top + step))
    target = crossing
  } else if (direction === 'next') {
    const below = lines[lines.indexOf(last) + 1]
    if (below && top < maximum - 1) {
      scroller.scrollTop = Math.min(maximum, below.offsetTop)
      target = below
    } else target = last
  } else {
    const above = lines[lines.indexOf(first) - 1]
    if (above && top > 1) {
      scroller.scrollTop = Math.max(0, above.offsetTop + above.offsetHeight - scroller.clientHeight)
      const next = scroller.scrollTop
      target = linesInView(lines, next, next + scroller.clientHeight)[0] ?? above
    } else target = first
  }
  const index = Number(target.dataset.lineIndex)
  if (index !== props.selectedLineIndex) {
    // The parent updates scan selection, but must not then scroll to the far
    // end of a tall line to try to fit the whole line inside this viewport.
    pagedSelection = index
    emit('select-line', index)
  }
}

/** Wheel input over the minimap scrolls the text, like the scrollbar it replaces. */
function scrollBy(deltaY: number) {
  if (scrollElement.value) scrollElement.value.scrollTop += deltaY
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'PageDown' && event.key !== 'PageUp') return
  event.preventDefault()
  scrollPage(event.key === 'PageDown' ? 'next' : 'previous')
}

let viewportFrame: number | undefined
function measureViewport() {
  viewportFrame = undefined
  const scroller = scrollElement.value
  const lines = [
    ...(scroller?.querySelectorAll<HTMLElement>('[data-line-index]:not([data-hidden])') ?? []),
  ]
  if (!scroller || !lines.length) {
    viewport.value = null
    return
  }
  const top = scroller.scrollTop
  const bottom = top + scroller.clientHeight
  // Lines are in document order: binary-search the first line reaching the viewport.
  let low = 0
  let high = lines.length - 1
  while (low < high) {
    const middle = (low + high) >> 1
    if (lines[middle]!.offsetTop + lines[middle]!.offsetHeight <= top) low = middle + 1
    else high = middle
  }
  let last = low
  while (last + 1 < lines.length && lines[last + 1]!.offsetTop < bottom) last += 1
  viewport.value = {
    first: Number(lines[low]!.dataset.lineIndex),
    last: Number(lines[last]!.dataset.lineIndex),
  }
}
function scheduleViewport() {
  if (viewportFrame === undefined && typeof requestAnimationFrame !== 'undefined')
    viewportFrame = requestAnimationFrame(measureViewport)
}

let resizeObserver: ResizeObserver | undefined
onMounted(() => {
  document.addEventListener('selectionchange', scheduleSelectedGaps)
  window.addEventListener('keydown', trackModifiers)
  window.addEventListener('keyup', trackModifiers)
  window.addEventListener('blur', releaseModifiers)
  if (scrollElement.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(scheduleViewport)
    resizeObserver.observe(scrollElement.value)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', scheduleSelectedGaps)
  window.removeEventListener('keydown', trackModifiers)
  window.removeEventListener('keyup', trackModifiers)
  window.removeEventListener('blur', releaseModifiers)
  if (selectionFrame !== undefined) cancelAnimationFrame(selectionFrame)
  resizeObserver?.disconnect()
  if (viewportFrame !== undefined) cancelAnimationFrame(viewportFrame)
})

// Hiding visible selected text, through a mode change or Reset, clears that selection.
watch(
  includedLines,
  (next, previous) => {
    const current = textSelection()
    if (!current) return
    for (const element of scrollElement.value?.querySelectorAll<HTMLElement>('[data-line-index]') ?? []) {
      const index = Number(element.dataset.lineIndex)
      if (previous?.[index] && !next[index] && current.range.intersectsNode(element)) {
        current.selection.removeAllRanges()
        return
      }
    }
  },
  { flush: 'pre' },
)

watch(
  () => props.selectedLineIndex,
  () => {
    revealPending = props.selectedLineIndex !== pagedSelection
    pagedSelection = null
  },
  { flush: 'sync' },
)

watch(
  () => [props.selectedLineIndex, includedLines.value, props.isTranslationOpen, isTranslationExpanded.value],
  async () => {
    await nextTick()
    if (revealPending) revealSelectedLine()
    scheduleViewport()
  },
  { flush: 'post', immediate: true },
)

watch(
  () => props.selectedLanguage,
  () => {
    isTranslationExpanded.value = false
  },
)

function expandTranslation() {
  if (isTranslationExpanded.value) return
  const translation = translationElement.value
  if (translation && translation.scrollWidth > translation.clientWidth) {
    isTranslationExpanded.value = true
  }
}

defineExpose({ scrollPage, navigateTo, focusMentionCard })
</script>

<template>
  <div class="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-background">
    <PanelBar label="Teleprompter settings">
      <ToggleGroup type="single" variant="outline" size="sm" class="shrink-0" aria-label="Lines"
        :model-value="lineVisibility" @update:model-value="setLineVisibility">
        <ToggleGroupItem v-for="mode in LINE_VISIBILITIES" :key="mode" :value="mode" class="gap-1 px-2"
          :aria-label="lineVisibilityLabels[mode]" :title="lineVisibilityLabels[mode]">
          <component :is="lineVisibilityIcons[mode]" class="size-3.5" aria-hidden="true" />
          <span class="hidden @3xl:inline">{{ lineVisibilityLabels[mode] }}</span>
        </ToggleGroupItem>
        <!-- Shown only while active, and always labeled: revealing lines creates it,
          choosing a mode leaves it. -->
        <ToggleGroupItem v-if="lineVisibility === 'custom'" value="custom" class="gap-1 px-2"
          :aria-label="lineVisibilityLabels.custom" title="Lines you revealed. Choose a mode to reset.">
          <component :is="lineVisibilityIcons.custom" class="size-3.5" aria-hidden="true" />
          {{ lineVisibilityLabels.custom }}
        </ToggleGroupItem>
      </ToggleGroup>
      <AnnotationStateToggles v-model="annotationHighlight" />
      <template v-if="$slots['panel-actions']" #end>
        <slot name="panel-actions" />
      </template>
    </PanelBar>

    <div ref="bodyElement"
      class="relative grid min-h-0 grid-cols-[minmax(0,1fr)_2.5rem] gap-2 px-3 sm:grid-cols-[minmax(0,1fr)_3.5rem] sm:px-6">
      <section ref="scrollElement" tabindex="0"
        class="teleprompter-scroll relative min-h-0 overflow-y-auto py-2 text-base font-serif leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        aria-label="Transcription teleprompter" @scroll.passive="scheduleViewport(); hoverCard.close(true)" @keydown="handleKeydown"
        @click="clearOutsideLines"
        @copy="handleCopy">
        <p v-if="emptyMessage" class="px-2 py-4 font-sans text-sm text-muted-foreground">{{ emptyMessage }}</p>
        <!-- Every line stays in the DOM; hidden lines only stop being displayed, so
          text selection spans collapsed gaps natively. -->
        <template v-for="(line, index) in transcription" :key="line.id">
          <div v-if="gapsByStart.get(index)" :data-gap-start="index" :data-gap-end="gapsByStart.get(index)!.end"
            :data-selected="selectedGaps.has(index) ? '' : undefined"
            class="teleprompter-gap flex select-none flex-col border-y bg-muted/50 font-sans">
            <!-- Each action spans the full row; its icon sits in the line-number gutter. -->
            <Button v-for="(action, actionIndex) in gapActions(gapsByStart.get(index)!)" :key="action.label"
              variant="ghost" size="xs" class="w-full justify-start gap-0 rounded-none px-0"
              :aria-label="action.label" @click="emit('expand', action.passage, action.direction, action.count)">
              <span class="flex w-10 shrink-0 justify-center"><component :is="action.icon" aria-hidden="true" /></span>
              <span class="truncate">{{ action.text }}</span>
              <small v-if="actionIndex === 0" class="ml-auto shrink-0 pr-2 text-muted-foreground" aria-hidden="true">
                {{ lineCountText(gapsByStart.get(index)!.end - index + 1) }}
              </small>
            </Button>
          </div>
            <div v-show="includedLines[index]" role="group"
              :aria-label="`Line ${index + 1}`" :data-line-index="index"
              :data-hidden="includedLines[index] ? undefined : ''"
              class="teleprompter-line grid min-w-0 grid-cols-[2.5rem_1fr] items-start rounded-sm text-left transition-colors"
              :class="index === selectedLineIndex
                ? 'bg-muted text-foreground'
                : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'"
              :aria-current="index === selectedLineIndex ? 'true' : undefined" @click="selectLine(index)">
              <small class="select-none pr-2 text-right font-mono font-bold uppercase"
                :class="index === selectedLineIndex ? 'text-secondary' : 'text-muted-foreground'" aria-hidden="true">
                L{{ index + 1 }}
              </small>
              <p data-line-text class="cursor-text select-text font-serif leading-[1.75em]">
                <template v-for="(segment, segmentIndex) in segments[index]" :key="segmentIndex">
                  <mark v-if="segment.entity && isHighlighted(segment.entity)" tabindex="0" role="button"
                    :aria-label="mentionLabel(segment.entity)" :data-link-state="spanHighlightState(segment.entity)"
                    :aria-pressed="isSelectedMention(segment.entity)"
                    :data-occurrence="entityKey(segment.entity)"
                    :data-mention-id="segment.entity.mention_id"
                    class="transcription-entity cursor-pointer" :class="mentionClasses(segment.entity)"
                    :data-selection="mentionSelectionState(segment.entity)"
                    @mouseenter="showMentionCard($event, index, segment.entity)" @mouseleave="hideMentionCard"
                    @focus="showMentionCard($event, index, segment.entity)" @blur="hideMentionCard"
                    @keydown.enter.stop.prevent="activateEntity(index, segment.entity, $event)"
                    @keydown.space.stop.prevent="activateEntity(index, segment.entity, $event)"
                    @keydown.esc="preview ? hoverCard.close(true) : selectedMentionIds.length && ($event.stopPropagation(), clearMentions())"
                    @mousedown="keepTextSelection" @click.stop="activateEntity(index, segment.entity, $event)">
                    {{ segment.text }}
                  </mark>
                  <template v-else>{{ segment.text }}</template>
                </template>
              </p>
            </div>
        </template>
      </section>
      <!-- The person card floats above or below its mention, like a face's card. -->
      <!-- Outside the text, so it never shifts lines or joins a selection or copy. -->
      <Popover :open="Boolean(shownCardAnchor && $slots['mention-card'])">
        <PopoverAnchor :reference="shownCardAnchor ?? undefined" as="span" class="hidden" />
        <PopoverContent v-if="$slots['mention-card']" data-mention-card side="bottom" align="start"
          :side-offset="4" :collision-padding="8"
          sticky="always" hide-when-detached update-position-strategy="always"
          :aria-label="preview ? 'Mention details' : 'Selected mentions'"
          :data-preview="preview ? '' : undefined"
          @mouseenter="hoverCard.hold" @mouseleave="leaveCard"
          @pointerdown.capture="selectPreview" @focusin="selectPreview"
          class="max-h-(--reka-popover-content-available-height) w-64 max-w-[calc(100vw-2rem)] overflow-y-auto p-0 transition-opacity"
          :class="selectingMore && 'pointer-events-none opacity-25'"
          :data-selecting-more="selectingMore ? '' : undefined"
          @open-auto-focus.prevent @close-auto-focus.prevent @interact-outside.prevent
          @escape-key-down.prevent="clearMentions">
          <slot name="mention-card" />
        </PopoverContent>
      </Popover>
      <!-- Create or change a mention from text selected within one line (#176). -->
      <div v-if="selectionAction" class="absolute z-20"
        :style="{ left: `${selectionAction.left}px`, top: `${selectionAction.top}px` }">
        <Button type="button" size="xs" variant="outline" class="bg-background shadow-xs" data-selection-action
          @mousedown.prevent @click="applySelectionAction">
          <TextCursor aria-hidden="true" />
          {{ { create: 'Create mention', change: 'Change mention', merge: 'Merge mentions' }[selectionAction.kind] }}
        </Button>
      </div>
      <div class="min-h-0 select-none overflow-hidden py-2">
        <TeleprompterMinimap :lines="minimap" :viewport="viewport" @navigate="navigateTo"
          @scroll="scrollBy" />
      </div>
    </div>

    <section v-if="isTranslationOpen && !emptyMessage"
      class="grid shrink-0 grid-cols-[2.5rem_minmax(0,1fr)_2rem] items-start border-t bg-background px-3 py-2 text-base sm:px-6"
      aria-label="Translate teleprompter text">
      <small class="pr-2 text-right font-mono font-bold uppercase text-secondary">
        {{ selectedLanguage }}
      </small>
      <p v-if="translationLoading" ref="translationElement"
        class="min-w-0 select-text overflow-hidden font-serif italic leading-[1.75em]" aria-label="Loading translation"
        aria-busy="true">
        <span class="inline-block h-5 w-3/4 animate-pulse rounded-sm bg-muted" />
      </p>
      <p v-else ref="translationElement"
        class="min-w-0 select-text overflow-hidden font-serif italic text-muted-foreground leading-[1.75em]"
        :class="isTranslationExpanded ? 'cursor-text' : 'h-[1.75em] cursor-pointer whitespace-nowrap truncate'"
        :aria-expanded="isTranslationExpanded" @click="expandTranslation">
        {{ currentTranslation || 'No translation available' }}
      </p>
      <Button v-if="isTranslationExpanded" variant="ghost" size="icon-xs" class="-mt-1"
        aria-label="Collapse translation" title="Collapse translation" @click="isTranslationExpanded = false">
        <X />
      </Button>
    </section>
  </div>
</template>

<style scoped>
/* Off-screen lines skip rendering work but stay in the DOM for selection and copying. */
/* The minimap replaces the scrollbar; wheel, touch and keyboard scrolling remain. */
.teleprompter-scroll {
  scrollbar-width: none;
}
.teleprompter-scroll::-webkit-scrollbar {
  display: none;
}

/* A collapsed gap inside a text selection: its hidden lines are copied too. */
.teleprompter-gap[data-selected] {
  background-color: color-mix(in srgb, Highlight 30%, transparent);
}

.teleprompter-line {
  content-visibility: auto;
  contain-intrinsic-size: auto 1.75em;
}
</style>

<style>
/* The card's portal wrapper lets clicks pass too while a modifier is held. */
[data-reka-popper-content-wrapper]:has(> [data-selecting-more]) {
  pointer-events: none !important;
}
</style>
