<script setup lang="ts">
import { X } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'

import type { EntityType } from '@/client/types.gen'
import type {
  TranscriptionEntitySpan,
  TranscriptionLine,
  TranslationLanguage,
  VisibleTranscriptionLine,
} from '@/components/custom/document-page.types'
import { Button } from '@/components/ui/button'

type TranscriptionSegment = {
  text: string
  entity?: TranscriptionEntitySpan
}

const props = defineProps<{
  visibleTranscription: VisibleTranscriptionLine[]
  selectedLineIndex: number
  contextLineCount: number
  selectedEntityKey: string | null
  isTranslationOpen: boolean
  selectedLanguage: TranslationLanguage
  currentTranslation: string
}>()

const emit = defineEmits<{
  'select-line': [index: number]
  'select-entity': [index: number, entity: TranscriptionEntitySpan]
  'navigate-line': [direction: 'next' | 'previous']
}>()

const entityClasses = {
  person: 'border-b-2 border-secondary/60 text-secondary',
  place: 'border-b-2 border-accent/60 text-accent',
  date: 'border-b border-foreground/40 text-foreground',
} satisfies Record<EntityType, string>

const entityLabels = {
  person: 'Person',
  place: 'Place',
  date: 'Date',
} satisfies Record<EntityType, string>

const hoveredEntityKey = ref<string | null>(null)
const teleprompterElement = ref<HTMLElement | null>(null)
const translationElement = ref<HTMLElement | null>(null)
const isTranslationExpanded = ref(false)

function entityKey(entity: TranscriptionEntitySpan) {
  return `${entity.line_id}:${entity.start_index}:${entity.end_index}`
}

function entityStyle(entity: TranscriptionEntitySpan) {
  const key = entityKey(entity)
  if (props.selectedEntityKey === key) {
    return { backgroundColor: 'color-mix(in srgb, var(--accent) 25%, transparent)', outline: '1px solid var(--accent)' }
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

  teleprompter.scrollTop = 0
  const teleprompterBounds = teleprompter.getBoundingClientRect()
  const selectedLineBounds = selectedLine.getBoundingClientRect()

  if (selectedLineBounds.top < teleprompterBounds.top) {
    teleprompter.scrollTop = selectedLineBounds.top - teleprompterBounds.top
  } else if (selectedLineBounds.bottom > teleprompterBounds.bottom) {
    teleprompter.scrollTop = selectedLineBounds.bottom - teleprompterBounds.bottom
  }
}

watch(
  () => [props.selectedLineIndex, props.contextLineCount],
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
  <section ref="teleprompterElement"
    class="my-2 min-h-0 shrink-0 overflow-hidden bg-background text-sm font-serif leading-5"
    :style="{ maxHeight: `calc(${contextLineCount} * 1.75em)` }" aria-label="Transcription teleprompter"
    @wheel.stop.prevent="handleWheel">
    <template v-for="item in visibleTranscription" :key="item.line.id">
      <component :is="item.index === selectedLineIndex ? 'div' : 'button'"
        :type="item.index === selectedLineIndex ? undefined : 'button'"
        class="grid min-h-max min-w-0 grid-cols-[2rem_1fr] items-start rounded-sm text-left transition-colors" :class="item.index === selectedLineIndex
          ? 'cursor-text select-text bg-muted text-foreground'
          : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'"
        :aria-current="item.index === selectedLineIndex ? 'true' : undefined"
        @click="item.index !== selectedLineIndex && emit('select-line', item.index)">
        <small class="font-mono font-bold uppercase text-secondary text-right pr-2"
          :class="item.index === selectedLineIndex ? 'text-secondary' : 'text-muted-foreground'" aria-hidden="true">
          L{{ item.index + 1 }}
        </small>
        <p class="font-serif leading-[1.75em]">
          <template v-for="(segment, segmentIndex) in transcriptionSegments(item.line)" :key="segmentIndex">
            <mark v-if="segment.entity" class="transcription-entity cursor-pointer"
              :class="entityClasses[segment.entity.label]" :style="entityStyle(segment.entity)"
              :title="`${entityLabels[segment.entity.label]}: ${segment.entity.text}`"
              @mouseenter="hoveredEntityKey = entityKey(segment.entity)" @mouseleave="hoveredEntityKey = null"
              @click.stop="emit('select-entity', item.index, segment.entity)">
              {{ segment.text }}
            </mark>
            <template v-else>{{ segment.text }}</template>
          </template>
        </p>
      </component>
    </template>
  </section>

  <section v-if="isTranslationOpen"
    class="grid shrink-0 grid-cols-[2rem_minmax(0,1fr)_2rem] items-start border-t bg-background py-2 text-sm"
    aria-label="Line translation">
    <small class="pr-2 text-right font-mono font-bold uppercase text-secondary">
      {{ selectedLanguage }}
    </small>
    <p ref="translationElement"
      class="min-w-0 select-text overflow-hidden font-serif italic text-muted-foreground leading-[1.75em]"
      :class="isTranslationExpanded ? 'cursor-text' : 'h-[1.75em] cursor-pointer whitespace-nowrap truncate'"
      :aria-expanded="isTranslationExpanded" @click="expandTranslation">
      {{ currentTranslation }}
    </p>
    <Button v-if="isTranslationExpanded" variant="ghost" size="icon-xs" class="-mt-1" aria-label="Collapse translation"
      title="Collapse translation" @click="isTranslationExpanded = false">
      <X />
    </Button>
  </section>
</template>
