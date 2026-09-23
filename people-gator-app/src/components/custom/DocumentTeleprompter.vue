<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { X } from '@lucide/vue'

import type { EntityType, Language } from '@/client/types.gen'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'

type TranscriptionSegment = {
  text: string
  entity?: TranscriptionEntitySpan
}

const props = defineProps<{
  transcription: TranscriptionLine[]
  selectedLineIndex: number
  selectedEntityKey: string | null
  relatedEntityKey: string | null
  isTranslationOpen?: boolean
  selectedLanguage?: Language
  currentTranslation?: string
  translationLoading?: boolean
}>()

const emit = defineEmits<{
  'select-line': [index: number]
  'select-entity': [index: number, entity: TranscriptionEntitySpan]
  'navigate-line': [direction: 'next' | 'previous']
}>()

const entityClasses = {
  person: 'border-b-2 border-secondary/60 text-secondary',
} satisfies Record<EntityType, string>

const entityLabels = {
  person: 'Person',
} satisfies Record<EntityType, string>

const hoveredEntityKey = ref<string | null>(null)
const teleprompterElement = ref<HTMLElement | null>(null)
const translationElement = ref<HTMLElement | null>(null)
const isTranslationExpanded = ref(false)
let teleprompterResizeObserver: ResizeObserver | undefined

function entityKey(entity: TranscriptionEntitySpan) {
  return transcriptionEntityKey(entity)
}

function entityText(entity: TranscriptionEntitySpan) {
  if (!entity.entity_id) return entity.text

  return props.transcription
    .flatMap((line) => line.entities ?? [])
    .filter((fragment) => fragment.entity_id === entity.entity_id)
    .map((fragment) => fragment.text.trim())
    .join(' ')
}

function entityStyle(entity: TranscriptionEntitySpan) {
  const key = entityKey(entity)
  if (props.selectedEntityKey === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--secondary) 25%, transparent)', outline: '1px solid var(--secondary)' }
  }
  if (props.relatedEntityKey === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--accent) 25%, transparent)', outline: '2px solid var(--accent)' }
  }
  if (hoveredEntityKey.value === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--accent) 15%, transparent)', outline: '1px solid color-mix(in srgb, var(--accent) 50%, transparent)' }
  }
  return { backgroundColor: 'transparent' }
}

function transcriptionSegments(line: TranscriptionLine): TranscriptionSegment[] {
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

function handleWheel(event: WheelEvent) {
  if (Math.abs(event.deltaY) < 4) return
  emit('navigate-line', event.deltaY > 0 ? 'next' : 'previous')
}

function expandTranslation() {
  if (isTranslationExpanded.value) return
  const translation = translationElement.value
  if (translation && translation.scrollWidth > translation.clientWidth) {
    isTranslationExpanded.value = true
  }
}

function revealSelectedLine() {
  const teleprompter = teleprompterElement.value
  const selectedLine = teleprompter?.querySelector<HTMLElement>('[aria-current="true"]')
  if (!teleprompter || !selectedLine) return

  const teleprompterBounds = teleprompter.getBoundingClientRect()
  const selectedLineBounds = selectedLine.getBoundingClientRect()
  const selectedCenter = selectedLineBounds.top - teleprompterBounds.top
    + teleprompter.scrollTop + selectedLineBounds.height / 2
  const maximumScrollTop = teleprompter.scrollHeight - teleprompter.clientHeight
  teleprompter.scrollTop = Math.min(maximumScrollTop, Math.max(0, selectedCenter - teleprompter.clientHeight / 2))
}

onMounted(() => {
  if (!teleprompterElement.value || typeof ResizeObserver === 'undefined') return
  teleprompterResizeObserver = new ResizeObserver(revealSelectedLine)
  teleprompterResizeObserver.observe(teleprompterElement.value)
})

onBeforeUnmount(() => {
  teleprompterResizeObserver?.disconnect()
})

watch(
  () => [props.selectedLineIndex, props.isTranslationOpen, isTranslationExpanded.value],
  async () => {
    await nextTick()
    revealSelectedLine()
  },
  { flush: 'post', immediate: true },
)

watch(
  () => props.selectedLanguage,
  () => {
    isTranslationExpanded.value = false
  },
)

</script>

<template>
  <div class="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden bg-background"
    @wheel.stop.prevent="handleWheel">
    <section ref="teleprompterElement" class="min-h-0 overflow-hidden py-2 text-base font-serif leading-5"
      aria-label="Transcription teleprompter">
      <template v-for="(line, index) in transcription" :key="line.id">
        <component :is="index === selectedLineIndex ? 'div' : 'button'"
          :type="index === selectedLineIndex ? undefined : 'button'"
          class="grid min-h-max min-w-0 grid-cols-[2rem_1fr] items-start rounded-sm text-left transition-colors" :class="index === selectedLineIndex
            ? 'cursor-text select-text bg-muted text-foreground'
            : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'"
          :aria-current="index === selectedLineIndex ? 'true' : undefined"
          @click="index !== selectedLineIndex && emit('select-line', index)">
          <small class="font-mono font-bold uppercase text-secondary text-right pr-2"
            :class="index === selectedLineIndex ? 'text-secondary' : 'text-muted-foreground'" aria-hidden="true">
            L{{ index + 1 }}
          </small>
          <p class="font-serif leading-[1.75em]">
            <template v-for="(segment, segmentIndex) in transcriptionSegments(line)" :key="segmentIndex">
              <mark v-if="segment.entity" class="transcription-entity cursor-pointer"
                :class="entityClasses[segment.entity.label]" :style="entityStyle(segment.entity)"
                :title="`${entityLabels[segment.entity.label]}: ${entityText(segment.entity)}`"
                @mouseenter="hoveredEntityKey = entityKey(segment.entity)" @mouseleave="hoveredEntityKey = null"
                @click.stop="emit('select-entity', index, segment.entity)">
                {{ segment.text }}
              </mark>
              <template v-else>{{ segment.text }}</template>
            </template>
          </p>
        </component>
      </template>
    </section>

    <section v-if="isTranslationOpen"
      class="grid shrink-0 grid-cols-[2rem_minmax(0,1fr)_2rem] items-start border-t bg-background py-2 text-base"
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
