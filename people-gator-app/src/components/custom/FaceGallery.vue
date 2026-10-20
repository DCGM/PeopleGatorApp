<script setup lang="ts">
import UiTooltip from './UiTooltip.vue'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { linkTooltip } from '@/lib/entity-links'
import type { AcceptableValue } from 'reka-ui'
import { computed, nextTick, ref, watch } from 'vue'

import type { Face, FaceStatus } from '@/viewmodels/document-workspace.types'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  faces: Face[]
  selectedFaceId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'reset-filters': []
  select: [faceId: string]
}>()

type FaceFilter = 'all' | FaceStatus

const faceFilter = ref<FaceFilter>('all')
const thumbnailList = ref<HTMLElement | null>(null)
const faceFilterOptions: Array<{ value: FaceFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'assigned', label: 'Annotated' },
  { value: 'unassigned', label: 'Not annotated' },
]
const faceStatusCounts = computed<Record<FaceStatus, number>>(() => {
  const counts: Record<FaceStatus, number> = { assigned: 0, unassigned: 0 }
  for (const face of props.faces) counts[face.status] += 1
  return counts
})
const visibleFaces = computed(() =>
  faceFilter.value === 'all'
    ? props.faces
    : props.faces.filter((face) => face.status === faceFilter.value),
)

function faceFilterCount(filter: FaceFilter) {
  return filter === 'all' ? props.faces.length : faceStatusCounts.value[filter]
}

function emptyFilterLabel(filter: FaceFilter) {
  if (filter === 'assigned') return 'No annotated faces'
  if (filter === 'unassigned') return 'No unannotated faces'
  return 'No faces found'
}

function updateFaceFilter(value: AcceptableValue | AcceptableValue[]) {
  if (faceFilterOptions.some((option) => option.value === value)) {
    faceFilter.value = value as FaceFilter
  }
}

function scrollSelectedThumbnailIntoView() {
  void nextTick(() => {
    const selected = thumbnailList.value?.querySelector<HTMLElement>('[aria-current="true"]')
    const viewport = thumbnailList.value?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
    if (!selected || !viewport) return
    const target = selected.getBoundingClientRect()
    const bounds = viewport.getBoundingClientRect()
    if (target.left >= bounds.left && target.right <= bounds.right) return
    // Keep selection visible inside the strip without scrolling the document viewer offscreen.
    viewport.scrollTo?.({
      left: viewport.scrollLeft + target.left - bounds.left - (bounds.width - target.width) / 2,
      behavior: 'smooth',
    })
  })
}

watch([() => props.selectedFaceId, faceFilter], scrollSelectedThumbnailIntoView, {
  immediate: true,
})
</script>

<template>
  <aside class="min-h-0 border-l bg-background" aria-labelledby="face-gallery-title">
    <div class="p-3 sm:p-5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p id="face-gallery-title" class="font-mono text-xs font-semibold uppercase text-secondary">
          Page faces
        </p>
        <ToggleGroup
          type="single"
          variant="outline"
          size="xs"
          :model-value="faceFilter"
          aria-label="Choose which page faces to show"
          @update:model-value="updateFaceFilter"
        >
          <ToggleGroupItem
            v-for="option in faceFilterOptions"
            :key="option.value"
            :value="option.value"
            class="px-2"
            :aria-label="`Show ${option.label.toLocaleLowerCase()} faces`"
          >
            <span>{{ option.label }}</span>
            <span class="font-mono opacity-70">{{ faceFilterCount(option.value) }}</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <ScrollArea type="always" orientation="horizontal" class="mt-4 w-full">
        <div ref="thumbnailList" class="flex min-h-22 w-max items-start gap-3 px-1 pb-5 pt-1">
          <UiTooltip v-for="(face, index) in visibleFaces" :key="face.id" :text="linkTooltip(face)">
          <button
            :key="face.id"
            type="button"
            class="group relative size-16 shrink-0 rounded-md border-2 bg-muted outline-none transition-[border-color,box-shadow] hover:border-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:size-18"
            :class="
              face.id === props.selectedFaceId
                ? 'border-secondary ring-2 ring-secondary ring-offset-2'
                : 'border-border'
            "
            :aria-label="`Select face ${index + 1}: ${face.status === 'assigned' ? `${face.name}, annotated` : 'not annotated'}, ${linkTooltip(face)}`"
            :aria-pressed="face.id === props.selectedFaceId"
            :aria-current="face.id === props.selectedFaceId ? 'true' : undefined"
            @click="emit('select', face.id)"
          >
            <LoadableImage
              :src="face.portrait"
              :loading="face.portraitLoading"
              :alt="face.status === 'assigned' ? face.name : 'Unassigned face'"
              class="size-full rounded-[calc(var(--radius-md)-2px)]"
              image-class="size-full object-cover grayscale transition-transform duration-200 group-hover:scale-105"
            />
            <EntityLinkStateBadge v-bind="face" :focusable="false" compact class="absolute -right-1.5 -bottom-1.5 shadow-sm" />
          </button>
          </UiTooltip>
          <p
            v-if="!props.loading && visibleFaces.length === 0"
            class="flex h-16 items-center pr-4 text-sm text-muted-foreground sm:h-18"
            role="status"
          >
            {{ emptyFilterLabel(faceFilter) }}
            <button class="ml-2 underline" @click="faceFilter = 'all'; emit('reset-filters')">Reset filters</button>
          </p>
          <div
            v-if="props.loading"
            class="size-16 shrink-0 animate-pulse rounded-md border bg-muted sm:size-18"
            aria-label="Loading faces"
          ></div>
        </div>
      </ScrollArea>
    </div>
  </aside>
</template>
