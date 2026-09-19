<script setup lang="ts">
import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import { ChevronRight, Link, ListFilter, ScanFace, UserRoundX, X } from '@lucide/vue'
import { useDebounce } from '@vueuse/core'
import {
  computed,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Component,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DocumentControls from '@/components/custom/DocumentControls.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import FaceItem from '@/components/custom/FaceItem.vue'
import FaceItemSkeleton from '@/components/custom/FaceItemSkeleton.vue'
import FaceListEmptyState from '@/components/custom/FaceListEmptyState.vue'
import SimilarPeoplePanel from '@/components/custom/SimilarPeoplePanel.vue'
import { topBarContextKey } from '@/components/custom/top-bar-context'
import type { FaceStatus, TranscriptionEntitySpan } from '@/components/custom/document-page.types'
import { transcriptionEntityKey } from '@/components/custom/document-page.types'
import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useDocumentWorkspace } from '@/query/document-workspace'

const minimumZoomPercent = 55
const maximumZoomPercent = 350
const faceStatuses = ['assigned', 'unassigned'] as const
const faceStatusLabels = {
  assigned: 'Assigned',
  unassigned: 'Unassigned',
} satisfies Record<FaceStatus, string>
const faceStatusClasses = {
  assigned: 'text-emerald-700',
  unassigned: 'text-muted-foreground',
} satisfies Record<FaceStatus, string>
const faceStatusIcons = {
  assigned: Link,
  unassigned: UserRoundX,
} satisfies Record<FaceStatus, Component>

const route = useRoute()
const router = useRouter()
const topBarContext = inject(topBarContextKey)
const libraryId = computed(() => String(route.params.libraryId))
const documentId = computed(() => String(route.params.documentId))
const pageId = computed(() => String(route.params.pageId))
const selectedFaceId = ref<string | null>(
  typeof route.query.person === 'string' ? route.query.person : null,
)
const selectedPersonId = ref<string | null>(
  typeof route.query.selectedPerson === 'string' ? route.query.selectedPerson : null,
)
const candidateTerm = ref('')
const debouncedCandidateTerm = useDebounce(candidateTerm, 250)
const {
  assignFace,
  assignmentStatus,
  createAndAssign,
  error,
  faces,
  isLoading,
  pageDimensions,
  pageImageUrl,
  similarPeople,
  similarPeopleLoading,
  transcription,
} = useDocumentWorkspace(libraryId, documentId, pageId, selectedFaceId, debouncedCandidateTerm)

const selectedLineIndex = ref(0)
const zoomPercent = ref(82)
const selectedFaceStatus = ref<'all' | FaceStatus>('all')
const selectedEntityKey = ref<string | null>(null)
const viewerElement = ref<HTMLElement | null>(null)
const zoomElement = ref<HTMLElement | null>(null)
const faceListElement = ref<HTMLElement | null>(null)
let panzoom: PanzoomObject | undefined

const selectedFace = computed(() => faces.value.find((face) => face.id === selectedFaceId.value))
const selectedPersonCandidate = computed(() =>
  similarPeople.value.find((person) => person.id === selectedPersonId.value),
)
const selectedFaceIndex = computed(() =>
  faces.value.findIndex((face) => face.id === selectedFaceId.value),
)
const faceStatusFilter = computed<'all' | FaceStatus>({
  get: () => selectedFaceStatus.value,
  set: (status) => {
    selectedFaceStatus.value = status ?? 'all'
  },
})
const visibleFaces = computed(() =>
  faceStatusFilter.value === 'all'
    ? faces.value
    : faces.value.filter((face) => face.status === faceStatusFilter.value),
)
const faceStatusCounts = computed<Record<FaceStatus, number>>(() => {
  const counts: Record<FaceStatus, number> = { assigned: 0, unassigned: 0 }
  for (const face of faces.value) counts[face.status] += 1
  return counts
})

function routeLineIndex(value: unknown) {
  if (typeof value !== 'string') return 0
  const idIndex = transcription.value.findIndex((line) => line.id === value)
  const numericIndex = Number(value)
  if (idIndex >= 0) return idIndex
  if (Number.isFinite(numericIndex)) {
    return Math.min(transcription.value.length - 1, Math.max(0, numericIndex))
  }
  return 0
}

function syncRoute() {
  const line = transcription.value[selectedLineIndex.value]
  void router.replace({
    query: {
      person: selectedFaceId.value ?? undefined,
      selectedPerson: selectedPersonId.value ?? undefined,
      line: line?.id,
    },
  })
}

function selectFace(faceId: string) {
  selectedFaceId.value = faceId
  selectedPersonId.value = faces.value.find((face) => face.id === faceId)?.personId ?? null
  syncRoute()
}

function clearFaceSelection() {
  selectedFaceId.value = null
  selectedPersonId.value = null
  syncRoute()
}

function scrollSelectedFaceIntoView() {
  void nextTick(() => {
    const faceList = faceListElement.value
    const viewport = faceList?.closest('[data-slot="scroll-area-viewport"]')
    const selected = Array.from(faceList?.children ?? []).find(
      (element) =>
        element instanceof HTMLElement && element.dataset.faceId === selectedFaceId.value,
    )
    if (!(viewport instanceof HTMLElement) || !(selected instanceof HTMLElement)) return
    const listBounds = viewport.getBoundingClientRect()
    const faceBounds = selected.getBoundingClientRect()
    const delta =
      faceBounds.left < listBounds.left
        ? faceBounds.left - listBounds.left
        : Math.max(0, faceBounds.right - listBounds.right)
    if (delta) viewport.scrollBy({ left: delta })
  })
}

function selectLine(index: number) {
  if (index < 0 || index >= transcription.value.length) return
  selectedLineIndex.value = index
  selectedEntityKey.value = null
  syncRoute()
}

function selectEntity(index: number, entity: TranscriptionEntitySpan) {
  selectedLineIndex.value = index
  selectedEntityKey.value = transcriptionEntityKey(entity)
  syncRoute()
}

function nextFace() {
  if (selectedFaceIndex.value >= faces.value.length - 1) return
  selectFace(faces.value[selectedFaceIndex.value + 1]!.id)
}

function previousFace() {
  if (selectedFaceIndex.value <= 0) return
  selectFace(faces.value[selectedFaceIndex.value - 1]!.id)
}

function nextLine() {
  selectLine(Math.min(selectedLineIndex.value + 1, transcription.value.length - 1))
}
function previousLine() {
  selectLine(Math.max(selectedLineIndex.value - 1, 0))
}
function navigateLine(direction: 'next' | 'previous') {
  if (direction === 'next') nextLine()
  else previousLine()
}

function previewSimilarPerson(person: SimilarPersonCandidate) {
  selectedPersonId.value = person.id
  if (person.entityLineIndex !== undefined) {
    selectedLineIndex.value = person.entityLineIndex
    selectedEntityKey.value = null
  }
  syncRoute()
}

function assignSimilarPerson(person: SimilarPersonCandidate) {
  if (!selectedFace.value) return
  assignFace(selectedFace.value.id, person.id)
  selectedPersonId.value = person.id
  syncRoute()
}

async function createSimilarPerson(person: SimilarPersonCandidate) {
  if (!selectedFace.value) return
  const entity = await createAndAssign(selectedFace.value.id, person.name)
  selectedPersonId.value = entity.entity_id
  syncRoute()
}

function setZoom(direction: 'in' | 'out') {
  if (!panzoom) return
  if (direction === 'in' && zoomPercent.value < maximumZoomPercent) panzoom.zoomIn()
  if (direction === 'out' && zoomPercent.value > minimumZoomPercent) panzoom.zoomOut()
}
function resetView() {
  panzoom?.reset({ animate: true })
}

function handleWheel(event: WheelEvent) {
  panzoom?.zoomWithWheel(event)
}

function handleNavigationKeydown(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (
    event.target instanceof HTMLElement &&
    (event.target.isContentEditable ||
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName))
  )
    return
  const navigate = {
    ArrowUp: previousLine,
    ArrowDown: nextLine,
    ArrowLeft: previousFace,
    ArrowRight: nextFace,
  }[event.key]
  if (!navigate) return
  event.preventDefault()
  navigate()
}

watch(
  transcription,
  () => {
    selectedLineIndex.value = routeLineIndex(route.query.line)
  },
  { immediate: true },
)
watch(
  () => route.query.person,
  (person) => {
    selectedFaceId.value = typeof person === 'string' ? person : null
  },
)
watch(
  () => route.query.selectedPerson,
  (person) => {
    selectedPersonId.value = typeof person === 'string' ? person : null
  },
)
watch(selectedFaceId, scrollSelectedFaceIntoView, { immediate: true })

onMounted(async () => {
  window.addEventListener('keydown', handleNavigationKeydown)
  await nextTick()
  if (!zoomElement.value) return
  panzoom = Panzoom(zoomElement.value, {
    canvas: true,
    maxScale: maximumZoomPercent / 100,
    minScale: minimumZoomPercent / 100,
    startScale: 0.82,
    step: 0.18,
  })
  viewerElement.value?.addEventListener('wheel', handleWheel, { passive: false })
  zoomElement.value.addEventListener('panzoomchange', ((event: CustomEvent<{ scale: number }>) => {
    zoomPercent.value = Math.round(event.detail.scale * 100)
  }) as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleNavigationKeydown)
  viewerElement.value?.removeEventListener('wheel', handleWheel)
  panzoom?.destroy()
})
</script>

<template>
  <Teleport v-if="topBarContext" :to="topBarContext">
    <DocumentControls :selected-line-index="selectedLineIndex" :line-count="transcription.length"
      :selected-face-index="selectedFaceIndex" :face-count="faces.length" :zoom-percent="zoomPercent"
      :minimum-zoom-percent="minimumZoomPercent" :maximum-zoom-percent="maximumZoomPercent"
      @previous-line="previousLine" @next-line="nextLine" @previous-face="previousFace" @next-face="nextFace"
      @set-zoom="setZoom" @reset-view="resetView" />
  </Teleport>

  <main class="workspace-grid">
    <div class="workspace-fold">
      <section class="workspace-teleprompter relative min-h-0 min-w-0 overflow-hidden border-b bg-background"
        aria-labelledby="page-transcription-title">
        <DocumentTeleprompter class="absolute inset-y-0 left-3 right-3 sm:left-6 sm:right-6"
          :transcription="transcription" :selected-line-index="selectedLineIndex"
          :selected-entity-key="selectedEntityKey" :related-entity-key="selectedPersonCandidate?.entityKey ?? null"
          @select-line="selectLine" @select-entity="selectEntity" @navigate-line="navigateLine" />
      </section>

      <section ref="viewerElement" class="workspace-viewer bg-viewer min-h-0 overflow-hidden"
        aria-label="Pan and zoom document page">
        <div ref="zoomElement" class="panzoom-layer flex size-full min-h-full min-w-full items-center justify-center">
          <div class="scan-page relative w-135 shrink-0 overflow-hidden bg-card shadow-2xl"
            :style="{ aspectRatio: `${pageDimensions.width} / ${pageDimensions.height}` }">
            <img v-if="pageImageUrl" :src="pageImageUrl" :alt="`Scan ${pageId}`"
              class="absolute inset-0 size-full object-contain" />
            <div v-else class="absolute inset-0 flex items-center justify-center text-muted-foreground">
              <span v-if="error">Could not load scan</span><span v-else>Loading scan…</span>
            </div>

            <button v-for="(line, index) in transcription" :key="line.id" type="button"
              class="absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              :class="index === selectedLineIndex
                  ? 'border-accent bg-accent/20 ring-1 ring-background/75'
                  : 'border-transparent hover:border-accent/70 hover:bg-accent/10'
                " :style="{
                left: `${line.position.left}%`,
                top: `${line.position.top}%`,
                width: `${line.position.width}%`,
                height: `${line.position.height}%`,
              }" :aria-label="`Select line ${index + 1}: ${line.text}`" :aria-pressed="index === selectedLineIndex"
              @click.stop="selectLine(index)" />

            <button v-for="face in faces" :key="face.id" type="button" class="absolute border-2 transition-colors"
              :class="face.id === selectedFace?.id
                  ? 'border-secondary bg-secondary/15 ring-2 ring-background/80'
                  : face.personId === selectedPersonId ||
                    face.id === selectedPersonCandidate?.faceId
                    ? 'border-accent bg-accent/25 ring-2 ring-accent/70'
                    : 'border-accent/60 bg-accent/5 hover:bg-accent/20'
                " :style="{
                left: `${face.position.left}%`,
                top: `${face.position.top}%`,
                width: `${face.position.width}%`,
                height: `${face.position.height}%`,
              }" :aria-label="`Select ${face.name}`" :aria-pressed="face.id === selectedFace?.id"
              @click.stop="selectFace(face.id)">
              <span class="absolute -left-0.5 -top-5 bg-foreground px-1.5 py-0.5 font-mono text-[8px] text-background">
                {{ face.id }}
              </span>
            </button>
          </div>
        </div>
      </section>

      <aside class="workspace-selection min-h-0 border-l bg-background" aria-labelledby="selected-person-title">
        <header class="min-h-48 p-5">
          <div v-if="selectedFace" class="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-4 gap-y-3">
            <div class="aspect-square size-24 overflow-hidden bg-muted">
              <img v-if="selectedFace.portrait" :src="selectedFace.portrait" :alt="selectedFace.name"
                class="size-full object-cover grayscale" />
            </div>
            <div class="min-w-0">
              <div class="flex items-start justify-between gap-2">
                <p id="selected-person-title" class="font-mono text-xs font-semibold uppercase text-secondary">
                  Current selection
                </p>
                <Button type="button" size="icon-sm" variant="ghost" aria-label="Clear face selection"
                  @click="clearFaceSelection">
                  <X />
                </Button>
              </div>
              <h3 class="text-lg">
                <RouterLink v-if="selectedFace.personId"
                  :to="{ name: 'person-detail', params: { personId: selectedFace.personId } }"
                  class="group flex max-w-full items-center gap-1 underline-offset-4 hover:underline">
                  <span class="truncate">{{ selectedFace.name }}</span>
                  <ChevronRight class="size-[1em]" />
                </RouterLink>
                <span v-else>{{ selectedFace.name }}</span>
              </h3>
              <code class="block truncate text-sm text-muted-foreground">{{
                selectedFace.id
              }}</code>
              <span class="mt-1 flex items-center gap-1 text-sm" :class="faceStatusClasses[selectedFace.status]">
                <component :is="faceStatusIcons[selectedFace.status]" class="size-4" />
                {{ faceStatusLabels[selectedFace.status] }} · {{ selectedFace.confidence }}%
              </span>
              <small v-if="assignmentStatus === 'pending'" class="text-muted-foreground">Saving…</small>
            </div>
          </div>
          <div v-else class="flex min-h-36 items-center gap-4" role="status">
            <div class="flex size-16 shrink-0 items-center justify-center border bg-muted">
              <ScanFace class="size-7 text-muted-foreground" />
            </div>
            <div>
              <p id="selected-person-title" class="font-mono text-xs font-semibold uppercase text-secondary">
                Current selection
              </p>
              <h3 class="mt-1 text-lg">No face selected</h3>
              <p class="mt-1 text-sm text-muted-foreground">
                Select a face on the page or from the list.
              </p>
            </div>
          </div>
        </header>
      </aside>
    </div>

    <SimilarPeoplePanel v-model:search-term="candidateTerm" class="workspace-similar border-l"
      :people="candidateTerm.trim() === debouncedCandidateTerm.trim() ? similarPeople : []" :loading="isLoading || similarPeopleLoading || candidateTerm.trim() !== debouncedCandidateTerm.trim()
        " :assigned-person-id="selectedFace?.personId ?? null" :viewed-person-id="selectedPersonId"
      @preview="previewSimilarPerson" @assign="assignSimilarPerson" @create="createSimilarPerson" />

    <section class="workspace-faces @container min-w-0 overflow-hidden border-t bg-background px-3 py-4 sm:px-6"
      aria-labelledby="page-faces-title">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <ToggleGroup v-model="faceStatusFilter" type="single" variant="outline" size="sm"
          aria-label="Filter faces by status" class="max-w-full overflow-x-auto">
          <ToggleGroupItem value="all" aria-label="Show all face statuses" class="px-2 py-0.5 text-xs">
            <ListFilter /><b>All faces</b><code>{{ faces.length }}</code>
          </ToggleGroupItem>
          <ToggleGroupItem v-for="status in faceStatuses" :key="status" :value="status"
            :aria-label="`Toggle ${faceStatusLabels[status]} faces`" class="px-2 py-0.5 text-xs"
            :class="faceStatusClasses[status]">
            <component :is="faceStatusIcons[status]" /><b>{{ faceStatusLabels[status] }}</b>
            <code>{{ faceStatusCounts[status] }}</code>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <ScrollArea type="always" orientation="horizontal" class="w-full">
        <div ref="faceListElement" class="flex w-max gap-2 pb-5">
          <FaceItem v-for="face in visibleFaces" :key="face.id" :face="face" :selected="face.id === selectedFace?.id"
            @select="selectFace" />
          <FaceItemSkeleton v-if="isLoading" />
          <FaceListEmptyState v-if="!isLoading && visibleFaces.length === 0" />
        </div>
      </ScrollArea>
    </section>
  </main>
</template>

<style scoped>
.workspace-grid {
  min-height: calc(100vh - 3.25rem);
}

.workspace-fold {
  display: grid;
  height: calc(100dvh - 3.25rem);
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.workspace-viewer {
  grid-column: 1;
  grid-row: 2;
}

.workspace-selection {
  grid-column: 1;
  grid-row: 3;
}

.workspace-teleprompter {
  grid-column: 1;
  grid-row: 1;
  height: clamp(8rem, 22dvh, 12rem);
}

.bg-viewer {
  background-color: var(--color-muted);
  background-image:
    linear-gradient(color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px,
      transparent 1px),
    linear-gradient(90deg,
      color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px,
      transparent 1px);
  background-size: 24px 24px;
}

.scan-page {
  user-select: none;
}

@media (min-width: 1024px) {
  .workspace-grid {
    display: grid;
    height: calc(100vh - 3.25rem);
    grid-template-columns: minmax(0, 1fr) 25rem;
    grid-template-rows: auto minmax(0, 1fr) auto;
  }

  .workspace-fold {
    display: contents;
  }

  .workspace-viewer {
    grid-column: 1;
    grid-row: 2;
  }

  .workspace-selection {
    grid-column: 2;
    grid-row: 1;
  }

  .workspace-faces {
    grid-column: 1;
    grid-row: 3;
  }

  .workspace-teleprompter {
    grid-column: 1;
    grid-row: 1;
    height: auto;
  }

  .workspace-similar {
    grid-column: 2;
    grid-row: 2 / 4;
    overflow: hidden;
  }
}

@media (min-width: 1536px) {
  .workspace-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) 25rem;
  }

  .workspace-viewer {
    grid-column: 1 / 3;
    grid-row: 1 / 3;
  }

  .workspace-selection {
    grid-column: 3;
  }

  .workspace-teleprompter {
    grid-column: 2;
    grid-row: 3;
    border-top-width: 1px;
    border-left-width: 1px;
    border-bottom-width: 0;
  }

  .workspace-similar {
    grid-column: 3;
  }
}
</style>
