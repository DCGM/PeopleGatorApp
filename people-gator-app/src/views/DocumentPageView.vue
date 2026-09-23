<script setup lang="ts">
import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import { useDebounce } from '@vueuse/core'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DocumentControls from '@/components/custom/DocumentControls.vue'
import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import FaceGallery from '@/components/custom/FaceGallery.vue'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import SimilarPeoplePanel from '@/components/custom/SimilarPeoplePanel.vue'
import { topBarContextKey } from '@/components/custom/top-bar-context'
import type {
  PageViewportBounds,
  TranscriptionEntitySpan,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import type { Language } from '@/client'
import { useDocumentWorkspace } from '@/viewmodels/document-workspace'
import { useTranslationQuery } from '@/query/translation'

const minimumZoomPercent = 55
const maximumZoomPercent = 350
const controlledZoomStep = 0.24
const touchZoomStep = 0.45
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
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  loadMore,
  pageDimensions,
  pageImageLoading,
  pageImageUrl,
  similarPeople,
  similarPeopleLoading,
  transcription,
  unassignFace,
} = useDocumentWorkspace(libraryId, documentId, pageId, selectedFaceId, debouncedCandidateTerm)

const selectedLineIndex = ref(0)
const isTranslationOpen = ref(false)
const showBadgeNames = ref(true)
const selectedLanguage = ref<Language>('en')
const zoomPercent = ref(82)
const selectedEntityKey = ref<string | null>(null)
const viewerElement = ref<HTMLElement | null>(null)
const zoomElement = ref<HTMLElement | null>(null)
const pageElement = ref<HTMLElement | null>(null)
const pageBounds = ref<PageViewportBounds | null>(null)
let panzoom: PanzoomObject | undefined
let pageResizeObserver: ResizeObserver | undefined

const selectedFace = computed(() => faces.value.find((face) => face.id === selectedFaceId.value))
const selectedPersonCandidate = computed(() =>
  similarPeople.value.find((person) => person.id === selectedPersonId.value),
)
const selectedFaceIndex = computed(() =>
  faces.value.findIndex((face) => face.id === selectedFaceId.value),
)
const translationOptions = computed<readonly ('off' | Language)[]>(() => [
  'off',
  'cs',
  'en',
  'de',
])
const selectedLineText = computed(() => transcription.value[selectedLineIndex.value]?.text ?? '')
const translationQuery = useTranslationQuery(
  selectedLineText,
  selectedLanguage,
  computed(() => isTranslationOpen.value),
)
const currentTranslation = computed(() => translationQuery.data.value?.translation ?? '')
const translationLoading = computed(() => translationQuery.isFetching.value)

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
      translate: isTranslationOpen.value ? 'on' : 'off',
    },
  })
}

function selectFace(faceId: string) {
  selectedFaceId.value = faceId
  selectedPersonId.value = faces.value.find((face) => face.id === faceId)?.personId ?? null
  syncRoute()
}

function unassignSelectedFace() {
  if (!selectedFace.value?.personId) return
  unassignFace(selectedFace.value.id)
  selectedPersonId.value = null
  syncRoute()
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

function selectTranslation(language: Language | 'off') {
  isTranslationOpen.value = language !== 'off'
  if (language !== 'off') selectedLanguage.value = language
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
  const entity = await createAndAssign(selectedFace.value.id, person.name, person.shortDescription)
  selectedPersonId.value = entity.entity_id
  syncRoute()
}

function setZoom(direction: 'in' | 'out') {
  if (!panzoom) return
  if (direction === 'in' && zoomPercent.value < maximumZoomPercent)
    panzoom.zoomIn({ animate: false, step: controlledZoomStep })
  if (direction === 'out' && zoomPercent.value > minimumZoomPercent)
    panzoom.zoomOut({ animate: false, step: controlledZoomStep })
}
function resetView() {
  panzoom?.reset({ animate: false })
}

function handleWheel(event: WheelEvent) {
  panzoom?.zoomWithWheel(event, { step: controlledZoomStep })
}

function updatePageBounds() {
  const viewer = viewerElement.value
  const page = pageElement.value
  if (!viewer || !page) return

  const viewerRect = viewer.getBoundingClientRect()
  const pageRect = page.getBoundingClientRect()
  pageBounds.value = {
    left: pageRect.left - viewerRect.left,
    top: pageRect.top - viewerRect.top,
    width: pageRect.width,
    height: pageRect.height,
  }
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
  () => route.query.translate,
  (translate) => {
    isTranslationOpen.value = translate === 'on'
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

onMounted(async () => {
  window.addEventListener('keydown', handleNavigationKeydown)
  await nextTick()
  if (!zoomElement.value) return
  panzoom = Panzoom(zoomElement.value, {
    canvas: true,
    maxScale: maximumZoomPercent / 100,
    minScale: minimumZoomPercent / 100,
    startScale: 0.82,
    step: touchZoomStep,
  })
  viewerElement.value?.addEventListener('wheel', handleWheel, { passive: false })
  zoomElement.value.addEventListener('panzoomchange', ((event: CustomEvent<{ scale: number }>) => {
    zoomPercent.value = Math.round(event.detail.scale * 100)
    updatePageBounds()
  }) as EventListener)
  window.addEventListener('resize', updatePageBounds)
  if (typeof ResizeObserver !== 'undefined' && viewerElement.value && pageElement.value) {
    pageResizeObserver = new ResizeObserver(updatePageBounds)
    pageResizeObserver.observe(viewerElement.value)
    pageResizeObserver.observe(pageElement.value)
  }
  updatePageBounds()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleNavigationKeydown)
  window.removeEventListener('resize', updatePageBounds)
  viewerElement.value?.removeEventListener('wheel', handleWheel)
  pageResizeObserver?.disconnect()
  panzoom?.destroy()
})
</script>

<template>
  <Teleport v-if="topBarContext" :to="topBarContext">
    <DocumentControls
      :selected-line-index="selectedLineIndex"
      :line-count="transcription.length"
      :selected-face-index="selectedFaceIndex"
      :face-count="faces.length"
      :zoom-percent="zoomPercent"
      :minimum-zoom-percent="minimumZoomPercent"
      :maximum-zoom-percent="maximumZoomPercent"
      :translation-options="translationOptions"
      :is-translation-open="isTranslationOpen"
      :selected-language="selectedLanguage"
      :show-badge-names="showBadgeNames"
      @previous-line="previousLine"
      @next-line="nextLine"
      @previous-face="previousFace"
      @next-face="nextFace"
      @set-zoom="setZoom"
      @reset-view="resetView"
      @select-translation="selectTranslation"
      @toggle-badge-names="showBadgeNames = !showBadgeNames"
    />
  </Teleport>

  <main class="workspace-grid">
    <div class="workspace-fold">
      <section
        class="workspace-teleprompter relative min-h-0 min-w-0 overflow-hidden border-b bg-background"
        aria-labelledby="page-transcription-title"
      >
        <DocumentTeleprompter
          class="absolute inset-y-0 left-3 right-3 sm:left-6 sm:right-6"
          :transcription="transcription"
          :selected-line-index="selectedLineIndex"
          :selected-entity-key="selectedEntityKey"
          :related-entity-key="selectedPersonCandidate?.entityKey ?? null"
          :is-translation-open="isTranslationOpen"
          :selected-language="selectedLanguage"
          :current-translation="currentTranslation"
          :translation-loading="translationLoading"
          @select-line="selectLine"
          @select-entity="selectEntity"
          @navigate-line="navigateLine"
        />
      </section>

      <section
        ref="viewerElement"
        class="workspace-viewer bg-viewer relative min-h-0 overflow-hidden"
        aria-label="Pan and zoom document page"
      >
        <div
          ref="zoomElement"
          class="panzoom-layer flex size-full min-h-full min-w-full items-center justify-center"
        >
          <div
            ref="pageElement"
            class="scan-page relative w-135 shrink-0 overflow-hidden bg-card shadow-2xl"
            :style="{ aspectRatio: `${pageDimensions.width} / ${pageDimensions.height}` }"
          >
            <LoadableImage
              :src="pageImageUrl"
              :loading="pageImageLoading"
              :alt="`Scan ${pageId}`"
              class="absolute inset-0 size-full"
              image-class="object-contain"
            >
              <template #fallback>
                <div class="flex size-full items-center justify-center text-muted-foreground">
                  <span v-if="error">Could not load scan</span><span v-else>Loading scan…</span>
                </div>
              </template>
            </LoadableImage>
          </div>
        </div>
        <DocumentPageOverlay
          :page-bounds="pageBounds"
          :transcription="transcription"
          :faces="faces"
          :selected-line-index="selectedLineIndex"
          :selected-face-id="selectedFace?.id ?? null"
          :selected-person-id="selectedPersonId"
          :selected-candidate-face-id="selectedPersonCandidate?.faceId ?? null"
          :show-badge-names="showBadgeNames"
          @select-line="selectLine"
          @select-face="selectFace"
        />
      </section>

      <FaceGallery
        class="workspace-selection"
        :faces="faces"
        :selected-face-id="selectedFace?.id ?? null"
        :loading="isLoading"
        @select="selectFace"
      />
    </div>

    <SimilarPeoplePanel
      v-model:search-term="candidateTerm"
      class="workspace-similar border-l"
      :people="candidateTerm.trim() === debouncedCandidateTerm.trim() ? similarPeople : []"
      :loading="
        isLoading || similarPeopleLoading || candidateTerm.trim() !== debouncedCandidateTerm.trim()
      "
      :has-next-page="hasNextPage"
      :is-fetching-next-page="isFetchingNextPage"
      :selected-face="selectedFace ?? null"
      :viewed-person-id="selectedPersonId"
      :assignment-pending="assignmentStatus === 'pending'"
      @load-more="loadMore()"
      @preview="previewSimilarPerson"
      @assign="assignSimilarPerson"
      @create="createSimilarPerson"
      @unassign="unassignSelectedFace"
    />
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
    linear-gradient(
      color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px,
      transparent 1px
    ),
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px,
      transparent 1px
    );
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
    grid-template-rows: auto minmax(0, 1fr);
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

  .workspace-teleprompter {
    grid-column: 1;
    grid-row: 1;
    height: auto;
  }

  .workspace-similar {
    grid-column: 2;
    grid-row: 2;
    overflow: hidden;
  }
}

@media (min-width: 1536px) {
  .workspace-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) 25rem;
    grid-template-rows: auto minmax(0, 1fr) auto;
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
    grid-row: 2 / 4;
  }
}
</style>
