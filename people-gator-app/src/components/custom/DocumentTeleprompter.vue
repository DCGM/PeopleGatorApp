<script setup lang="ts">
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import TeleprompterMinimap from './TeleprompterMinimap.vue'
import { linkTooltip } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowDownFromLine,
  ArrowUpFromLine,
  Highlighter,
  UnfoldVertical,
  X,
} from '@lucide/vue'

import type { EntityType, Language } from '@/client/types.gen'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import {
  ANNOTATION_HIGHLIGHTS,
  EXPAND_STEP,
  LINE_VISIBILITIES,
  annotationHighlightLabels,
  highlightsSpan,
  lineVisibilityLabels,
  minimapLines,
  passages as toPassages,
  type AnnotationHighlight,
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
    /** Original lines currently available in the text; defaults to all. */
    included?: boolean[]
    hasExpansions?: boolean
    isTranslationOpen?: boolean
    selectedLanguage?: Language
    currentTranslation?: string
    translationLoading?: boolean
  }>(),
  { included: undefined, hasExpansions: false },
)

const lineVisibility = defineModel<LineVisibility>('lineVisibility', { default: 'all' })
const annotationHighlight = defineModel<AnnotationHighlight>('annotationHighlight', {
  default: 'all',
})

const emit = defineEmits<{
  'select-line': [index: number]
  'select-entity': [index: number, entity: TranscriptionEntitySpan]
  expand: [passage: Passage, direction: 'before' | 'after', count: number]
  reset: []
}>()

const entityClasses = {
  person: 'border-b-2 border-secondary/60 text-secondary',
} satisfies Record<EntityType, string>

const hoveredEntityKey = ref<string | null>(null)
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
        label: `Show ${lineCountText(size)}, ${range}`,
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
          label: `Show ${EXPAND_STEP} lines below L${gap.before.end + 1}`,
          passage: gap.before,
          direction: 'after' as const,
          count: EXPAND_STEP,
        }]
      : []),
    ...(gap.after
      ? [{
          icon: ArrowUpFromLine,
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
  if (lineVisibility.value === 'person')
    return props.relatedEntityId
      ? 'No lines for this person. Select another person or switch to All.'
      : 'Select a person to see their lines.'
  if (lineVisibility.value === 'annotated') return 'No annotated lines. Switch to All.'
  return 'No transcription.'
})

const minimap = computed(() =>
  minimapLines(
    props.transcription,
    includedLines.value,
    annotationHighlight.value,
    props.relatedEntityId,
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

function entityStyle(entity: TranscriptionEntitySpan) {
  const key = entityKey(entity)
  if (props.selectedEntityKey === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--secondary) 25%, transparent)', outline: '1px solid var(--secondary)' }
  }
  if (entity.entity_id && props.relatedEntityId === entity.entity_id) {
    return { backgroundColor: 'color-mix(in srgb, var(--accent) 25%, transparent)', outline: '2px solid var(--accent)' }
  }
  if (hoveredEntityKey.value === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--accent) 15%, transparent)', outline: '1px solid color-mix(in srgb, var(--accent) 50%, transparent)' }
  }
  return { backgroundColor: 'transparent' }
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
  if (typeof value === 'string' && LINE_VISIBILITIES.includes(value as LineVisibility))
    lineVisibility.value = value as LineVisibility
}

function setAnnotationHighlight(value: unknown) {
  if (typeof value === 'string' && ANNOTATION_HIGHLIGHTS.includes(value as AnnotationHighlight))
    annotationHighlight.value = value as AnnotationHighlight
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
  return scroller.contains(range.commonAncestorContainer) ? { selection, range } : null
}

function selectLine(index: number) {
  // Finishing a drag selection must not also move the selected line.
  if (textSelection()) return
  if (index !== props.selectedLineIndex) emit('select-line', index)
}

function activateEntity(index: number, entity: TranscriptionEntitySpan) {
  if (!textSelection()) emit('select-entity', index, entity)
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

/** Page Up/Down: one viewport of available lines, keeping the selected line. */
function scrollPage(direction: 'next' | 'previous') {
  const scroller = scrollElement.value
  if (scroller) scroller.scrollTop += (direction === 'next' ? 1 : -1) * scroller.clientHeight
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
  if (scrollElement.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(scheduleViewport)
    resizeObserver.observe(scrollElement.value)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', scheduleSelectedGaps)
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
    revealPending = true
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

defineExpose({ scrollPage, navigateTo })
</script>

<template>
  <div class="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-background">
    <div role="toolbar" aria-label="Teleprompter settings"
      class="flex min-w-0 flex-row flex-nowrap items-center gap-2 border-b py-1.5">
      <ToggleGroup type="single" variant="outline" size="sm" class="shrink-0" aria-label="Lines"
        :model-value="lineVisibility" @update:model-value="setLineVisibility">
        <ToggleGroupItem v-for="mode in LINE_VISIBILITIES" :key="mode" :value="mode" class="px-2.5">
          {{ lineVisibilityLabels[mode] }}
        </ToggleGroupItem>
      </ToggleGroup>
      <Select :model-value="annotationHighlight" @update:model-value="setAnnotationHighlight">
        <SelectTrigger size="sm" aria-label="Highlight" class="min-w-0 shrink">
          <Highlighter aria-hidden="true" />
          <SelectValue class="truncate" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="option in ANNOTATION_HIGHLIGHTS" :key="option" :value="option">
            {{ annotationHighlightLabels[option] }}
          </SelectItem>
        </SelectContent>
      </Select>
      <Button v-if="hasExpansions" variant="ghost" size="sm" class="ml-auto shrink-0"
        @click="emit('reset')">Reset</Button>
    </div>

    <div class="grid min-h-0 grid-cols-[minmax(0,1fr)_2.5rem] gap-2 sm:grid-cols-[minmax(0,1fr)_3.5rem]">
      <section ref="scrollElement" tabindex="0"
        class="teleprompter-scroll relative min-h-0 overflow-y-auto py-2 text-base font-serif leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        aria-label="Transcription teleprompter" @scroll.passive="scheduleViewport" @keydown="handleKeydown"
        @copy="handleCopy">
        <p v-if="emptyMessage" class="px-2 py-4 font-sans text-sm text-muted-foreground">{{ emptyMessage }}</p>
        <!-- Every line stays in the DOM; hidden lines only stop being displayed, so
          text selection spans collapsed gaps natively. -->
        <template v-for="(line, index) in transcription" :key="line.id">
          <div v-if="gapsByStart.get(index)" :data-gap-start="index" :data-gap-end="gapsByStart.get(index)!.end"
            :data-selected="selectedGaps.has(index) ? '' : undefined"
            class="teleprompter-gap grid select-none grid-cols-[2.5rem_1fr] items-center border-y bg-muted/50 font-sans">
            <div class="flex flex-col items-center">
              <Button v-for="action in gapActions(gapsByStart.get(index)!)" :key="action.label" variant="ghost"
                size="icon-xs" :aria-label="action.label" :title="action.label"
                @click="emit('expand', action.passage, action.direction, action.count)">
                <component :is="action.icon" aria-hidden="true" />
              </Button>
            </div>
            <small class="px-1 text-xs text-muted-foreground">
              {{ lineCountText(gapsByStart.get(index)!.end - index + 1) }}
            </small>
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
                    :aria-label="`${entityText(segment.entity)}: ${linkTooltip(segment.entity)}`"
                    class="transcription-entity cursor-pointer" :class="entityClasses[segment.entity.label]"
                    :style="entityStyle(segment.entity)"
                    @mouseenter="hoveredEntityKey = entityKey(segment.entity)" @mouseleave="hoveredEntityKey = null"
                    @keydown.enter.stop.prevent="emit('select-entity', index, segment.entity)"
                    @keydown.space.stop.prevent="emit('select-entity', index, segment.entity)"
                    @click.stop="activateEntity(index, segment.entity)">
                    {{ segment.text }}<EntityLinkStateBadge v-if="segment.entity.firstFragment !== false"
                      v-bind="segment.entity" :focusable="false" :tooltip="false" compact data-copy-exclude
                      class="ml-1 inline-flex select-none align-middle" />
                  </mark>
                  <template v-else>{{ segment.text }}</template>
                </template>
              </p>
            </div>
        </template>
      </section>
      <div class="min-h-0 overflow-hidden py-2">
        <TeleprompterMinimap :lines="minimap" :viewport="viewport" @navigate="navigateTo"
          @scroll="scrollBy" />
      </div>
    </div>

    <section v-if="isTranslationOpen && !emptyMessage"
      class="grid shrink-0 grid-cols-[2.5rem_minmax(0,1fr)_2rem] items-start border-t bg-background py-2 text-base"
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
