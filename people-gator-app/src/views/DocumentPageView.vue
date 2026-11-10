<script setup lang="ts">
import { useCreationFilters } from '@/viewmodels/shared-filters'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { focusTransform, MINIMUM_ZOOM, MAXIMUM_ZOOM } from '@/viewmodels/document-focus'
import { SCAN_ZOOM_STEP, useScanViewport } from '@/composables/scan-viewport'
import {
  SIDEBAR_WIDTH,
  useSidebarWidth,
  useWorkspaceSplit,
  type WorkspacePanel,
} from '@/composables/workspace-split'
import { useMediaQuery } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import { Button } from '@/components/ui/button'
import { BadgeCheck } from '@lucide/vue'
import UiTooltip from '@/components/custom/UiTooltip.vue'
import { useCanAnnotate, useCanDeleteDetection } from '@/composables/can-annotate'
import { useVerifyLinkMutation } from '@/query/entity-links'
import { useDeleteFaceMutation, useFaceQuery } from '@/query/faces'
import { useTextMentionQuery } from '@/query/text-mentions'
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
import { useDocumentLookupQuery } from '@/query/media'
import DocumentControls from '@/components/custom/DocumentControls.vue'
import DocumentPageGallery from '@/components/custom/DocumentPageGallery.vue'
import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import ScanFacesPanel from '@/components/custom/ScanFacesPanel.vue'
import ScanInfoPanel from '@/components/custom/ScanInfoPanel.vue'
import ScanMentionsPanel from '@/components/custom/ScanMentionsPanel.vue'
import ScanPeoplePanel from '@/components/custom/ScanPeoplePanel.vue'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
import type {
  PageViewportBounds,
  TranscriptionEntitySpan,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import type { Language } from '@/client'
import { useDocumentWorkspace } from '@/viewmodels/document-workspace'
import PagePosition from '@/components/custom/PagePosition.vue'
import { useRouteSort } from '@/lib/sorting'
import { GALLERY_DEFAULT, GALLERY_SORT_KEYS, GALLERY_SORTS } from '@/viewmodels/sort-options'
import {
  effectivePeopleOrder,
  resolveSearchModel,
  SCAN_SELECTED_MENTION,
  useScanSidebarState,
  type ScanSidebarState,
} from '@/viewmodels/scan-sidebar'
import { useScanPeople } from '@/viewmodels/scan-people'
import { useScanFaces } from '@/viewmodels/scan-faces'
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
// Wide screens size the sidebar beside the workspace; narrow ones stack it below.
const sidebarPanel = ref<WorkspacePanel | null>(null)
const sidebarWidth = useSidebarWidth(isWideWorkspace, sidebarPanel)
const sidebar = useScanSidebarState()
const sidebarState = sidebar.state
const libraryId = computed(() => String(route.params.libraryId))
const documentId = computed(() => String(route.params.documentId))
const linkStates = useLinkStateFilter('page_link_state')
const creation = useCreationFilters()
function resetEvidenceFilters() {
  linkStates.value = []
  creation.clear()
}
const documentQuery = useDocumentLookupQuery(libraryId, documentId)
const pageId = computed(() => String(route.params.pageId))
const selectedFaceId = ref<string | null>(
  typeof route.query.person === 'string' ? route.query.person : null,
)
const selectedPersonId = ref<string | null>(
  typeof route.query.selectedPerson === 'string' ? route.query.selectedPerson : null,
)
// Sidebar settings live in the URL; each change is a history entry.
function setting<Key extends keyof ScanSidebarState>(key: Key) {
  return computed({
    get: () => sidebarState.value[key],
    set: (value: ScanSidebarState[Key]) => sidebar.update({ [key]: value }),
  })
}
// Typed name text replaces the current history entry instead of adding one per pause.
const peopleText = computed({
  get: () => sidebarState.value.peopleText,
  set: (value: string) => sidebar.update({ peopleText: value }, 'replace'),
})
const faceScope = setting('faceScope')
const faceView = setting('faceView')
const mentionScope = setting('mentionScope')
const mentionView = setting('mentionView')
const mentionSort = setting('mentionSort')
const mentionGroupSort = setting('mentionGroupSort')
const activityDirection = setting('activityDirection')
const peopleScope = setting('peopleScope')
// The scan's faces follow the Faces tab's flat order for navigation.
const faceSort = setting('faceSort')
const gallerySort = useRouteSort(GALLERY_SORT_KEYS, GALLERY_SORTS, GALLERY_DEFAULT)
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
  isLoading,
  pageDimensions,
  pageImageLoading,
  pageImageError,
  pageImageLoaded,
  pageImageReady,
  pageImageUrl,
  transcription,
  entityNames,
  unassignFace,
} = useDocumentWorkspace(libraryId, documentId, pageId, selectedFaceId, linkStates, faceSort)

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
const peoplePanel = ref<InstanceType<typeof ScanPeoplePanel> | null>(null)
const teleprompter = ref<InstanceType<typeof DocumentTeleprompter> | null>(null)
const focusPageKey = computed(() => `${libraryId.value}/${documentId.value}/${pageId.value}`)
const scanViewport = useScanViewport(
  viewerElement,
  zoomElement,
  pageElement,
  focusPageKey,
  pageBounds,
  zoomPercent,
  scheduleFocus,
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
// A selected face hidden by evidence filters still anchors its card on this scan.
const overlayFaces = computed(() =>
  referenceFace.value && !faces.value.some((face) => face.id === referenceFace.value?.id)
    ? [...faces.value, referenceFace.value]
    : faces.value,
)
const sources = computed(() => {
  const document = documentQuery.data.value
  return page.value && document
    ? { page: page.value.source_id, document: document.source_id }
    : null
})

// People search may carry one attached reference face, independent of selection.
const searchFaceId = computed(() => sidebarState.value.searchFaceId)
const searchFaceQuery = useFaceQuery(() => searchFaceId.value ?? '')
// Models the attached face has embeddings for; the chosen one, else its first.
const searchFaceModels = computed(() => {
  const record = searchFaceQuery.data.value
  return record?.detection_id === searchFaceId.value ? (record.embeddings ?? []) : []
})
const searchModel = computed(() =>
  resolveSearchModel(sidebarState.value.searchModel, searchFaceModels.value),
)
const searchFace = computed(() =>
  searchFaceId.value && searchModel.value
    ? { id: searchFaceId.value, embeddingModel: searchModel.value }
    : null,
)
// A deleted face, or one without an embedding, cannot score People; drop it.
watch(
  () => [searchFaceId.value, searchFaceQuery.data.value, searchFaceQuery.isError.value] as const,
  ([id, record, failed]) => {
    if (id && (failed || (record?.detection_id === id && !record.embeddings?.[0])))
      sidebar.update({ searchFaceId: null }, 'replace')
  },
)
const peopleScored = computed(
  () => Boolean(sidebarState.value.peopleText.trim()) || Boolean(searchFaceId.value),
)
const peopleOrder = computed({
  get: () => effectivePeopleOrder(sidebarState.value.peopleOrder, peopleScored.value),
  set: (value) => sidebar.update({ peopleOrder: value }),
})
const people = reactive(
  useScanPeople({
    sources,
    scope: () => sidebarState.value.peopleScope,
    order: peopleOrder,
    search: () => ({ text: sidebarState.value.peopleText, face: searchFace.value }),
    searchPending: () => Boolean(searchFaceId.value) && searchFaceQuery.isPending.value,
    filters: creation.params,
    enabled: () => sidebarState.value.tab === 'people' && !creation.error.value,
    pageFaces: faces,
    transcription,
    pageSourceId: () => page.value?.source_id ?? '',
  }),
)
const scanFaces = reactive(
  useScanFaces({
    sources,
    scope: faceScope,
    view: faceView,
    sort: faceSort,
    linkStates,
    filters: creation.params,
    enabled: () => sidebarState.value.tab === 'faces' && !creation.error.value,
  }),
)
function removeSearchFace() {
  // Typed name text stays; Similarity needs a name or face to score.
  sidebar.update({
    searchFaceId: null,
    searchModel: null,
    ...(!sidebarState.value.peopleText.trim() && { peopleOrder: 'context' as const }),
  })
}
const focusPeopleRequested = ref(false)
function applyPeopleFocus() {
  if (!focusPeopleRequested.value || sidebarState.value.tab !== 'people' || !peoplePanel.value)
    return
  focusPeopleRequested.value = false
  peoplePanel.value.focus()
}
watch([peoplePanel, () => sidebarState.value.tab], applyPeopleFocus, { flush: 'post' })
function focusPeopleSearch() {
  focusPeopleRequested.value = true
  if (sidebarState.value.tab === 'people') void nextTick(applyPeopleFocus)
  else sidebar.update({ tab: 'people' })
}
// Face Search opens People with the results; focus stays on the scan card.
function searchByFace(face: Face) {
  sidebar.searchByFace(face.id)
}
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
  people.people.find((person) => person.id === selectedPersonId.value),
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
  sidebar.patch({
    person: selectedFaceId.value ?? undefined,
    selectedPerson: selectedPersonId.value ?? undefined,
    line: line?.id,
    // A Custom line set is not shareable; links keep the mode it came from.
    lines: routeLineMode.value === 'all' ? undefined : routeLineMode.value,
    highlight: annotationHighlight.value.length ? annotationHighlight.value : undefined,
    translate: isTranslationOpen.value ? 'on' : 'off',
  })
}

function selectFace(faceId: string) {
  requestFocus({ kind: 'face', id: faceId })
  selectedFaceId.value = faceId
  selectedPersonId.value = faces.value.find((face) => face.id === faceId)?.personId ?? null
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
        // Detection boxes and their card keep face and line navigation.
        !event.target.closest('[data-region-type="face"], [data-detection-card]')))
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

// A Mentions-tab link selects its mention here like a click in the transcription.
// Spans match recorded text, so the mention's own context picks its line; an
// unlinked mention has no span and selects that line instead.
const requestedMention = computed(() =>
  typeof route.query.mention === 'string' ? route.query.mention : '',
)
const requestedMentionQuery = useTextMentionQuery(requestedMention)
const selectedUnlinkedMention = ref<string | null>(null)
watch([selectedLineIndex, selectedEntityKey], () => (selectedUnlinkedMention.value = null), {
  flush: 'sync',
})
watch(
  [requestedMention, transcription, isLoading, () => requestedMentionQuery.data.value],
  ([id]) => {
    if (!id || isLoading.value) return
    const record = requestedMentionQuery.data.value
    if (record?.mention_id !== id && !requestedMentionQuery.isError.value) return
    const lines = transcription.value
    const context = (record?.context ?? '').trim()
    const own = (index: number) => {
      const text = lines[index]!.text.trim()
      return Boolean(text) && context.includes(text)
    }
    const spanLines = lines.flatMap((line, index) =>
      line.entities?.some((span) => span.mention_id === id) ? [index] : [],
    )
    const index = spanLines.find(own) ?? spanLines[0]
    if (index !== undefined) {
      const spans = lines[index]!.entities!.filter((span) => span.mention_id === id)
      const span = spans.find((item) => item.firstFragment !== false) ?? spans[0]!
      if (!includedLines.value[index]) teleprompterLines.reveal([index])
      selectEntity(index, span)
    } else {
      const fallback = context ? lines.findIndex((_line, line) => own(line)) : -1
      if (fallback >= 0) {
        selectLine(fallback)
        selectedUnlinkedMention.value = id
      }
    }
    sidebar.patch({ mention: undefined })
  },
  { immediate: true },
)
// The mention selected on the scan, shown in the Mentions list too.
provide(
  SCAN_SELECTED_MENTION,
  computed(() => {
    const key = selectedEntityKey.value
    if (!key) return selectedUnlinkedMention.value
    for (const line of transcription.value)
      for (const span of line.entities ?? [])
        if (transcriptionEntityKey(span) === key) return span.mention_id ?? null
    return null
  }),
)

// Narrow screens scroll the sidebar with the page. A tab switch keeps the tab
// bar where it was; when scrolled past it, the new tab starts at its top.
const sidebarTabs = ref<{ $el: HTMLElement } | null>(null)
let tabBarTop: number | null = null
function tabBar() {
  return sidebarTabs.value?.$el?.querySelector<HTMLElement>('[role="tablist"]') ?? null
}
function appBarHeight() {
  return 3.25 * parseFloat(getComputedStyle(document.documentElement).fontSize || '16')
}
watch(
  () => sidebarState.value.tab,
  () => {
    tabBarTop = isWideWorkspace.value ? null : (tabBar()?.getBoundingClientRect().top ?? null)
  },
  { flush: 'pre' },
)
watch(
  () => sidebarState.value.tab,
  () => {
    const before = tabBarTop
    tabBarTop = null
    if (before === null) return
    const target = Math.max(before, appBarHeight())
    // Once the new tab has laid out, return the tab bar to its place.
    const place = () => {
      const bar = tabBar()
      if (bar) window.scrollBy({ top: bar.getBoundingClientRect().top - target })
    }
    requestAnimationFrame(() => {
      place()
      requestAnimationFrame(place)
    })
  },
  { flush: 'post' },
)

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
    <ResizablePanelGroup
      direction="horizontal"
      class="workspace-layout"
      @layout="sidebarWidth.layoutChanged"
    >
      <ResizablePanel :min-size="50" class="workspace-main">
        <!-- The splitter sets an inline 100% height, so this wrapper owns the height. -->
        <div class="workspace-split">
          <ResizablePanelGroup :direction="splitDirection" @layout="workspaceSplit.layoutChanged">
            <!-- On wide screens 40% keeps the settings row on one line from about 1440px. -->
            <ResizablePanel
              ref="transcriptionPanel"
              :default-size="workspaceSplit.defaultSize"
              :min-size="15"
              :max-size="70"
            >
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
                        <div
                          class="flex size-full items-center justify-center text-muted-foreground"
                        >
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
                  :actions-enabled="!deletionTarget"
                  :transcription="transcription"
                  :faces="overlayFaces"
                  :selected-line-index="selectedLineIndex"
                  :selected-face-id="selectedFace?.id ?? null"
                  :selected-person-id="selectedPersonId"
                  :selected-candidate-face-id="selectedPersonCandidate?.faceId ?? null"
                  :show-badge-names="showBadgeNames"
                  @select-line="selectLine"
                  @select-face="selectFace"
                  @clear-face="clearFace"
                >
                  <template #card="{ face }">
                    <SelectedFaceItem
                      :face="face"
                      :assignment-pending="actionBusy"
                      :can-annotate="canAnnotate"
                      :can-delete="canDelete"
                      :action-error="actionError"
                      @find-profile="focusPeopleSearch"
                      @search-face="searchByFace(face)"
                      @create-profile="createSimilarPerson"
                      @unassign="unassignSelectedFace"
                      @delete="requestDeletion(face)"
                    >
                      <template #actions>
                        <UiTooltip
                          v-if="face.personId && face.linkState !== 'verified'"
                          text="Verify this link"
                        >
                          <Button
                            variant="outline"
                            size="icon-xs"
                            class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
                            :disabled="actionBusy"
                            aria-label="Verify this link"
                            @click="verifyFace(face)"
                            ><BadgeCheck aria-hidden="true"
                          /></Button>
                        </UiTooltip>
                      </template>
                    </SelectedFaceItem>
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
      </ResizablePanel>
      <ResizableHandle
        v-if="isWideWorkspace"
        with-handle
        aria-label="Resize sidebar"
        class="z-30 after:w-3"
      />
      <ResizablePanel
        ref="sidebarPanel"
        size-unit="px"
        :default-size="sidebarWidth.defaultSize"
        :min-size="isWideWorkspace ? SIDEBAR_WIDTH.min : 0"
        :max-size="SIDEBAR_WIDTH.max"
        class="workspace-aside"
      >
        <Tabs
          ref="sidebarTabs"
          class="workspace-sidebar flex min-h-0 min-w-0 flex-col gap-0 overflow-hidden border-t bg-background"
          :model-value="sidebarState.tab"
          @update:model-value="(tab) => sidebar.update({ tab: tab as ScanSidebarState['tab'] })"
        >
          <div class="shrink-0 border-b p-3">
            <TabsList aria-label="Page sidebar" class="w-full">
              <TabsTrigger value="people">People</TabsTrigger>
              <TabsTrigger value="faces">Faces</TabsTrigger>
              <TabsTrigger value="mentions">Mentions</TabsTrigger>
              <TabsTrigger value="info">Info</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="people" class="mt-0 flex min-h-0 flex-1 flex-col">
            <ScanPeoplePanel
              ref="peoplePanel"
              v-model:text="peopleText"
              v-model:scope="peopleScope"
              v-model:order="peopleOrder"
              :people="people.people"
              :scored="peopleScored"
              :loading="people.loading"
              :total-count="people.totalCount"
              :has-next-page="people.hasNextPage"
              :is-fetching="people.isFetching"
              :error="people.error"
              :search-face-id="searchFaceId"
              :face-models="searchFaceModels"
              :face-model="searchModel"
              @update:face-model="(model) => sidebar.update({ searchModel: model })"
              :selected-face="selectedFace ?? null"
              :viewed-person-id="selectedPersonId"
              :assignment-pending="actionBusy"
              :load-more="people.loadMore"
              :retry="people.retry"
              @remove-face="removeSearchFace"
              @attach-selected-face="selectedFace && searchByFace(selectedFace)"
              @preview="previewSimilarPerson"
              @assign="assignSimilarPerson"
            />
          </TabsContent>
          <TabsContent value="faces" class="mt-0 flex min-h-0 flex-1 flex-col">
            <ScanFacesPanel
              v-model:scope="faceScope"
              v-model:view="faceView"
              v-model:sort="faceSort"
              :items="scanFaces.items"
              :groups="scanFaces.groups"
              :loading="scanFaces.loading"
              :has-next-page="scanFaces.hasNextPage"
              :is-fetching="scanFaces.isFetching"
              :error="scanFaces.error"
              :total-count="scanFaces.totalCount"
              :selected-face-id="selectedFace?.id ?? null"
              :filtered="linkStates.length > 0 || Object.keys(creation.params.value).length > 0"
              :load-more="scanFaces.loadMore"
              :retry="scanFaces.retry"
              @select="selectFace"
              @reset-filters="resetEvidenceFilters"
            />
          </TabsContent>
          <TabsContent value="mentions" class="mt-0 flex min-h-0 flex-1 flex-col">
            <ScanMentionsPanel
              v-model:scope="mentionScope"
              v-model:view="mentionView"
              v-model:sort="mentionSort"
              v-model:group-sort="mentionGroupSort"
              :sources="sources"
              :link-states="linkStates"
              :creation-filters="creation.params.value"
              :enabled="!creation.error.value"
              @reset-filters="resetEvidenceFilters"
            />
          </TabsContent>
          <TabsContent value="info" class="mt-0 flex min-h-0 flex-1 flex-col">
            <ScanInfoPanel v-model:direction="activityDirection" :page="page" />
          </TabsContent>
        </Tabs>
      </ResizablePanel>
    </ResizablePanelGroup>
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

/* Narrow screens: the sidebar sits below the workspace and grows with its
   content, so its lists scroll with the page instead of an inner container.
   The sidebar splitter stays mounted, so its inline flex layout is undone here. */
@media (max-width: 1023.98px) {
  .workspace-layout {
    display: block !important;
    height: auto !important;
    overflow: visible !important;
  }

  .workspace-main,
  .workspace-aside {
    overflow: visible !important;
  }
}

.workspace-sidebar {
  height: auto;
  overflow: visible;
  /* At least one screen tall, so a shorter tab never pulls the page (and the
     tab bar) up when switching tabs, and the tab bar can rest under the app bar. */
  min-height: 100dvh;
  /* The tab switch places the page itself; browser anchoring would undo it. */
  overflow-anchor: none;
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
  }

  .workspace-split {
    height: 100%;
    min-height: 0;
  }

  /* The resize handle draws the border between the workspace and the sidebar. */
  .workspace-sidebar {
    height: 100%;
    min-height: 0;
    overflow: hidden;
    border-top-width: 0;
  }
}
</style>
