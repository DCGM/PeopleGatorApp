<script setup lang="ts">
import { Link, UserRoundX } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { computed, nextTick, ref, watch, type Component } from 'vue'

import type { Face, FaceStatus } from '@/viewmodels/document-workspace.types'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  faces: Face[]
  selectedFaceId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
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
const faceStatusIcons = {
  assigned: Link,
  unassigned: UserRoundX,
} satisfies Record<FaceStatus, Component>
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
    selected?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest', inline: 'center' })
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
          <button
            v-for="(face, index) in visibleFaces"
            :key="face.id"
            type="button"
            class="group relative size-16 shrink-0 rounded-md border-2 bg-muted outline-none transition-[border-color,box-shadow] hover:border-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:size-18"
            :class="
              face.id === props.selectedFaceId
                ? 'border-secondary ring-2 ring-secondary ring-offset-2'
                : 'border-border'
            "
            :aria-label="`Select face ${index + 1}: ${face.status === 'assigned' ? `${face.name}, annotated` : 'not annotated'}`"
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
            <Badge
              data-face-status-badge
              class="pointer-events-none absolute -left-1.5 -top-1.5 size-5 rounded-full border-0 p-0 shadow-sm"
              :class="
                face.status === 'assigned'
                  ? 'bg-emerald-700 text-white'
                  : 'bg-muted-foreground text-background'
              "
              :title="face.status === 'assigned' ? 'Annotated' : 'Not annotated'"
              aria-hidden="true"
            >
              <component :is="faceStatusIcons[face.status]" class="size-3" />
            </Badge>
          </button>
          <p
            v-if="!props.loading && visibleFaces.length === 0"
            class="flex h-16 items-center pr-4 text-sm text-muted-foreground sm:h-18"
            role="status"
          >
            {{ emptyFilterLabel(faceFilter) }}
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
