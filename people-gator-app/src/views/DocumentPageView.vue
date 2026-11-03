<script setup lang="ts">
import PageActivityPanel from '@/components/custom/PageActivityPanel.vue'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { focusTransform, MINIMUM_ZOOM, MAXIMUM_ZOOM } from '@/viewmodels/document-focus'
import { SCAN_ZOOM_STEP, useScanViewport } from '@/composables/scan-viewport'
import { useWorkspaceSplit, type WorkspacePanel } from '@/composables/workspace-split'
import { useDebounce, useMediaQuery } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import { Button } from '@/components/ui/button'
import { BadgeCheck } from '@lucide/vue'
import UiTooltip from '@/components/custom/UiTooltip.vue'
import FaceActionButtons from '@/components/custom/FaceActionButtons.vue'
import { useCanAnnotate, useCanDeleteDetection } from '@/composables/can-annotate'
import { useVerifyLinkMutation } from '@/query/entity-links'
import { useDeleteFaceMutation } from '@/query/faces'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog'
import type { Face } from '@/viewmodels/document-workspace.types'
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
import PagePosition from '@/components/custom/PagePosition.vue'
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
  useDocumentPageGallery,
  type PageGalleryItem,
} from '@/viewmodels/document-page-gallery'
import { useTranslationQuery } from '@/query/translation'
import {
  adjacentIncluded,
  nearestIncluded,
  parseHighlightStates,
  parseLineVisibility,
  useTeleprompterLines,
  type LineVisibility,
  type Passage,
} from '@/viewmodels/teleprompter'

const minimumZoomPercent = MINIMUM_ZOOM * 100
const maximumZoomPercent = MAXIMUM_ZOOM * 100
const route = useRoute()
// The transcription panel is always left of the scan on wide screens and above
// it on narrow ones; each layout remembers its own user-resized split.
const isWideWorkspace = useMediaQuery('(min-width: 1024px)')
const splitDirection = computed(() => (isWideWorkspace.value ? 'horizontal' : 'vertical'))
const transcriptionPanel = ref<WorkspacePanel | null>(null)
const workspaceSplit = useWorkspaceSplit(splitDirection, transcriptionPanel)
const router = useRouter()
const libraryId = computed(() => String(route.params.libraryId))
const documentId = computed(() => String(route.params.documentId))
const linkStates = useLinkStateFilter('page_link_state')
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
  referenceFace,
  assignFace,
  assignmentStatus,
  assignmentError,
  resetAssignment,
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
  entityNames,
  unassignFace,
} = useDocumentWorkspace(
  libraryId,
  documentId,
  pageId,
  selectedFaceId,
  debouncedCandidateTerm,
  candidateBrowseMode,
  linkStates,
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
const teleprompter = ref<InstanceType<typeof DocumentTeleprompter> | null>(null)
const focusPageKey = computed(() => `${libraryId.value}/${documentId.value}/${pageId.value}`)
const scanViewport = useScanViewport(
  viewerElement, zoomElement, pageElement, focusPageKey, pageBounds, zoomPercent, scheduleFocus,
)
const lineVisibility = ref<LineVisibility>(parseLineVisibility(route.query.lines))
const annotationHighlight = ref(parseHighlightStates(route.query.highlight))
// Annotation states narrow the Annotated and Person lines as well as highlights.
const teleprompterLines = useTeleprompterLines(
  transcription,
  lineVisibility,
  selectedPersonId,
  focusPageKey,
  annotationHighlight,
)
const includedLines = teleprompterLines.included
const routeLineMode = computed(() =>
  lineVisibility.value === 'custom' ? teleprompterLines.customBase.value : lineVisibility.value,
)
const visibleLineIndices = computed(() =>
  includedLines.value.flatMap((included, index) => (included ? [index] : [])),
)
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
  const panzoom = scanViewport.current()
  const viewer = viewerElement.value
  const pageNode = pageElement.value
  if (
    !request ||
    !panzoom ||
    !viewer ||
    !pageNode ||
    !pageImageReady.value ||
    annotationsLoading.value
  )
    return
  if (request.page !== focusPageKey.value) {
    pendingFocus.value = null
    return
  }
  if (page.value?.page_id !== pageId.value) return
  const target = request.target
  const position =
    target.kind === 'face'
      ? selectedFaceId.value === target.id
        ? faces.value.find((face) => face.id === target.id)?.position
        : undefined
      : transcription.value.find(
          (line, index) =>
            index === selectedLineIndex.value &&
            line.id === target.id &&
            (!target.entityKey ||
              (selectedEntityKey.value === target.entityKey &&
                line.entities?.some(
                  (entity) => transcriptionEntityKey(entity) === target.entityKey,
                ))),
        )?.position
  if (!position) {
    pendingFocus.value = null
    return
  }
  const viewerRect = viewer.getBoundingClientRect()
  const pageRect = pageNode.getBoundingClientRect()
  const toolbar = viewer.querySelector('.viewer-tools')?.getBoundingClientRect()
  const transform = focusTransform(
    position,
    {
      left: pageRect.left - viewerRect.left,
      top: pageRect.top - viewerRect.top,
      width: pageRect.width,
      height: pageRect.height,
    },
    {
      width: viewerRect.width,
      height: viewerRect.height,
      toolbarBottom: toolbar ? toolbar.bottom - viewerRect.top : 0,
    },
    { scale: panzoom.getScale(), ...panzoom.getPan() },
  )
  if (!transform) return
  pendingFocus.value = null
  panzoom.zoom(transform.scale, { animate: false })
  panzoom.pan(transform.x, transform.y, { animate: false, force: true })
}

watch(
  focusPageKey,
  () => {
    pendingFocus.value = null
  },
  { flush: 'sync' },
)
// Another page reuses this view: discard the previous page's selections and viewport.
watch(focusPageKey, () => {
  selectedEntityKey.value = null
  selectedLineIndex.value = 0
  scanViewport.reset()
})
watch([pageImageReady, faces, transcription, annotationsLoading], () => {
  scheduleFocus()
})

const selectedFace = computed(
  () => faces.value.find((face) => face.id === selectedFaceId.value) ?? referenceFace.value,
)
const canAnnotate = useCanAnnotate()
const canDelete = useCanDeleteDetection()
const verifyMutation = useVerifyLinkMutation()
const deleteMutation = useDeleteFaceMutation()
const deletionTarget = ref<Face | null>(null)
const creatingPerson = ref(false)
const actionBusy = computed(
  () =>
    creatingPerson.value ||
    assignmentStatus.value === 'pending' ||
    verifyMutation.isPending.value ||
    deleteMutation.isPending.value,
)
// Delete errors stay in the confirmation dialog, which remains open for a retry.
const actionError = computed(() =>
  verifyMutation.error.value
    ? 'Could not verify link.'
    : assignmentError.value
      ? 'Could not update link.'
      : '',
)
// Only a face drawn on this scan can be deleted from here, not an off-page reference.
const selectedFaceOnPage = computed(() =>
  faces.value.some((face) => face.id === selectedFace.value?.id),
)
watch(selectedFaceId, () => {
  if (!verifyMutation.isPending.value) verifyMutation.reset()
  if (assignmentStatus.value !== 'pending') resetAssignment()
})
function closeDeletion(open: boolean) {
  if (open || deleteMutation.isPending.value) return
  deletionTarget.value = null
  deleteMutation.reset()
}
function requestDeletion(face: Face | null) {
  if (!face || actionBusy.value) return
  deletionTarget.value = face
}
function verifyFace(face: Face) {
  if (actionBusy.value) return
  verifyMutation.mutate({ id: face.id, kind: 'face' })
}
async function deleteDetection() {
  const face = deletionTarget.value
  if (!face || actionBusy.value) return
  try {
    await deleteMutation.mutateAsync(face.id)
    clearFace()
    closeDeletion(false)
    viewerElement.value?.focus()
  } catch {
    // Keep the detection and confirmation available for retry.
  }
}

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
      // A Custom line set is not shareable; links keep the mode it came from.
      lines: routeLineMode.value === 'all' ? undefined : routeLineMode.value,
      highlight: annotationHighlight.value.length ? annotationHighlight.value : undefined,
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

function clearFace() {
  selectedFaceId.value = null
  selectedPersonId.value = null
  syncRoute()
}

function unassignSelectedFace() {
  if (!selectedFace.value?.personId || actionBusy.value) return
  unassignFace(selectedFace.value.id)
  selectedPersonId.value = null
  syncRoute()
}

function selectLine(index: number) {
  if (index < 0 || index >= transcription.value.length) return
  // An overlay click on a hidden line reveals it as local context.
  if (!includedLines.value[index]) teleprompterLines.reveal([index])
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

// Explicit line navigation follows the visible sequence in original order.
function nextLine() {
  const index = adjacentIncluded(includedLines.value, selectedLineIndex.value, 'next')
  if (index !== null) selectLine(index)
}
function previousLine() {
  const index = adjacentIncluded(includedLines.value, selectedLineIndex.value, 'previous')
  if (index !== null) selectLine(index)
}

function expandContext(passage: Passage, direction: 'before' | 'after', count: number) {
  teleprompterLines.expand(passage, direction, count)
}

watch([lineVisibility, () => annotationHighlight.value.join()], syncRoute)
// Mode changes, Reset and route restoration move a hidden selection to the
// nearest available line.
watch([includedLines, selectedLineIndex], ([included, index]) => {
  if (included[index]) return
  const nearest = nearestIncluded(included, index)
  if (nearest !== null) selectLine(nearest)
})

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
  if (!selectedFace.value || actionBusy.value) return
  assignFace(selectedFace.value.id, person.id)
  selectedPersonId.value = person.id
  syncRoute()
}

async function createSimilarPerson(person: { name: string; shortDescription?: string }) {
  if (!selectedFace.value || actionBusy.value) return
  creatingPerson.value = true
  try {
    const entity = await createAndAssign(
      selectedFace.value.id,
      person.name,
      person.shortDescription,
    )
    selectedPersonId.value = entity.entity_id
    syncRoute()
  } finally {
    creatingPerson.value = false
  }
}

async function focusSimilarPeopleSearch() {
  await router.replace({ query: { ...route.query, panel: undefined }, hash: '' })
  await nextTick()
  similarPeopleSearch.value?.focus()
}

function setZoom(direction: 'in' | 'out') {
  const panzoom = scanViewport.current()
  if (!panzoom) return
  if (direction === 'in' && zoomPercent.value < maximumZoomPercent)
    panzoom.zoomIn({ animate: false, step: SCAN_ZOOM_STEP })
  if (direction === 'out' && zoomPercent.value > minimumZoomPercent)
    panzoom.zoomOut({ animate: false, step: SCAN_ZOOM_STEP })
}
function resetView() {
  pendingFocus.value = null
  scanViewport.reset()
}

function handleNavigationKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey)
    return
  if (
    event.target instanceof HTMLElement &&
    (event.target.isContentEditable ||
      (event.target.closest(
        'input, select, textarea, button, a, [role=tablist], [role=dialog], [role=alertdialog]',
      ) &&
        // Detection boxes and their action panel keep face and line navigation.
        !event.target.closest('[data-region-type="face"], [data-detection-actions]')))
  )
    return
  const navigate = {
    ArrowUp: previousLine,
    ArrowDown: nextLine,
    ArrowLeft: previousFace,
    ArrowRight: nextFace,
    PageDown: () => teleprompter.value?.scrollPage('next'),
    PageUp: () => teleprompter.value?.scrollPage('previous'),
  }[event.key]
  if (!navigate) return
  event.preventDefault()
  navigate()
}

watch(
  transcription,
  () => {
    // A restored line hidden by the current mode starts at the nearest visible line.
    const index = routeLineIndex(route.query.line)
    selectedLineIndex.value = nearestIncluded(includedLines.value, index) ?? index
  },
  { immediate: true },
)
watch(
  () => [route.query.lines, route.query.highlight],
  () => {
    // The URL keeps a Custom view's base mode, so only a different mode applies.
    const lines = parseLineVisibility(route.query.lines)
    if (lines !== routeLineMode.value) lineVisibility.value = lines
    const highlight = parseHighlightStates(route.query.highlight)
    // Query arrays are recreated on each navigation; keep equal selections stable.
    if (highlight.join() !== annotationHighlight.value.join()) annotationHighlight.value = highlight
  },
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

watch([faces, referenceFace, transcription, annotationsLoading], () => {
  if (annotationsLoading.value) return
  let changed = false
  if (selectedFaceId.value && !selectedFace.value) {
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

onMounted(() => {
  window.addEventListener('keydown', handleNavigationKeydown)
  if (selectedFaceId.value) requestFocus({ kind: 'face', id: selectedFaceId.value })
})

onBeforeUnmount(() => {
  if (focusFrame !== undefined) cancelAnimationFrame(focusFrame)
  pendingFocus.value = null
  window.removeEventListener('keydown', handleNavigationKeydown)
})
</script>

<template>
  <main class="workspace-grid">
    <!-- The splitter sets an inline 100% height, so this wrapper owns the height. -->
    <div class="workspace-split">
      <ResizablePanelGroup
        :direction="splitDirection"
        @layout="workspaceSplit.layoutChanged"
      >
        <!-- On wide screens 40% keeps the settings row on one line from about 1440px. -->
        <ResizablePanel ref="transcriptionPanel" :default-size="workspaceSplit.defaultSize" :min-size="15" :max-size="70">
          <section
            class="workspace-teleprompter relative size-full min-h-0 min-w-0 overflow-hidden bg-background"
            aria-labelledby="page-transcription-title"
          >
            <DocumentTeleprompter
              ref="teleprompter"
              v-model:line-visibility="lineVisibility"
              v-model:annotation-highlight="annotationHighlight"
              class="absolute inset-y-0 left-3 right-3 sm:left-6 sm:right-6"
              :transcription="transcription"
              :selected-line-index="selectedLineIndex"
              :selected-entity-key="selectedEntityKey"
              :related-entity-id="selectedPersonId"
              :entity-names="entityNames"
              :included="includedLines"
              :is-translation-open="isTranslationOpen"
              :selected-language="selectedLanguage"
              :current-translation="currentTranslation"
              :translation-loading="translationLoading"
              @select-line="selectLine"
              @select-entity="selectEntity"
              @expand="expandContext"
            />
          </section>
        </ResizablePanel>
        <!-- Above scan overlays and toolbars, which would otherwise capture drags at the edge. -->
        <ResizableHandle
          with-handle
          aria-label="Resize transcription panel"
          class="z-30 data-[orientation=vertical]:after:h-3 data-[orientation=horizontal]:after:w-3"
        />
        <ResizablePanel
          :default-size="100 - workspaceSplit.defaultSize"
          class="flex min-h-0 min-w-0 flex-col"
        >
          <section
            ref="viewerElement"
            class="workspace-viewer bg-viewer relative min-h-0 flex-1 overflow-hidden"
            aria-label="Pan and zoom document page"
            tabindex="-1"
          >
            <PagePosition
              class="absolute bottom-3 right-3 z-20 bg-background px-2 py-1"
              :number="page?.page_number"
              :total="page?.registered_page_count"
            />
            <DocumentControls
              class="viewer-tools absolute inset-x-3 top-3 z-20 mx-auto w-fit max-w-[calc(100%-1.5rem)]"
              @pointerdown.stop
              @wheel.stop
              @keydown.stop
              v-model:link-states="linkStates"
              :selected-line-index="visibleLineIndices.indexOf(selectedLineIndex)"
              :line-count="visibleLineIndices.length"
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
                      <span v-if="error || pageImageError">Could not load scan</span
                      ><span v-else>Loading scan…</span>
                    </div>
                  </template>
                </LoadableImage>
              </div>
            </div>
            <DocumentPageOverlay
              :page-bounds="pageBounds"
              :viewer="viewerElement"
              :actions-enabled="(canAnnotate || canDelete) && !deletionTarget"
              :transcription="transcription"
              :faces="faces"
              :selected-line-index="selectedLineIndex"
              :selected-face-id="selectedFace?.id ?? null"
              :selected-person-id="selectedPersonId"
              :selected-candidate-face-id="selectedPersonCandidate?.faceId ?? null"
              :show-badge-names="showBadgeNames"
              @select-line="selectLine"
              @select-face="selectFace"
              @clear-face="clearFace"
            >
              <template #actions="{ face }">
                <FaceActionButtons
                  :face="face"
                  :can-annotate="canAnnotate"
                  :can-delete="canDelete"
                  :busy="actionBusy"
                  @find-profile="focusSimilarPeopleSearch"
                  @unassign="unassignSelectedFace"
                  @verify="verifyFace(face)"
                  @delete="requestDeletion(face)"
                />
                <p v-if="actionError" role="alert" class="text-xs text-destructive">
                  {{ actionError }}
                </p>
              </template>
            </DocumentPageOverlay>
          </section>

          <DocumentPageGallery
            class="workspace-gallery shrink-0 border-t"
            :document-url="documentQuery.data.value?.url"
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
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>

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
          :assignment-pending="actionBusy"
          :can-delete="canDelete && selectedFaceOnPage"
          :action-error="actionError"
          @delete="requestDeletion(selectedFace ?? null)"
          @find-profile="focusSimilarPeopleSearch"
          @create="createSimilarPerson"
          @unassign="unassignSelectedFace"
        >
          <UiTooltip
            v-if="selectedFace?.personId && selectedFace.linkState !== 'verified' && canAnnotate"
            text="Verify this link"
          >
            <Button
              variant="outline"
              size="icon-xs"
              class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
              :disabled="actionBusy"
              aria-label="Verify this link"
              @click="verifyFace(selectedFace)"
              ><BadgeCheck aria-hidden="true"
            /></Button>
          </UiTooltip>
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
          :assignment-pending="actionBusy"
          :search-term="`${candidateBrowseMode}:${candidateTerm}`"
          @load-more="loadMore()"
          @preview="previewSimilarPerson"
          @assign="assignSimilarPerson"
        />
      </TabsContent>
      <TabsContent value="activity" class="mt-0 min-h-0 overflow-y-auto">
        <PageActivityPanel v-if="page" :source-id="page.source_id" :workspace-filters="false" />
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
    <AlertDialog :open="Boolean(deletionTarget)" @update:open="closeDeletion">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this detection?</AlertDialogTitle>
          <AlertDialogDescription
            >This cannot be undone. Any link to a person is removed.</AlertDialogDescription
          >
        </AlertDialogHeader>
        <p v-if="deleteMutation.error.value" role="alert" class="text-sm text-destructive">
          Could not delete detection. Try again.
        </p>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="deleteMutation.isPending.value">Cancel</AlertDialogCancel>
          <Button variant="destructive" :disabled="actionBusy" @click="deleteDetection"
            >Delete</Button
          >
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>

<style scoped>
.workspace-grid {
  display: grid;
  min-height: calc(100vh - 3.25rem);
  grid-template-columns: minmax(0, 1fr);
}

/* Narrow screens: transcription above the scan, filling one screen height. */
.workspace-split {
  height: max(34rem, calc(100dvh - 3.25rem));
}

.workspace-sidebar {
  height: 85dvh;
  min-height: 36rem;
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
  }

  .workspace-split {
    height: auto;
    min-height: 0;
  }

  .workspace-sidebar {
    height: auto;
    min-height: 0;
    border-left-width: 1px;
    border-top-width: 0;
  }
}
</style>
