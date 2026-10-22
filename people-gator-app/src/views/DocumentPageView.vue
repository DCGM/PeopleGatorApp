<script setup lang="ts">
import SharedFilterTags from '@/components/custom/SharedFilterTags.vue'
import PageActivityPanel from '@/components/custom/PageActivityPanel.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSharedFilters, hasSharedFilters, legacyFilterNotice } from '@/viewmodels/shared-filters'
import { focusTransform, MINIMUM_ZOOM, MAXIMUM_ZOOM } from '@/viewmodels/document-focus'
import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import { useDebounce } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import VerifyEntityLink from '@/components/custom/VerifyEntityLink.vue'
import PageStatisticsPanel from '@/components/custom/PageStatisticsPanel.vue'
import { useDocumentLookupQuery } from '@/query/media'
import DocumentControls from '@/components/custom/DocumentControls.vue'
import DocumentPageGallery from '@/components/custom/DocumentPageGallery.vue'
import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import CurrentFacePanel from '@/components/custom/CurrentFacePanel.vue'
import FaceGallery from '@/components/custom/FaceGallery.vue'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import SimilarPeopleResults from '@/components/custom/SimilarPeopleResults.vue'
import SimilarPeopleSearch from '@/components/custom/SimilarPeopleSearch.vue'
import type {
  PageViewportBounds,
  TranscriptionEntitySpan,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import type { CandidateBrowseMode } from '@/viewmodels/similar-people'
import type { Language } from '@/client'
import { useDocumentWorkspace } from '@/viewmodels/document-workspace'
import { useRouteSort } from '@/lib/sorting'
import {
  CANDIDATE_SORT_KEYS,
  FACE_DEFAULT,
  FACE_SORT_KEYS,
  GALLERY_DEFAULT,
  GALLERY_SORT_KEYS,
  GALLERY_SORTS,
  PEOPLE_BROWSE_DEFAULT,
  PEOPLE_SORTS,
  RELEVANCE,
  WORKSPACE_FACE_SORTS,
  scoredOptions,
} from '@/viewmodels/sort-options'
import {
  PAGE_GALLERY_BATCH_SIZE,
  pageGalleryQuery,
  useDocumentPageGallery,
  type PageGalleryItem,
} from '@/viewmodels/document-page-gallery'
import { useTranslationQuery } from '@/query/translation'

const minimumZoomPercent = MINIMUM_ZOOM * 100
const maximumZoomPercent = MAXIMUM_ZOOM * 100
const controlledZoomStep = 0.24
const touchZoomStep = 0.45
const route = useRoute()
const router = useRouter()
const evidence = useSharedFilters()
const libraryId = computed(() => String(route.params.libraryId))
const documentId = computed(() => String(route.params.documentId))
const linkStates = useLinkStateFilter()
const documentQuery = useDocumentLookupQuery(libraryId, documentId)
const pageId = computed(() => String(route.params.pageId))
const selectedFaceId = ref<string | null>(
  typeof route.query.person === 'string' ? route.query.person : null,
)
const selectedPersonId = ref<string | null>(
  typeof route.query.selectedPerson === 'string' ? route.query.selectedPerson : null,
)
const candidateTerm = ref(
  typeof route.query.candidate_text === 'string' ? route.query.candidate_text : '',
)
const candidateBrowseMode = ref<CandidateBrowseMode>(
  route.query.candidate_mode === 'face' ? 'face' : 'page',
)
const candidateSearchResetKey = ref(0)
const debouncedCandidateTerm = useDebounce(candidateTerm, 250)
// Faces, gallery pages and candidates keep independent, shareable orders.
const faceSort = useRouteSort(FACE_SORT_KEYS, WORKSPACE_FACE_SORTS, FACE_DEFAULT)
const gallerySort = useRouteSort(GALLERY_SORT_KEYS, GALLERY_SORTS, GALLERY_DEFAULT)
const candidateScored = computed(
  () => Boolean(debouncedCandidateTerm.value.trim()) || candidateBrowseMode.value === 'face',
)
const candidateSortOptions = computed(() => scoredOptions(PEOPLE_SORTS, candidateScored.value))
const candidateSort = useRouteSort(CANDIDATE_SORT_KEYS, candidateSortOptions, () =>
  candidateScored.value ? RELEVANCE : PEOPLE_BROWSE_DEFAULT,
)
const {
  page,
  annotationsLoading,
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
  pageImageError,
  pageImageLoaded,
  pageImageReady,
  pageImageUrl,
  similarPeople,
  similarPeopleLoading,
  transcription,
  unassignFace,
} = useDocumentWorkspace(
  libraryId,
  documentId,
  pageId,
  selectedFaceId,
  debouncedCandidateTerm,
  candidateBrowseMode,
  linkStates,
  evidence.params,
  computed(() => !evidence.error.value),
  faceSort,
  candidateSort,
)

const gallery = useDocumentPageGallery(
  libraryId,
  documentId,
  pageId,
  PAGE_GALLERY_BATCH_SIZE,
  gallerySort,
)
function galleryLocation(item: PageGalleryItem) {
  return {
    name: 'document-page',
    params: { libraryId: item.library, documentId: item.documentId, pageId: item.pageId },
    query: pageGalleryQuery(route.query),
  }
}

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
const similarPeopleSearch = ref<InstanceType<typeof SimilarPeopleSearch> | null>(null)
let panzoom: PanzoomObject | undefined
let pageResizeObserver: ResizeObserver | undefined
const focusPageKey = computed(() => `${libraryId.value}/${documentId.value}/${pageId.value}`)
type FocusTarget = { kind: 'face'; id: string } | { kind: 'line'; id: string; entityKey?: string }
let focusFrame: number | undefined
const pendingFocus = ref<{ page: string; target: FocusTarget } | null>(null)

function scheduleFocus() {
  void nextTick(() => {
    if (!pendingFocus.value) return
    if (focusFrame !== undefined) cancelAnimationFrame(focusFrame)
    // Panzoom writes transforms on animation frames. Measure after those writes,
    // including when keyboard navigation requests another target in quick succession.
    focusFrame = requestAnimationFrame(() => {
      focusFrame = undefined
      applyPendingFocus()
    })
  })
}

function requestFocus(target: FocusTarget) {
  pendingFocus.value = { page: focusPageKey.value, target }
  scheduleFocus()
}

function applyPendingFocus() {
  const request = pendingFocus.value
  const viewer = viewerElement.value
  const pageNode = pageElement.value
  if (!request || !panzoom || !viewer || !pageNode || !pageImageReady.value || annotationsLoading.value) return
  if (request.page !== focusPageKey.value) { pendingFocus.value = null; return }
  if (page.value?.page_id !== pageId.value) return
  const target = request.target
  const position = target.kind === 'face'
    ? (selectedFaceId.value === target.id ? faces.value.find(face => face.id === target.id)?.position : undefined)
    : transcription.value.find((line, index) => index === selectedLineIndex.value && line.id === target.id &&
        (!target.entityKey || (selectedEntityKey.value === target.entityKey &&
          line.entities?.some(entity => transcriptionEntityKey(entity) === target.entityKey))))?.position
  if (!position) { pendingFocus.value = null; return }
  const viewerRect = viewer.getBoundingClientRect()
  const pageRect = pageNode.getBoundingClientRect()
  const toolbar = viewer.querySelector('.viewer-tools')?.getBoundingClientRect()
  const transform = focusTransform(position, {
    left: pageRect.left - viewerRect.left, top: pageRect.top - viewerRect.top,
    width: pageRect.width, height: pageRect.height,
  }, { width: viewerRect.width, height: viewerRect.height,
    toolbarBottom: toolbar ? toolbar.bottom - viewerRect.top : 0 },
  { scale: panzoom.getScale(), ...panzoom.getPan() })
  if (!transform) return
  pendingFocus.value = null
  panzoom.zoom(transform.scale, { animate: false })
  panzoom.pan(transform.x, transform.y, { animate: false, force: true })
}

watch(focusPageKey, () => { pendingFocus.value = null }, { flush: 'sync' })
// Another page reuses this view: discard the previous page's selections and viewport.
watch(pageId, () => {
  selectedEntityKey.value = null
  selectedLineIndex.value = 0
  panzoom?.reset({ animate: false })
})
watch([pageImageReady, faces, transcription, annotationsLoading], () => {
  scheduleFocus()
})

const selectedFace = computed(() => faces.value.find((face) => face.id === selectedFaceId.value))
const selectedPersonCandidate = computed(() =>
  similarPeople.value.find((person) => person.id === selectedPersonId.value),
)
const selectedFaceIndex = computed(() =>
  faces.value.findIndex((face) => face.id === selectedFaceId.value),
)
const translationOptions = computed<readonly ('off' | Language)[]>(() => ['off', 'cs', 'en', 'de'])
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
    hash: route.hash,
    query: {
      ...route.query,
      candidate_text: candidateTerm.value || undefined,
      candidate_mode: candidateBrowseMode.value,
      person: selectedFaceId.value ?? undefined,
      selectedPerson: selectedPersonId.value ?? undefined,
      line: line?.id,
      translate: isTranslationOpen.value ? 'on' : 'off',
    },
  })
}

watch(
  () => [route.query.candidate_text, route.query.candidate_mode],
  () => {
    candidateTerm.value =
      typeof route.query.candidate_text === 'string' ? route.query.candidate_text : ''
    candidateBrowseMode.value = route.query.candidate_mode === 'face' ? 'face' : 'page'
  },
)

watch([candidateTerm, candidateBrowseMode], syncRoute)

function showOnPageEntities() {
  candidateTerm.value = ''
  candidateBrowseMode.value = 'page'
  candidateSearchResetKey.value += 1
}

function selectFace(faceId: string) {
  requestFocus({ kind: 'face', id: faceId })
  selectedFaceId.value = faceId
  selectedPersonId.value = faces.value.find((face) => face.id === faceId)?.personId ?? null
  if (selectedPersonId.value) showOnPageEntities()
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
  requestFocus({ kind: 'line', id: transcription.value[index]!.id })
  syncRoute()
}

function selectEntity(index: number, entity: TranscriptionEntitySpan) {
  selectedLineIndex.value = index
  selectedEntityKey.value = transcriptionEntityKey(entity)
  requestFocus({ kind: 'line', id: entity.line_id, entityKey: transcriptionEntityKey(entity) })
  selectedPersonId.value = entity.entity_id ?? null
  if (selectedPersonId.value) showOnPageEntities()
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
  pendingFocus.value = null
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

async function createSimilarPerson(person: { name: string; shortDescription?: string }) {
  if (!selectedFace.value) return
  const entity = await createAndAssign(selectedFace.value.id, person.name, person.shortDescription)
  selectedPersonId.value = entity.entity_id
  syncRoute()
}

function focusSimilarPeopleSearch() {
  similarPeopleSearch.value?.focus()
}

function setZoom(direction: 'in' | 'out') {
  if (!panzoom) return
  if (direction === 'in' && zoomPercent.value < maximumZoomPercent)
    panzoom.zoomIn({ animate: false, step: controlledZoomStep })
  if (direction === 'out' && zoomPercent.value > minimumZoomPercent)
    panzoom.zoomOut({ animate: false, step: controlledZoomStep })
}
function resetView() {
  pendingFocus.value = null
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
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey)
    return
  if (
    event.target instanceof HTMLElement &&
    (event.target.isContentEditable ||
      event.target.closest('input, select, textarea, button, a, [role=tablist]'))
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

watch([faces, transcription, annotationsLoading], () => {
  if (annotationsLoading.value) return
  let changed = false
  if (selectedFaceId.value && !faces.value.some((face) => face.id === selectedFaceId.value)) {
    selectedFaceId.value = null
    selectedPersonId.value = null
    changed = true
  }
  if (
    selectedEntityKey.value &&
    !transcription.value.some((line) =>
      line.entities?.some((span) => transcriptionEntityKey(span) === selectedEntityKey.value),
    )
  ) {
    selectedEntityKey.value = null
    selectedPersonId.value = null
    changed = true
  }
  if (changed) syncRoute()
})

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
    pageResizeObserver = new ResizeObserver(() => { updatePageBounds(); scheduleFocus() })
    pageResizeObserver.observe(viewerElement.value)
    pageResizeObserver.observe(pageElement.value)
  }
  updatePageBounds()
  if (selectedFaceId.value) requestFocus({ kind: 'face', id: selectedFaceId.value })
  scheduleFocus()
})

onBeforeUnmount(() => {
  if (focusFrame !== undefined) cancelAnimationFrame(focusFrame)
  pendingFocus.value = null
  window.removeEventListener('keydown', handleNavigationKeydown)
  window.removeEventListener('resize', updatePageBounds)
  viewerElement.value?.removeEventListener('wheel', handleWheel)
  pageResizeObserver?.disconnect()
  panzoom?.destroy()
})
</script>

<template>
  <main class="workspace-grid">
    <section
      class="workspace-teleprompter relative min-h-0 min-w-0 overflow-hidden border-b bg-background"
      aria-labelledby="page-transcription-title"
    >
      <DocumentTeleprompter
        class="absolute inset-y-0 left-3 right-3 sm:left-6 sm:right-6"
        :transcription="transcription"
        :selected-line-index="selectedLineIndex"
        :selected-entity-key="selectedEntityKey"
        :related-entity-id="selectedPersonId"
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
      <DocumentControls
        class="viewer-tools absolute inset-x-3 top-3 z-20 mx-auto w-fit max-w-[calc(100%-1.5rem)]"
        @pointerdown.stop
        @wheel.stop
        @keydown.stop
        v-model:link-states="linkStates"
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
            @load="pageImageLoaded"
          >
            <template #fallback>
              <div class="flex size-full items-center justify-center text-muted-foreground">
                <span v-if="error || pageImageError">Could not load scan</span><span v-else>Loading scan…</span>
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

    <DocumentPageGallery
      class="workspace-gallery border-t"
      :items="gallery.items.value"
      :total-count="gallery.totalCount.value"
      :loading="gallery.isLoading.value"
      :error="Boolean(gallery.error.value)"
      :has-next-page="gallery.hasNextPage.value"
      :is-fetching-next-page="gallery.isFetchingNextPage.value"
      :location="galleryLocation"
      v-model:sort="gallerySort"
      :sort-options="GALLERY_SORTS"
      @load-more="gallery.loadMore()"
      @retry="gallery.retry()"
    />

    <Tabs
      class="workspace-sidebar flex min-h-0 min-w-0 flex-col gap-0 overflow-hidden border-t bg-background"
      :model-value="
        route.query.panel === 'activity' || route.query.panel === 'statistics'
          ? route.query.panel
          : route.hash === '#link-statistics'
            ? 'statistics'
            : 'face'
      "
      @update:model-value="
        (value) =>
          router.push({
            query: { ...route.query, panel: value === 'face' ? undefined : value },
            hash: '',
          })
      "
    >
      <div class="shrink-0 border-b p-3">
        <TabsList aria-label="Page sidebar" class="w-full">
          <TabsTrigger value="face">Faces</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="statistics">Statistics</TabsTrigger>
        </TabsList>
      </div>
      <div
        v-if="hasSharedFilters(evidence.filters.value) || evidence.error.value || legacyFilterNotice.length"
        class="shrink-0 px-3 pb-3"
      >
        <SharedFilterTags />
      </div>
      <TabsContent value="face" class="mt-0 flex min-h-0 flex-col overflow-y-auto">
        <FaceGallery
          class="shrink-0 border-l-0"
          v-model:sort="faceSort"
          :sort-options="WORKSPACE_FACE_SORTS"
          :faces="faces"
          :selected-face-id="selectedFace?.id ?? null"
          :loading="isLoading"
          @reset-filters="linkStates = []"
          @select="selectFace"
        />

        <CurrentFacePanel
          class="p-5"
          :face="selectedFace ?? null"
          :assignment-pending="assignmentStatus === 'pending'"
          @find-profile="focusSimilarPeopleSearch"
          @create="createSimilarPerson"
          @unassign="unassignSelectedFace"
        >
          <VerifyEntityLink
            v-if="selectedFace"
            v-bind="selectedFace"
            :id="selectedFace.id"
            kind="face"
          />
        </CurrentFacePanel>
        <SimilarPeopleSearch
          :key="candidateSearchResetKey"
          ref="similarPeopleSearch"
          v-model="candidateTerm"
          v-model:result-mode="candidateBrowseMode"
          v-model:sort="candidateSort"
          :sort-options="candidateSortOptions"
          class="shrink-0 px-5 pb-5"
          :selected-face="selectedFace ?? null"
        />
        <SimilarPeopleResults
          class="min-h-80 shrink-0 px-5 pb-5 lg:min-h-64 lg:flex-1"
          :people="candidateTerm.trim() === debouncedCandidateTerm.trim() ? similarPeople : []"
          :loading="
            isLoading ||
            similarPeopleLoading ||
            candidateTerm.trim() !== debouncedCandidateTerm.trim()
          "
          :has-next-page="hasNextPage"
          :is-fetching-next-page="isFetchingNextPage"
          :selected-face="selectedFace ?? null"
          :viewed-person-id="selectedPersonId"
          :assignment-pending="assignmentStatus === 'pending'"
          :search-term="`${candidateBrowseMode}:${candidateTerm}`"
          @load-more="loadMore()"
          @preview="previewSimilarPerson"
          @assign="assignSimilarPerson"
        />
      </TabsContent>
      <TabsContent value="activity" class="mt-0 min-h-0 overflow-y-auto">
        <PageActivityPanel v-if="page" :source-id="page.source_id" hide-filter-tags />
      </TabsContent>
      <TabsContent value="statistics" class="mt-0 min-h-0 overflow-y-auto">
        <PageStatisticsPanel
          :page="page"
          :document="documentQuery.data.value"
          :loading="documentQuery.isPending.value"
          :error="Boolean(documentQuery.error.value)"
          @retry="documentQuery.refetch()"
        />
      </TabsContent>
    </Tabs>
  </main>
</template>

<style scoped>
.workspace-grid {
  display: grid;
  min-height: calc(100vh - 3.25rem);
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto minmax(28rem, calc(78dvh - 14rem)) auto minmax(36rem, 85dvh);
}

.workspace-viewer {
  grid-column: 1;
  grid-row: 2;
}

.workspace-gallery {
  grid-column: 1;
  grid-row: 3;
}

.workspace-sidebar {
  grid-column: 1;
  grid-row: 4;
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
    height: calc(100vh - 3.25rem);
    grid-template-columns: minmax(0, 1fr) 25rem;
    grid-template-rows: auto minmax(0, 1fr) auto;
  }

  .workspace-viewer {
    grid-column: 1;
    grid-row: 2;
  }

  .workspace-gallery {
    grid-column: 1;
    grid-row: 3;
  }

  .workspace-teleprompter {
    grid-column: 1;
    grid-row: 1;
    height: auto;
  }

  .workspace-sidebar {
    grid-column: 2;
    grid-row: 1 / 4;
    border-left-width: 1px;
    border-top-width: 0;
  }
}

@media (min-width: 1536px) {
  .workspace-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) 25rem;
  }

  .workspace-viewer {
    grid-column: 2;
    grid-row: 1 / 3;
  }

  .workspace-gallery {
    grid-column: 2;
    grid-row: 3;
  }

  .workspace-sidebar {
    grid-column: 3;
  }

  .workspace-teleprompter {
    grid-column: 1;
    grid-row: 1 / 4;
    border-right-width: 1px;
    border-bottom-width: 0;
  }
}
</style>
