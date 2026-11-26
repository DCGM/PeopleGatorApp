import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { AxiosError, type AxiosResponse } from 'axios'
import { mount, shallowMount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { reactive, ref, nextTick, type Ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DocumentPageView from '@/views/DocumentPageView.vue'
import type { Face, TranscriptionLine } from '@/viewmodels/document-workspace.types'

const mocks = vi.hoisted(() => ({
  workspace: vi.fn(),
  route: vi.fn(),
  zoom: vi.fn(),
  pan: vi.fn(),
  zoomIn: vi.fn(),
  zoomWithWheel: vi.fn(),
  reset: vi.fn(),
  gallery: vi.fn(),
  replace: vi.fn(),
  push: vi.fn(),
  focusPeople: vi.fn(),
  mention: vi.fn(),
  deleteFace: vi.fn(),
  patchFace: vi.fn(),
  assignFace: vi.fn(),
  unassignFace: vi.fn(),
  createAndAssign: vi.fn(),
  documentLookup: vi.fn(),
  getFace: vi.fn(),
  listEntities: vi.fn(),
  searchEntities: vi.fn(),
  patchMentions: vi.fn(),
  patchMention: vi.fn(),
  deleteMentions: vi.fn(),
  createMention: vi.fn(),
  putPerson: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: mocks.route,
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  deleteFaceRouteApiV1FacesDetectionIdDelete: mocks.deleteFace,
  patchFaceRouteApiV1FacesDetectionIdPatch: mocks.patchFace,
  getTextMentionRouteApiV1TextMentionsMentionIdGet: mocks.mention,
  getFaceRouteApiV1FacesDetectionIdGet: mocks.getFace,
  listEntitiesRouteApiV1EntitiesGet: mocks.listEntities,
  searchEntitiesGetApiV1SearchEntitiesGet: mocks.searchEntities,
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch: mocks.patchMentions,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch: mocks.patchMention,
  deleteTextMentionBatchRouteApiV1TextMentionsBatchDelete: mocks.deleteMentions,
  createTextMentionRouteApiV1TextMentionsPost: mocks.createMention,
  putPersonRouteApiV1PeopleEntityIdPut: mocks.putPerson,
}))
vi.mock('@/composables/can-annotate', () => ({
  useCanAnnotate: () => ref(true),
  useCanDeleteDetection: () => ref(true),
  useHasScope: () => ref(true),
}))
vi.mock('@/composables/link-state-filter', () => ({ useLinkStateFilter: () => ref([]) }))
vi.mock('@/query/entities', async (original) => ({
  ...(await original<typeof import('@/query/entities')>()),
  useEntityQuery: () => ({ data: ref(null) }),
}))
vi.mock('@/query/media', () => ({
  useDocumentLookupQuery: mocks.documentLookup,
}))
vi.mock('@/query/translation', () => ({
  useTranslationQuery: () => ({ data: ref(null), isFetching: ref(false) }),
}))
vi.mock('@/viewmodels/document-workspace', () => ({ useDocumentWorkspace: mocks.workspace }))
vi.mock('@/viewmodels/document-page-gallery', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/viewmodels/document-page-gallery')>()),
  useDocumentPageGallery: mocks.gallery,
}))
vi.mock('@panzoom/panzoom', () => ({
  default: () => ({
    zoom: mocks.zoom,
    zoomIn: mocks.zoomIn,
    zoomWithWheel: mocks.zoomWithWheel,
    pan: mocks.pan,
    reset: mocks.reset,
    getScale: () => 1,
    getPan: () => ({ x: 0, y: 0 }),
    destroy: vi.fn(),
  }),
}))

const box = { left: 10, top: 20, width: 20, height: 20 }
const face = (id: string): Face => ({
  id,
  personId: 'ada',
  name: 'Ada',
  confidence: 99,
  status: 'assigned',
  position: box,
  portrait: '',
  portraitLoading: false,
})
const span = (line_id: string) => ({
  entity_id: 'ada',
  line_id,
  label: 'person' as const,
  text: 'Ada',
  start_index: 0,
  end_index: 3,
})
let ready: Ref<boolean>
let faces: Ref<Face[]>
let lines: Ref<TranscriptionLine[]>
let route: { params: Record<string, string>; query: Record<string, string> }
let assignmentError: Ref<Error | null>
let assignmentStatus: Ref<string>
let referenceFace: Ref<Face | null>
beforeEach(() => {
  vi.clearAllMocks()
  route = reactive({ params: { libraryId: 'lib', documentId: 'doc', pageId: 'one' }, query: {} })
  mocks.route.mockReturnValue(route)
  mocks.documentLookup.mockReturnValue({ isPending: ref(false), error: ref(null), data: ref(null) })
  mocks.gallery.mockReturnValue({
    items: ref([]),
    totalCount: ref(null),
    isLoading: ref(false),
    error: ref(null),
    highlightError: ref(false),
    retryHighlights: vi.fn(),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    loadMore: vi.fn(),
    retry: vi.fn(),
  })
  ready = ref(true)
  assignmentError = ref(null)
  assignmentStatus = ref('idle')
  referenceFace = ref(null)
  faces = ref([face('a'), face('b')])
  lines = ref(
    ['l1', 'l2'].map((id, index) => ({
      id,
      text: 'Ada',
      position: { ...box, top: 20 + index * 50 },
      entities: [span(id)],
    })),
  )
  mocks.workspace.mockReturnValue({
    faces,
    assignmentStatus,
    assignFace: mocks.assignFace,
    unassignFace: mocks.unassignFace,
    createAndAssign: mocks.createAndAssign,
    assignmentError,
    resetAssignment: vi.fn(() => (assignmentError.value = null)),
    referenceFace,
    transcription: lines,
    page: ref({ page_id: 'one', source_id: 'source' }),
    pageImageReady: ready,
    annotationsLoading: ref(false),
    isLoading: ref(false),
    pageDimensions: ref({ width: 800, height: 1100 }),
    pageImageUrl: ref(''),
    pageImageLoading: ref(false),
  })
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    return {
      left: 0,
      top: 0,
      right: 800,
      bottom: this.classList.contains('viewer-tools') ? 80 : 600,
      width: 800,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }
  })
})
async function settleFocus() {
  await flushPromises()
  await new Promise((resolve) => requestAnimationFrame(resolve))
  await flushPromises()
}
async function mountView(renderActions = false, mentionCard = false) {
  const wrapper = (renderActions ? mount : shallowMount)(DocumentPageView, {
    global: {
      plugins: [
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
        ],
      ],
      stubs: {
        ...(renderActions
          ? {
              AlertDialogHeader: { template: '<div><slot /></div>' },
              AlertDialogTitle: { template: '<h2><slot /></h2>' },
              AlertDialogDescription: { template: '<p><slot /></p>' },
              AlertDialogCancel: true,
              DocumentControls: true,
              DocumentPageGallery: true,
              PageReviewControls: true,
              // Like the real overlay: one card, for the selected face only.
              DocumentPageOverlay: {
                name: 'DocumentPageOverlay',
                props: ['faces', 'selectedFaceId', 'actionsEnabled'],
                template: `<div><template v-for="face in faces" :key="face.id"><slot
                  v-if="actionsEnabled && face.id === selectedFaceId" name="card" :face="face"
                /></template></div>`,
              },
              DocumentTeleprompter: mentionCard
                ? {
                    name: 'DocumentTeleprompter',
                    props: [
                      'selectedMentionIds',
                      'selectedEntityKey',
                      'selectedLineIndex',
                      'relatedEntityId',
                      'canCreateMention',
                      'canChangeMention',
                      'canMergeMentions',
                    ],
                    methods: { focusMentionCard: () => undefined },
                    template: '<div><slot name="mention-card" /></div>',
                  }
                : true,
              LoadableImage: true,
              IdentityFacePreview: true,
              RouterLink: RouterLinkStub,
              ScanPeoplePanel: {
                name: 'ScanPeoplePanel',
                props: ['assignmentPending'],
                template: '<div />',
                methods: { focus: mocks.focusPeople },
              },
              ScanFacesPanel: true,
              ScanMentionsPanel: true,
              ScanInfoPanel: true,
            }
          : {}),
        AlertDialog: { name: 'AlertDialog', props: ['open'], template: '<div><slot /></div>' },
        AlertDialogContent: { template: '<div><slot /></div>' },
        AlertDialogFooter: { template: '<div><slot /></div>' },
        PanelBar: {
          props: ['as'],
          template:
            '<component :is="as || \'div\'"><slot name="start" /><slot /><slot name="end" /></component>',
        },
        Tabs: { name: 'Tabs', props: ['modelValue'], template: '<div><slot /></div>' },
        TabsList: { template: '<div><slot /></div>' },
        TabsTrigger: {
          name: 'TabsTrigger',
          props: ['value'],
          template: '<button><slot /></button>',
        },
        TabsContent: { template: '<div><slot /></div>' },
        ResizablePanelGroup: { template: '<div><slot /></div>' },
        ResizablePanel: { template: '<div><slot /></div>' },
        ResizableHandle: true,
      },
    },
  })
  await settleFocus()
  return wrapper
}
describe('evidence selection viewport focus', () => {
  it('focuses gallery, overlay and keyboard face selections, including reselection', async () => {
    const wrapper = await mountView()
    for (const component of ['ScanFacesPanel', 'DocumentPageOverlay']) {
      wrapper
        .findComponent({ name: component })
        .vm.$emit(component === 'ScanFacesPanel' ? 'select' : 'select-face', 'a')
      await settleFocus()
    }
    expect(mocks.pan).toHaveBeenCalledTimes(2)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    await settleFocus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(4)
    faces.value = [...faces.value]
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(4)
    wrapper.unmount()
  })
  it('focuses the selected occurrence line, even when both names share an identity', async () => {
    const wrapper = await mountView()
    const transcription = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    transcription.vm.$emit('select-entity', 0, span('l1'))
    await settleFocus()
    const first = mocks.pan.mock.calls[0]![1]
    transcription.vm.$emit('select-entity', 1, span('l2'))
    await settleFocus()
    expect(mocks.pan.mock.calls[1]![1]).not.toBe(first)
    transcription.vm.$emit('select-entity', 1, span('l2'))
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })
  it('waits for readiness, uses the latest request, and discards stale page or removed targets', async () => {
    ready.value = false
    const wrapper = await mountView()
    const gallery = wrapper.findComponent({ name: 'ScanFacesPanel' })
    gallery.vm.$emit('select', 'a')
    gallery.vm.$emit('select', 'b')
    await settleFocus()
    expect(mocks.pan).not.toHaveBeenCalled()
    ready.value = true
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(1)
    ready.value = false
    gallery.vm.$emit('select', 'a')
    await nextTick()
    route.params.pageId = 'two'
    ready.value = true
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(1)
    gallery.vm.$emit('select', 'missing')
    await settleFocus()
    expect(mocks.pan).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

describe('document page gallery navigation', () => {
  it('scopes the gallery to the route document, not evidence filters', async () => {
    const wrapper = await mountView()
    const [library, document, page] = mocks.gallery.mock.calls[0]!
    expect([library.value, document.value, page.value]).toEqual(['lib', 'doc', 'one'])
    // Only the route document and the gallery's own order; no evidence filters.
    const [, , , , order, person, , notVerified] = mocks.gallery.mock.calls[0]!
    expect(mocks.gallery.mock.calls[0]).toHaveLength(8)
    expect(person.value).toBe('')
    expect(notVerified.value).toBe(false)
    expect(order.value).toEqual({ field: 'page_number', direction: 'asc' })
    const location = wrapper.findComponent({ name: 'DocumentPageGallery' }).props('location')
    route.query = {
      person: 'a',
      line: 'l2',
      link_state: 'manual',
      page_link_state: 'verified',
      selectedPerson: 'nora',
      gallery_person_only: 'on',
      gallery_sort: 'faces_total_count',
      gallery_dir: 'desc',
      gallery_not_verified: 'on',
      pages_view: 'expanded',
    }
    await settleFocus()
    expect(person.value).toBe('nora')
    expect(notVerified.value).toBe(true)
    expect(location({ library: 'lib', documentId: 'doc', pageId: 'two' })).toEqual({
      name: 'document-page',
      params: { libraryId: 'lib', documentId: 'doc', pageId: 'two' },
      query: {
        gallery_person_only: 'on',
        gallery_not_verified: 'on',
        selectedPerson: 'nora',
        gallery_sort: 'faces_total_count',
        gallery_dir: 'desc',
      },
    })
    wrapper.unmount()
  })

  it('restores expansion from the URL without replacing the mounted viewer', async () => {
    route.query = { pages_view: 'expanded', selectedPerson: 'nora', gallery_person_only: 'on' }
    const wrapper = await mountView()
    const gallery = wrapper.findComponent({ name: 'DocumentPageGallery' })
    const viewer = wrapper.get('.workspace-viewer').element
    expect(gallery.props('expanded')).toBe(true)
    const review = wrapper.findComponent({ name: 'PageReviewControls' })
    expect(review.element.closest('header.viewer-tools')).not.toBeNull()
    expect(review.isVisible()).toBe(true)
    expect((viewer as HTMLElement).style.display).toBe('none')
    gallery.vm.$emit('update:expanded', false)
    await flushPromises()
    expect(mocks.push.mock.lastCall?.[0].query).toMatchObject({
      pages_view: undefined,
      selectedPerson: 'nora',
      gallery_person_only: 'on',
    })
    route.query = { selectedPerson: 'nora', gallery_person_only: 'on' }
    await settleFocus()
    expect(wrapper.get('.workspace-viewer').element).toBe(viewer)
    expect((viewer as HTMLElement).style.display).not.toBe('none')
    expect(gallery.props('expanded')).toBe(false)
    wrapper.unmount()
  })

  it('filters only by the sidebar selection while the compact toggle is enabled', async () => {
    const wrapper = await mountView()
    const strip = wrapper.findComponent({ name: 'DocumentPageGallery' })
    const person = mocks.gallery.mock.calls[0]![5]
    route.query = { selectedPerson: 'nora', gallery_person_only: 'on' }
    await settleFocus()
    expect(person.value).toBe('nora')
    route.query = { selectedPerson: 'ada', gallery_person_only: 'on' }
    await settleFocus()
    expect(person.value).toBe('ada')
    route.query = { selectedPerson: 'ada' }
    await settleFocus()
    expect(person.value).toBe('')
    strip.vm.$emit('update:personOnly', true)
    await flushPromises()
    expect(mocks.push.mock.lastCall?.[0].query).toMatchObject({
      selectedPerson: 'ada',
      gallery_person_only: 'on',
    })
    wrapper.unmount()
  })

  it('resets the viewport and page-specific selections when another page opens', async () => {
    const wrapper = await mountView()
    const transcription = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    transcription.vm.$emit('select-entity', 1, span('l2'))
    await settleFocus()
    expect(transcription.props('selectedEntityKey')).not.toBeNull()
    expect(transcription.props('selectedLineIndex')).toBe(1)
    route.params.pageId = 'two'
    await settleFocus()
    expect(mocks.reset).toHaveBeenCalledWith(
      expect.objectContaining({ animate: false, startScale: 0.82 }),
    )
    expect(transcription.props('selectedEntityKey')).toBeNull()
    expect(transcription.props('selectedLineIndex')).toBe(0)
    wrapper.unmount()
  })
})

it('anchors the selected reference on the scan when workspace filters hide it', async () => {
  // A former "Similar faces" link attaches that face to People search once.
  route.query = { person: 'a', candidate_mode: 'face' }
  const reference = ref<Face | null>(face('a'))
  mocks.workspace.mockReturnValue({
    ...mocks.workspace.getMockImplementation()!(),
    referenceFace: reference,
  })
  faces.value = []
  const wrapper = await mountView()
  await flushPromises()
  const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
  expect(overlay.props('faces').map((item: Face) => item.id)).toEqual(['a'])
  expect(overlay.props('selectedFaceId')).toBe('a')
  expect(mocks.replace).toHaveBeenCalledWith(
    expect.objectContaining({
      query: expect.objectContaining({ candidate_mode: undefined, candidate_face: 'a' }),
    }),
  )
  wrapper.unmount()
})

describe('shared detection actions', () => {
  it('confirms deletion, preserves a rejected detection and clears selection/route only on success', async () => {
    mocks.deleteFace
      .mockRejectedValueOnce(new Error('Forbidden'))
      .mockResolvedValueOnce({ data: null })
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    const card = () => wrapper.findComponent({ name: 'SelectedFaceItem' })
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    expect(overlay.props('actionsEnabled')).toBe(true)
    card().vm.$emit('delete')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    // The scan card stays hidden behind the confirmation.
    expect(overlay.props('actionsEnabled')).toBe(false)
    expect(mocks.deleteFace).not.toHaveBeenCalled()
    const confirm = () => wrapper.get('button[data-slot="button"][class*="bg-destructive"]')
    await confirm().trigger('click')
    await flushPromises()
    expect(overlay.props('selectedFaceId')).toBe('a')
    expect(card().exists()).toBe(false)
    expect(wrapper.text()).toContain('Could not delete detection. Try again.')
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    await confirm().trigger('click')
    await flushPromises()
    expect(mocks.deleteFace).toHaveBeenLastCalledWith({
      path: { detection_id: 'a' },
      throwOnError: true,
    })
    expect(overlay.props('selectedFaceId')).toBeNull()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
    expect(mocks.replace).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({ person: undefined, selectedPerson: undefined }),
      }),
    )
    wrapper.unmount()
  })
  it('clears a failed delete when the confirmation closes', async () => {
    mocks.deleteFace.mockRejectedValueOnce(new Error('Forbidden'))
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    wrapper.findComponent({ name: 'SelectedFaceItem' }).vm.$emit('delete')
    await flushPromises()
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'AlertDialog' }).vm.$emit('update:open', false)
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
    expect(wrapper.findComponent({ name: 'DocumentPageOverlay' }).props('actionsEnabled')).toBe(
      true,
    )
    expect(wrapper.text()).not.toContain('Could not delete detection')
    wrapper.unmount()
  })
  it('clears a failed link update when another face is selected', async () => {
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    assignmentError.value = new Error('Forbidden')
    await flushPromises()
    const card = () => wrapper.findComponent({ name: 'SelectedFaceItem' })
    expect(card().props('actionError')).toBe('Could not update link.')
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'b')
    await flushPromises()
    expect(card().props('face')).toMatchObject({ id: 'b' })
    expect(card().props('actionError')).toBe('')
    wrapper.unmount()
  })
  it('keeps face and line navigation from detection boxes and their card', async () => {
    const wrapper = await mountView()
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    const container = document.createElement('div')
    container.innerHTML = `
      <button data-region-type="face"></button>
      <div data-detection-card role="dialog"><button id="action"></button></div>
      <button id="other"></button>`
    document.body.append(container)
    const key = (selector: string, key: string) =>
      container
        .querySelector(selector)!
        .dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
    try {
      overlay.vm.$emit('select-face', 'a')
      await flushPromises()
      key('#action', 'ArrowRight')
      await flushPromises()
      expect(overlay.props('selectedFaceId')).toBe('b')
      key('[data-region-type="face"]', 'ArrowLeft')
      await flushPromises()
      expect(overlay.props('selectedFaceId')).toBe('a')
      key('#action', 'ArrowDown')
      await flushPromises()
      expect(
        wrapper.findComponent({ name: 'DocumentTeleprompter' }).props('selectedLineIndex'),
      ).toBe(1)
      // Ordinary buttons keep their own arrow keys.
      key('#other', 'ArrowRight')
      await flushPromises()
      expect(overlay.props('selectedFaceId')).toBe('a')
    } finally {
      container.remove()
      wrapper.unmount()
    }
  })
})

it('clears the selected face and route when the overlay requests Escape dismissal', async () => {
  const wrapper = await mountView()
  const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
  overlay.vm.$emit('select-face', 'a')
  await flushPromises()
  expect(overlay.props('selectedFaceId')).toBe('a')
  overlay.vm.$emit('clear-face')
  await flushPromises()
  expect(overlay.props('selectedFaceId')).toBeNull()
  expect(mocks.replace).toHaveBeenLastCalledWith(
    expect.objectContaining({
      query: expect.objectContaining({ person: undefined, selectedPerson: undefined }),
    }),
  )
  wrapper.unmount()
})

// Render the real card and hold requests open to exercise concurrency.
describe('detection mutation coordination', () => {
  it('shares pending/error state between the card and People assignment', async () => {
    faces.value = faces.value.map((item) => ({ ...item, linkState: 'manual' }))
    let rejectVerification!: (error: Error) => void
    mocks.patchFace.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectVerification = reject
        }),
    )
    const wrapper = await mountView(true)
    const card = () => wrapper.findComponent({ name: 'SelectedFaceItem' })
    const candidates = wrapper.findComponent({ name: 'ScanPeoplePanel' })
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    await card().get('[aria-label="Verify this link"]').trigger('click')
    await flushPromises()
    expect(mocks.patchFace).toHaveBeenCalledTimes(1)
    // Search remains available; every assignment action waits.
    for (const button of card().findAll('button[aria-label]'))
      if (!['Search people by this face', 'Close'].includes(button.attributes('aria-label')!))
        expect(button.attributes('disabled')).toBeDefined()
    expect(candidates.props('assignmentPending')).toBe(true)
    // Stale events cannot bypass the guard at the mutation boundary.
    candidates.vm.$emit('assign', { id: 'someone-else' })
    card().vm.$emit('unassign')
    card().vm.$emit('createProfile', { name: 'New person' })
    card().vm.$emit('delete')
    await flushPromises()
    expect(mocks.assignFace).not.toHaveBeenCalled()
    expect(mocks.unassignFace).not.toHaveBeenCalled()
    expect(mocks.createAndAssign).not.toHaveBeenCalled()
    expect(mocks.deleteFace).not.toHaveBeenCalled()
    expect(mocks.patchFace).toHaveBeenCalledTimes(1)
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
    rejectVerification(new Error('Forbidden'))
    await flushPromises()
    expect(card().text()).toContain('Could not verify link.')
    expect(candidates.props('assignmentPending')).toBe(false)
    expect(card().get('[aria-label="Verify this link"]').attributes('disabled')).toBeUndefined()
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'b')
    await flushPromises()
    expect(card().text()).not.toContain('Could not verify link.')
    mocks.patchFace.mockResolvedValueOnce({ data: {} })
    await card().get('[aria-label="Verify this link"]').trigger('click')
    await flushPromises()
    expect(mocks.patchFace).toHaveBeenLastCalledWith({
      path: { detection_id: 'b' },
      body: { entity_link_state: 'verified' },
      throwOnError: true,
    })
    expect(candidates.props('assignmentPending')).toBe(false)
    wrapper.unmount()
  })

  it('disables Verify during assignment, creation and deletion', async () => {
    faces.value = faces.value.map((item) => ({ ...item, linkState: 'manual' }))
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    const card = () => wrapper.findComponent({ name: 'SelectedFaceItem' })
    const candidates = wrapper.findComponent({ name: 'ScanPeoplePanel' })
    const expectBusy = () => {
      expect(card().get('[aria-label="Verify this link"]').attributes('disabled')).toBeDefined()
      expect(candidates.props('assignmentPending')).toBe(true)
    }
    assignmentStatus.value = 'pending'
    await flushPromises()
    expectBusy()
    assignmentStatus.value = 'idle'
    await flushPromises()
    let finishCreation!: (entity: { entity_id: string }) => void
    mocks.createAndAssign.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishCreation = resolve
        }),
    )
    card().vm.$emit('createProfile', { name: 'New person' })
    await flushPromises()
    expectBusy()
    finishCreation({ entity_id: 'new-person' })
    await flushPromises()
    expect(candidates.props('assignmentPending')).toBe(false)
    let rejectDeletion!: (error: Error) => void
    mocks.deleteFace.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectDeletion = reject
        }),
    )
    card().vm.$emit('delete')
    await flushPromises()
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    expect(candidates.props('assignmentPending')).toBe(true)
    rejectDeletion(new Error('Forbidden'))
    await flushPromises()
    expect(candidates.props('assignmentPending')).toBe(false)
    expect(mocks.patchFace).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('teleprompter focus modes (#36)', () => {
  function threeLines() {
    lines.value = ['l1', 'l2', 'l3'].map((id, index) => ({
      id,
      text: index === 1 ? 'Plain context' : 'Ada',
      position: { ...box, top: 20 + index * 30 },
      // Verified on L1 and L3, so a Verified filter keeps both.
      entities: index === 1 ? [] : [{ ...span(id), linkState: 'verified' as const }],
    }))
  }

  it('narrows Annotated lines to the chosen annotation states, keeping the mode', async () => {
    route.query = { lines: 'annotated' }
    threeLines()
    lines.value[2]!.entities = [{ ...span('l3'), linkState: 'manual' }]
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    expect(teleprompter.props('included')).toEqual([true, false, true])
    teleprompter.vm.$emit('update:annotationHighlight', ['manual'])
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('annotated')
    expect(teleprompter.props('included')).toEqual([false, false, true])
    // The selection moves from the now hidden L1 to the nearest matching line.
    expect(teleprompter.props('selectedLineIndex')).toBe(2)
    teleprompter.vm.$emit('update:annotationHighlight', [])
    await flushPromises()
    expect(teleprompter.props('included')).toEqual([true, false, true])
    wrapper.unmount()
  })

  it('restores Person mode from the URL and navigates only its visible lines', async () => {
    route.query = { lines: 'person', highlight: 'verified', selectedPerson: 'ada' }
    threeLines()
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    expect(teleprompter.props('lineVisibility')).toBe('person')
    expect(teleprompter.props('annotationHighlight')).toEqual(['verified'])
    expect(teleprompter.props('included')).toEqual([true, false, true])
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await flushPromises()
    expect(teleprompter.props('selectedLineIndex')).toBe(2)
    expect(mocks.replace).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({ line: 'l3', lines: 'person', highlight: ['verified'] }),
      }),
    )
    // Keyboard navigation stops at the last visible line and skips hidden ones.
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await flushPromises()
    expect(teleprompter.props('selectedLineIndex')).toBe(2)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp' }))
    await flushPromises()
    expect(teleprompter.props('selectedLineIndex')).toBe(0)
    wrapper.unmount()
  })

  it('reveals a hidden overlay line as Custom; choosing the mode again moves to the nearest line', async () => {
    route.query = { lines: 'annotated' }
    threeLines()
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    wrapper.findComponent({ name: 'DocumentPageOverlay' }).vm.$emit('select-line', 1)
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('custom')
    expect(teleprompter.props('included')).toEqual([true, true, true])
    expect(teleprompter.props('selectedLineIndex')).toBe(1)
    // A Custom view is not shareable; the URL keeps the mode it came from.
    expect(mocks.replace).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({ lines: 'annotated', line: 'l2' }),
      }),
    )
    teleprompter.vm.$emit('update:lineVisibility', 'annotated')
    await flushPromises()
    expect(teleprompter.props('included')).toEqual([true, false, true])
    expect(teleprompter.props('selectedLineIndex')).toBe(0)
    wrapper.unmount()
  })

  it('keeps Custom when the URL updates to its base mode, but applies a different mode', async () => {
    route.query = { lines: 'annotated' }
    threeLines()
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    teleprompter.vm.$emit('expand', { start: 0, end: 0 }, 'after', 1)
    await flushPromises()
    // The router echoes the synced query back, as a real navigation would.
    route.query = { ...route.query, lines: 'annotated', line: 'l1' }
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('custom')
    route.query = { ...route.query, lines: 'person' }
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('person')
    wrapper.unmount()
  })

  it('keeps Custom lines when another person is selected', async () => {
    route.query = { lines: 'person', selectedPerson: 'ada' }
    threeLines()
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    teleprompter.vm.$emit('expand', { start: 0, end: 0 }, 'after', 1)
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('custom')
    expect(teleprompter.props('included')).toEqual([true, true, true])
    wrapper.findComponent({ name: 'DocumentPageOverlay' }).vm.$emit('select-face', 'b')
    await flushPromises()
    expect(teleprompter.props('included')).toEqual([true, true, true])
    expect(teleprompter.props('lineVisibility')).toBe('custom')
    wrapper.unmount()
  })

  it('restores a URL line hidden by the mode at the nearest visible line', async () => {
    route.query = { lines: 'annotated', line: 'l2' }
    lines.value = []
    const wrapper = await mountView()
    threeLines()
    await flushPromises()
    // L2 is unannotated; L1 and L3 are equally near, so the earlier line wins.
    expect(wrapper.findComponent({ name: 'DocumentTeleprompter' }).props('selectedLineIndex')).toBe(
      0,
    )
    wrapper.unmount()
  })

  it('leaves Custom when a mode is chosen and keeps the empty Person mode', async () => {
    threeLines()
    const wrapper = await mountView()
    const teleprompter = wrapper.findComponent({ name: 'DocumentTeleprompter' })
    teleprompter.vm.$emit('update:lineVisibility', 'annotated')
    await flushPromises()
    teleprompter.vm.$emit('expand', { start: 0, end: 0 }, 'after', 1)
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('custom')
    teleprompter.vm.$emit('update:lineVisibility', 'person')
    await flushPromises()
    expect(teleprompter.props('lineVisibility')).toBe('person')
    // No selected person: no fallback to full text.
    expect(teleprompter.props('included')).toEqual([false, false, false])
    wrapper.unmount()
  })
})

describe('resizable transcription panel (#36)', () => {
  it.each([
    [true, 'horizontal'],
    [false, 'vertical'],
  ])(
    'splits beside the scan when wide=%s (%s), keeping the transcription first',
    async (wide, direction) => {
      const matchMedia = window.matchMedia
      window.matchMedia = vi.fn().mockReturnValue({
        matches: wide,
        media: '(min-width: 1024px)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
      }) as unknown as typeof window.matchMedia
      try {
        const wrapper = await mountView()
        const group = wrapper.get('.workspace-split > div')
        expect(group.attributes('direction')).toBe(direction)
        const panels = group.element.children
        // Transcription first (left or top), then the handle, then the scan.
        expect(panels[0]!.querySelector('[aria-label="Transcription"]')).not.toBeNull()
        expect(panels[2]!.querySelector('[aria-label="Pan and zoom document page"]')).not.toBeNull()
        wrapper.unmount()
      } finally {
        window.matchMedia = matchMedia
      }
    },
  )
})

describe('resizable scan sidebar (#121)', () => {
  it.each([true, false])('offers a sidebar handle only when wide=%s', async (wide) => {
    const matchMedia = window.matchMedia
    window.matchMedia = vi.fn().mockReturnValue({
      matches: wide,
      media: '(min-width: 1024px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    }) as unknown as typeof window.matchMedia
    try {
      const wrapper = await mountView()
      const layout = wrapper.get('main > .workspace-layout')
      const children = [...layout.element.children]
      // The workspace comes first, then (when wide) the handle, then the sidebar.
      expect(children[0]!.querySelector('.workspace-split')).not.toBeNull()
      expect(children[children.length - 1]!.querySelector('.workspace-sidebar')).not.toBeNull()
      const handle = layout.find('resizable-handle-stub[aria-label="Resize sidebar"]')
      expect(handle.exists()).toBe(wide)
      wrapper.unmount()
    } finally {
      window.matchMedia = matchMedia
    }
  })
})

it('keeps the live scan and its actions through repeated responsive round trips', async () => {
  const original = window.matchMedia
  const module = await import('@panzoom/panzoom')
  const initialize = vi.spyOn(module, 'default')
  let wide = true
  let listener: ((event: { matches: boolean; media: string }) => void) | undefined
  window.matchMedia = vi.fn((query: string) => ({
    get matches() {
      return query.includes('1024') && wide
    },
    media: query,
    addEventListener: (_: string, callback: typeof listener) => {
      if (query.includes('1024')) listener = callback
    },
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
  const wrapper = await mountView()
  try {
    const element = wrapper.get('.panzoom-layer').element
    const viewer = wrapper.get('.workspace-viewer').element
    for (let pass = 0; pass < 3; pass++) {
      for (const value of [false, true]) {
        wide = value
        listener?.({ matches: value, media: '(min-width: 1024px)' })
        await settleFocus()
        expect(wrapper.get('.panzoom-layer').element).toBe(element)
        expect(wrapper.get('.workspace-viewer').element).toBe(viewer)
        wrapper.findComponent({ name: 'DocumentControls' }).vm.$emit('set-zoom', 'in')
        viewer.dispatchEvent(new WheelEvent('wheel'))
      }
    }
    expect(initialize).toHaveBeenCalledTimes(1)
    expect(initialize.mock.calls[0]![0]).toBe(element)
    expect(mocks.zoomIn).toHaveBeenCalledTimes(6)
    expect(mocks.zoomWithWheel).toHaveBeenCalledTimes(6)
  } finally {
    wrapper.unmount()
    window.matchMedia = original
    initialize.mockRestore()
  }
})

describe('scan sidebar (#103)', () => {
  const lastQuery = (navigate: typeof mocks.push) =>
    (navigate.mock.lastCall?.[0] as { query: Record<string, unknown> }).query

  it('orders People, Faces, Mentions and Info and opens People by default', async () => {
    const wrapper = await mountView()
    const tabs = wrapper.findComponent({ name: 'Tabs' })
    expect(
      wrapper.findAllComponents({ name: 'TabsTrigger' }).map((tab) => tab.props('value')),
    ).toEqual(['people', 'faces', 'mentions', 'info'])
    expect(tabs.props('modelValue')).toBe('people')
    // Former Activity and Statistics links open Info.
    route.query = { panel: 'statistics' }
    await flushPromises()
    expect(tabs.props('modelValue')).toBe('info')
    tabs.vm.$emit('update:modelValue', 'faces')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({ panel: 'faces' })
    wrapper.unmount()
  })

  it('searches by the selected face: one attachment, no name text, global Similarity', async () => {
    route.query = {
      people_scope: 'document',
      candidate_text: 'Novak',
      candidate_face: 'previous',
      panel: 'faces',
    }
    faces.value = faces.value.map((item) => ({ ...item, embeddingModel: 'model' }))
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    // Ordinary selection leaves the attached search face alone.
    expect(mocks.push).not.toHaveBeenCalled()
    expect(lastQuery(mocks.replace)).toMatchObject({ person: 'a', candidate_face: 'previous' })
    await wrapper
      .findComponent({ name: 'SelectedFaceItem' })
      .get('[aria-label="Search people by this face"]')
      .trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledTimes(1)
    expect(lastQuery(mocks.push)).toMatchObject({
      panel: undefined,
      candidate_face: 'a',
      candidate_text: undefined,
      candidate_sort: undefined,
      people_scope: undefined,
    })
    // Unlike Link/Reassign, Search leaves focus where it is, even once People opens.
    route.query = { ...route.query, panel: undefined } as unknown as Record<string, string>
    await flushPromises()
    expect(mocks.focusPeople).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('searches all people while a name or face search is active, keeping the stored scope', async () => {
    route.query = { people_scope: 'page' }
    const wrapper = await mountView()
    const people = () => wrapper.findComponent({ name: 'ScanPeoplePanel' })
    expect(people().props('scope')).toBe('page')
    route.query = { people_scope: 'page', candidate_text: 'Ada' }
    await flushPromises()
    expect(people().props('scope')).toBe('all')
    route.query = { people_scope: 'page', candidate_face: 'a' }
    await flushPromises()
    expect(people().props('scope')).toBe('all')
    route.query = { people_scope: 'page' }
    await flushPromises()
    expect(people().props('scope')).toBe('page')
    wrapper.unmount()
  })

  it('attaches the selected face from the People context menu', async () => {
    route.query = { candidate_text: 'Ada' }
    faces.value = faces.value.map((item) => ({ ...item, embeddingModel: 'model' }))
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'b')
    await flushPromises()
    wrapper.findComponent({ name: 'ScanPeoplePanel' }).vm.$emit('attach-selected-face')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({
      candidate_face: 'b',
      candidate_text: undefined,
      candidate_sort: undefined,
      people_scope: undefined,
    })
    wrapper.unmount()
  })

  it('opens People search for Link and keeps typed text when the face is removed', async () => {
    route.query = { panel: 'info', candidate_face: 'a', candidate_sort: 'relevance' }
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    wrapper.findComponent({ name: 'SelectedFaceItem' }).vm.$emit('findProfile')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({ panel: undefined, candidate_face: 'a' })
    // The mocked router leaves the route as it was; apply the tab change.
    route.query = { ...route.query, panel: undefined } as unknown as Record<string, string>
    await flushPromises()
    expect(mocks.focusPeople).toHaveBeenCalledTimes(1)
    const people = wrapper.findComponent({ name: 'ScanPeoplePanel' })
    // Without a name or face to score, Similarity falls back to context order.
    people.vm.$emit('remove-face')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({
      candidate_face: undefined,
      candidate_sort: undefined,
    })
    route.query = { candidate_face: 'a', candidate_sort: 'relevance', candidate_text: 'Ada' }
    await flushPromises()
    people.vm.$emit('remove-face')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({
      candidate_face: undefined,
      candidate_sort: 'relevance',
      candidate_text: 'Ada',
    })
    wrapper.unmount()
  })
})

it('selects a mention requested from the Mentions tab on its own, revealed line (#103)', async () => {
  // Spans match recorded text, so mention m9 also matches the first line.
  lines.value = ['l1', 'l2', 'l3'].map((id, index) => ({
    id,
    text: index === 1 ? 'Plain context' : index === 0 ? 'Ada opened' : 'Ada wrote',
    position: { ...box, top: 20 + index * 50 },
    entities: index === 1 ? [] : [{ ...span(id), mention_id: 'm9', occurrence: `m9:${id}:0` }],
  }))
  mocks.mention.mockResolvedValue({
    data: { mention_id: 'm9', name: 'Ada', context: 'Ada wrote', entity_id: 'ada' },
  })
  // Person mode for someone else hides the requested line until it is selected.
  route.query = { mention: 'm9', lines: 'person', selectedPerson: 'nobody' }
  const wrapper = await mountView()
  await settleFocus()
  const transcription = wrapper.findComponent({ name: 'DocumentTeleprompter' })
  expect(transcription.props('selectedLineIndex')).toBe(2)
  expect(transcription.props('selectedEntityKey')).toBe('m9:l3:0')
  expect(transcription.props('included')[2]).toBe(true)
  expect(mocks.replace).toHaveBeenLastCalledWith(
    expect.objectContaining({
      query: expect.objectContaining({ mention: undefined, line: 'l3', selectedPerson: 'ada' }),
    }),
  )
  wrapper.unmount()
})

it('selects the line of an unlinked mention requested from the Mentions tab (#103)', async () => {
  mocks.mention.mockResolvedValue({
    data: { mention_id: 'loose', name: 'Ada', context: 'Ada', entity_id: null },
  })
  route.query = { mention: 'loose' }
  const wrapper = await mountView()
  await settleFocus()
  const transcription = wrapper.findComponent({ name: 'DocumentTeleprompter' })
  expect(transcription.props('selectedLineIndex')).toBe(0)
  expect(transcription.props('selectedEntityKey')).toBeNull()
  expect(mocks.replace).toHaveBeenLastCalledWith(
    expect.objectContaining({ query: expect.objectContaining({ mention: undefined }) }),
  )
  wrapper.unmount()
})

describe('face search with an unusable reference (#134)', () => {
  it('drops the face and lists people on this page, the document, then everyone', async () => {
    mocks.documentLookup.mockReturnValue({
      isPending: ref(false),
      error: ref(null),
      data: ref({ source_id: 'document-source' }),
    })
    // The face record lists its model, but the stored vector is all zeros.
    mocks.getFace.mockResolvedValue({ data: { detection_id: 'zero', embeddings: ['model'] } })
    mocks.searchEntities.mockRejectedValue(
      new AxiosError('Unprocessable Content', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 422,
        data: {
          detail: {
            code: 'invalid_search',
            message: "reference face has an unusable cosine embedding 'model': zero",
          },
        },
      } as AxiosResponse),
    )
    mocks.listEntities.mockResolvedValue({
      data: { items: [], cursor: null, total_count: 0 },
    })
    // The router commits navigation into the route, like the real one.
    const navigate = ({ query }: { query: Record<string, string | undefined> }) => {
      route.query = Object.fromEntries(
        Object.entries(query).filter((entry): entry is [string, string] => entry[1] !== undefined),
      )
    }
    mocks.push.mockImplementation(navigate)
    mocks.replace.mockImplementation(navigate)
    route.query = { candidate_face: 'zero', candidate_sort: 'relevance' }

    const wrapper = await mountView()
    await settleFocus()

    expect(mocks.searchEntities).toHaveBeenCalledTimes(1)
    // The fallback replaces the Search entry, so Back leaves the page.
    expect(mocks.push).not.toHaveBeenCalled()
    expect(mocks.replace).toHaveBeenCalled()
    expect(route.query.candidate_face).toBeUndefined()
    expect(route.query.candidate_sort).toBeUndefined()
    const scopes = mocks.listEntities.mock.calls.map(([{ query }]) => query)
    expect(scopes).toContainEqual(
      expect.objectContaining({
        'filter.entity_type': ['person'],
        'filter.page_source_id': ['source'],
        sort: 'name',
        sort_direction: 'asc',
      }),
    )
    wrapper.unmount()
  })
})

describe('independent panel visibility (#139)', () => {
  let wide: boolean
  let listeners: ((event: { matches: boolean; media: string }) => void)[]
  let restoreMedia: () => void
  beforeEach(() => {
    wide = true
    listeners = []
    const original = window.matchMedia
    window.matchMedia = vi.fn((query: string) => ({
      get matches() {
        return query.includes('1024') && wide
      },
      media: query,
      addEventListener: (_: string, callback: (typeof listeners)[number]) => {
        if (query.includes('1024')) listeners.push(callback)
      },
      removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia
    restoreMedia = () => {
      window.matchMedia = original
    }
  })
  afterEach(() => restoreMedia())

  it('keeps both panels and the live scan mounted while hidden, with reopen actions in the viewer header', async () => {
    const wrapper = await mountView()
    const viewer = wrapper.get('.workspace-viewer').element
    const transcription = wrapper.findComponent({ name: 'DocumentTeleprompter' }).element
    const sidebar = wrapper.get('.workspace-sidebar').element
    const state = wrapper.vm as unknown as { hidePanel: (side: 'left' | 'right') => void }
    state.hidePanel('left')
    state.hidePanel('right')
    await nextTick()
    expect(wrapper.get('#transcription-panel').attributes('style')).toContain('display: none')
    expect(wrapper.get('#people-panel').attributes('style')).toContain('display: none')
    // The splitter may expand internally as responsive constraints change; only
    // an explicit reopen action should reveal the user's hidden content.
    wrapper
      .findAllComponents({ name: 'ResizablePanel' })
      .forEach((panel) => panel.vm.$emit('expand'))
    await nextTick()
    expect(wrapper.get('#transcription-panel').attributes('style')).toContain('display: none')
    expect(wrapper.get('#people-panel').attributes('style')).toContain('display: none')
    const bar = wrapper.get('header.viewer-tools')
    expect(bar.find('[aria-label="Open transcription panel"]').exists()).toBe(true)
    expect(bar.find('[aria-label="Open people panel"]').exists()).toBe(true)
    await bar.get('[aria-label="Open transcription panel"]').trigger('click')
    await bar.get('[aria-label="Open people panel"]').trigger('click')
    expect(wrapper.get('.workspace-viewer').element).toBe(viewer)
    expect(wrapper.findComponent({ name: 'DocumentTeleprompter' }).element).toBe(transcription)
    expect(wrapper.get('.workspace-sidebar').element).toBe(sidebar)
    expect(wrapper.get('#transcription-panel').attributes('style') ?? '').not.toContain(
      'display: none',
    )
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(
      wrapper.get('.workspace-viewer').findComponent({ name: 'DocumentControls' }).exists(),
    ).toBe(false)
    wrapper.unmount()
  })

  it('collapses mobile transcription into its labelled bar while keeping People visible', async () => {
    wide = false
    const wrapper = await mountView(true)
    const viewer = wrapper.get('.workspace-viewer').element
    const bar = wrapper.get('header:has([aria-label="Hide transcription panel"])')
    expect(bar.text()).toContain('Transcription')
    expect(wrapper.find('[aria-label="Hide people panel"]').exists()).toBe(false)
    await bar.get('[aria-label="Hide transcription panel"]').trigger('click')
    expect(bar.get('[aria-label="Open transcription panel"]').attributes('aria-expanded')).toBe(
      'false',
    )
    expect(bar.text()).toContain('Transcription')
    expect(wrapper.get('#transcription-panel').attributes('style')).toContain('display: none')
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(
      wrapper.get('header.viewer-tools').find('[aria-label="Open transcription panel"]').exists(),
    ).toBe(false)
    await bar.get('[aria-label="Open transcription panel"]').trigger('click')
    expect(wrapper.get('#transcription-panel').attributes('style') ?? '').not.toContain(
      'display: none',
    )
    expect(wrapper.get('.workspace-viewer').element).toBe(viewer)
    wrapper.unmount()
  })

  it('shows the stacked People section even when its desktop panel was hidden', async () => {
    const wrapper = await mountView()
    const state = wrapper.vm as unknown as { hidePanel: (side: 'left' | 'right') => void }
    state.hidePanel('right')
    await nextTick()
    expect(wrapper.get('#people-panel').attributes('style')).toContain('display: none')
    wide = false
    listeners.forEach((listener) => listener({ matches: false, media: '(min-width: 1024px)' }))
    await flushPromises()
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(wrapper.find('[aria-label="Hide people panel"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Open people panel"]').exists()).toBe(false)
    state.hidePanel('right')
    await nextTick()
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    wide = true
    listeners.forEach((listener) => listener({ matches: true, media: '(min-width: 1024px)' }))
    await flushPromises()
    expect(wrapper.get('#people-panel').attributes('style')).toContain('display: none')
    await wrapper.get('[aria-label="Open people panel"]').trigger('click')
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    wrapper.unmount()
  })

  it('reveals a hidden People panel for Link and explicit face Search', async () => {
    faces.value = faces.value.map((item) => ({ ...item, embeddingModel: 'model' }))
    const wrapper = await mountView(true)
    const state = wrapper.vm as unknown as { hidePanel: (side: 'left' | 'right') => void }
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    state.hidePanel('right')
    await nextTick()
    wrapper.findComponent({ name: 'SelectedFaceItem' }).vm.$emit('findProfile')
    await flushPromises()
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(mocks.focusPeople).toHaveBeenCalledTimes(1)
    state.hidePanel('right')
    await nextTick()
    await wrapper
      .findComponent({ name: 'SelectedFaceItem' })
      .get('[aria-label="Search people by this face"]')
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('#people-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(mocks.focusPeople).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})

describe('scan name mentions and their person card (#176)', () => {
  const lastQuery = (navigate: typeof mocks.push) =>
    (navigate.mock.lastCall?.[0] as { query: Record<string, unknown> }).query
  const mention = (id: string, line_id: string, start: number, text: string, extra = {}) => ({
    mention_id: id,
    occurrence: `${id}:${line_id}:${start}`,
    line_id,
    label: 'person' as const,
    text,
    start_index: start,
    end_index: start + text.length,
    linkState: null,
    verifiedBy: null,
    verifiedAt: null,
    ...extra,
  })
  const m1 = mention('m1', 'l1', 0, 'Jan Bulk', { entity_id: 'jan', linkState: 'automatic' })
  const m2 = mention('m2', 'l2', 0, 'Eva')
  const m3 = mention('m3', 'l2', 8, 'Jan Bulk', { entity_id: 'jan', linkState: 'verified' })

  beforeEach(() => {
    lines.value = [
      { id: 'l1', text: 'Jan Bulk wrote', position: box, entities: [m1] },
      { id: 'l2', text: 'Eva and Jan Bulk', position: { ...box, top: 70 }, entities: [m2, m3] },
    ]
    const workspace = mocks.workspace()
    mocks.workspace.mockReturnValue({
      ...workspace,
      entityNames: ref(new Map([['jan', 'Jan Bulk']])),
    })
    mocks.patchMentions.mockImplementation(({ body }) =>
      Promise.resolve({ data: body.map((item: object) => ({ ...item, name: 'x' })) }),
    )
  })
  const teleprompter = (wrapper: Awaited<ReturnType<typeof mountView>>) =>
    wrapper.findComponent({ name: 'DocumentTeleprompter' })
  const mentionCard = (wrapper: Awaited<ReturnType<typeof mountView>>) =>
    wrapper.findAllComponents({ name: 'SelectedFaceItem' }).find((card) => card.props('mentions'))
  async function choose(
    wrapper: Awaited<ReturnType<typeof mountView>>,
    index: number,
    span: typeof m1,
    mode = 'replace',
  ) {
    teleprompter(wrapper).vm.$emit('select-entity', index, span, mode)
    await flushPromises()
  }

  it('selects one mention, toggles and ranges across lines, beside an independent face', async () => {
    const wrapper = await mountView(true, true)
    wrapper.findComponent({ name: 'ScanFacesPanel' }).vm.$emit('select', 'a')
    await flushPromises()
    await choose(wrapper, 0, m1)
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m1'])
    expect(teleprompter(wrapper).props('selectedEntityKey')).toBe('m1:l1:0')
    expect(lastQuery(mocks.replace)).toMatchObject({
      person: 'a',
      selectedPerson: 'jan',
      line: 'l1',
    })
    // The face keeps its own card; the mention gets the shared person card.
    const cards = wrapper.findAllComponents({ name: 'SelectedFaceItem' })
    expect(cards.map((card) => Boolean(card.props('face')))).toEqual([false, true])
    expect(mentionCard(wrapper)!.props('mentions')).toMatchObject({
      ids: ['m1'],
      texts: ['Jan Bulk'],
      personId: 'jan',
      name: 'Jan Bulk',
      linkState: 'automatic',
      anyUnverified: true,
    })
    // Ctrl adds m3 and moves the anchor; Shift from m3 back to m1 covers m2 on the next line.
    await choose(wrapper, 1, m3, 'toggle')
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m1', 'm3'])
    await choose(wrapper, 0, m1, 'range')
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m1', 'm2', 'm3'])
    // The scan marks each selected mention's line, without the person's other lines.
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    expect(overlay.attributes('selected-mention-lines')).toBe('0,1')
    expect(overlay.attributes('selected-person-id')).toBeUndefined()
    expect(mentionCard(wrapper)!.props('mentions')).toMatchObject({
      texts: ['Jan Bulk', 'Eva'],
      personId: null,
      mixed: true,
      linkState: null,
    })
    // Toggling the clicked mention off leaves the others.
    await choose(wrapper, 0, m1, 'toggle')
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m2', 'm3'])
    expect(teleprompter(wrapper).props('selectedEntityKey')).toBeNull()
    // Escape (or an empty click) clears the mentions; the face stays selected.
    teleprompter(wrapper).vm.$emit('clear-mentions')
    await flushPromises()
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual([])
    expect(mentionCard(wrapper)).toBeUndefined()
    expect(wrapper.findComponent({ name: 'SelectedFaceItem' }).props('face')).toMatchObject({
      id: 'a',
    })
    expect(lastQuery(mocks.replace)).toMatchObject({ person: 'a', selectedPerson: 'ada' })
    // People gets both targets with permission to assign.
    await choose(wrapper, 1, m2)
    const people = wrapper.findComponent({ name: 'ScanPeoplePanel' })
    expect(people.attributes()).toMatchObject({ 'can-assign': 'true' })
    expect(teleprompter(wrapper).props('canCreateMention')).toBe(true)
    expect(teleprompter(wrapper).props('canChangeMention')).toBe(true)
    wrapper.unmount()
  })

  it('assigns, unlinks, verifies, searches and deletes all selected mentions in batches', async () => {
    const wrapper = await mountView(true, true)
    await choose(wrapper, 0, m1)
    await choose(wrapper, 1, m3, 'range')
    const people = wrapper.findComponent({ name: 'ScanPeoplePanel' })
    people.vm.$emit('assignMentions', { id: 'ada' })
    await flushPromises()
    expect(mocks.patchMentions).toHaveBeenLastCalledWith({
      body: ['m1', 'm2', 'm3'].map((mention_id) => ({
        mention_id,
        entity_id: 'ada',
        entity_link_state: 'manual',
      })),
      throwOnError: true,
    })
    // Assigning mentions never touches a face.
    expect(mocks.assignFace).not.toHaveBeenCalled()
    await mentionCard(wrapper)!.get('[aria-label="Unassign current profile"]').trigger('click')
    await flushPromises()
    expect(mocks.patchMentions.mock.lastCall![0].body).toEqual(
      ['m1', 'm2', 'm3'].map((mention_id) => ({
        mention_id,
        entity_id: null,
        entity_link_state: null,
      })),
    )
    // Verify skips unlinked and already verified mentions.
    await mentionCard(wrapper)!.get('[aria-label="Verify this link"]').trigger('click')
    await flushPromises()
    expect(mocks.patchMentions.mock.lastCall![0].body).toEqual([
      { mention_id: 'm1', entity_link_state: 'verified' },
    ])
    // Search fills People with the distinct names and drops an attached face.
    await mentionCard(wrapper)!.get('[aria-label="Search people by these names"]').trigger('click')
    await flushPromises()
    expect(lastQuery(mocks.push)).toMatchObject({
      candidate_text: 'Jan Bulk Eva',
      candidate_face: undefined,
      panel: undefined,
    })
    // Delete confirms first, then deletes every selected mention at once.
    mocks.deleteMentions.mockResolvedValueOnce({ data: 3 })
    await mentionCard(wrapper)!.get('[aria-label="Delete mentions"]').trigger('click')
    await flushPromises()
    expect(mocks.deleteMentions).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    expect(wrapper.text()).toContain('Delete 3 mentions?')
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    expect(mocks.deleteMentions).toHaveBeenCalledWith({
      body: ['m1', 'm2', 'm3'],
      throwOnError: true,
    })
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual([])
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
    wrapper.unmount()
  })

  it('reports a failed update and keeps the selection', async () => {
    const wrapper = await mountView(true, true)
    await choose(wrapper, 1, m2)
    mocks.patchMentions.mockRejectedValueOnce(new Error('Forbidden'))
    wrapper.findComponent({ name: 'ScanPeoplePanel' }).vm.$emit('assignMentions', { id: 'ada' })
    await flushPromises()
    expect(mentionCard(wrapper)!.text()).toContain('Could not update link.')
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m2'])
    wrapper.unmount()
  })

  it('creates a person through PUT /people, links every mention and retries without a duplicate', async () => {
    const uuid = vi.spyOn(crypto, 'randomUUID')
    uuid.mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
    mocks.putPerson.mockImplementation(({ path, body }) =>
      Promise.resolve({ data: { ...body, entity_id: path.entity_id, user_id: 'u' } }),
    )
    const wrapper = await mountView(true, true)
    await choose(wrapper, 0, m1)
    await choose(wrapper, 1, m2, 'toggle')
    mocks.patchMentions.mockRejectedValueOnce(new Error('offline'))
    mentionCard(wrapper)!.vm.$emit('createProfile', { name: 'Jan Bulk', shortDescription: 'Clerk' })
    await flushPromises()
    expect(mentionCard(wrapper)!.text()).toContain('Could not create and link the person.')
    mentionCard(wrapper)!.vm.$emit('createProfile', { name: 'Jan Bulk' })
    await flushPromises()
    expect(mocks.putPerson.mock.calls.map(([options]) => options.path.entity_id)).toEqual([
      '11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111',
    ])
    expect(mocks.putPerson.mock.calls[0]![0].body).toEqual({
      entity_type: 'person',
      name: 'Jan Bulk',
      short_description: 'Clerk',
    })
    expect(mocks.patchMentions.mock.lastCall![0].body).toEqual(
      ['m1', 'm2'].map((mention_id) => ({
        mention_id,
        entity_id: '11111111-1111-4111-8111-111111111111',
        entity_link_state: 'manual',
      })),
    )
    expect(uuid).toHaveBeenCalledTimes(1)
    expect(lastQuery(mocks.replace)).toMatchObject({
      selectedPerson: '11111111-1111-4111-8111-111111111111',
    })
    uuid.mockRestore()
    wrapper.unmount()
  })

  it('creates an unlinked mention from selected text and selects it once its span appears', async () => {
    mocks.createMention.mockResolvedValue({ data: { mention_id: 'new', name: 'Eva' } })
    const wrapper = await mountView(true, true)
    teleprompter(wrapper).vm.$emit('create-mention', {
      lineIndex: 1,
      name: 'Eva',
      context: 'Eva and Jan Bulk',
    })
    await flushPromises()
    expect(mocks.createMention).toHaveBeenCalledWith({
      body: { name: 'Eva', context: 'Eva and Jan Bulk', source_id: 'source' },
      throwOnError: true,
    })
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual([])
    const created = mention('new', 'l2', 0, 'Eva')
    lines.value = [lines.value[0]!, { ...lines.value[1]!, entities: [created, m3] }]
    await flushPromises()
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['new'])
    expect(mentionCard(wrapper)!.props('mentions')).toMatchObject({
      ids: ['new'],
      texts: ['Eva'],
      personId: null,
    })
    // Changing a mention's words keeps its link: only name and context are sent.
    mocks.patchMention.mockResolvedValue({ data: { mention_id: 'm3', name: 'Bulk' } })
    teleprompter(wrapper).vm.$emit('change-mention', {
      mentionId: 'm3',
      name: 'Bulk',
      context: 'Eva and Jan Bulk',
    })
    await flushPromises()
    expect(mocks.patchMention).toHaveBeenCalledWith({
      path: { mention_id: 'm3' },
      body: { name: 'Bulk', context: 'Eva and Jan Bulk' },
      throwOnError: true,
    })
    const changed = { ...m3, occurrence: 'm3:l2:12', text: 'Bulk', start_index: 12 }
    lines.value = [lines.value[0]!, { ...lines.value[1]!, entities: [created, changed] }]
    await flushPromises()
    expect(teleprompter(wrapper).props('selectedMentionIds')).toEqual(['m3'])
    expect(teleprompter(wrapper).props('selectedEntityKey')).toBe('m3:l2:12')
    wrapper.unmount()
  })

  it('merges overlapped mentions into the verified one after confirmation', async () => {
    mocks.patchMention.mockResolvedValue({ data: { mention_id: 'm3' } })
    mocks.deleteMentions.mockResolvedValue({ data: 2 })
    const wrapper = await mountView(true, true)
    expect(teleprompter(wrapper).props('canMergeMentions')).toBe(true)
    teleprompter(wrapper).vm.$emit('merge-mentions', {
      mentionIds: ['m1', 'm2', 'm3'],
      name: 'Jan Bulk wrote Eva and Jan Bulk',
      context: 'Jan Bulk wrote\nEva and Jan Bulk',
    })
    await flushPromises()
    // Nothing is written before the confirmation.
    expect(mocks.patchMention).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    expect(wrapper.text()).toContain('Merge 3 mentions?')
    expect(wrapper.text()).toContain('It keeps the link to Jan Bulk.')
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    // m3 is the verified one: it takes the words, then the others are deleted.
    expect(mocks.patchMention).toHaveBeenCalledWith({
      path: { mention_id: 'm3' },
      body: {
        name: 'Jan Bulk wrote Eva and Jan Bulk',
        context: 'Jan Bulk wrote\nEva and Jan Bulk',
      },
      throwOnError: true,
    })
    expect(mocks.deleteMentions).toHaveBeenCalledWith({ body: ['m1', 'm2'], throwOnError: true })
    expect(mocks.patchMention.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.deleteMentions.mock.invocationCallOrder[0]!,
    )
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
    wrapper.unmount()
  })

  it('keeps every mention when the merge change fails', async () => {
    mocks.patchMention.mockRejectedValue(new Error('offline'))
    const wrapper = await mountView(true, true)
    teleprompter(wrapper).vm.$emit('merge-mentions', {
      mentionIds: ['m2', 'm1'],
      name: 'x',
      context: 'y',
    })
    await flushPromises()
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    // The linked m1 was chosen over the unlinked m2; nothing was deleted.
    expect(mocks.patchMention.mock.calls[0]![0].path).toEqual({ mention_id: 'm1' })
    expect(mocks.deleteMentions).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Could not merge mention.')
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    wrapper.unmount()
  })

  it('reports a failed mention creation', async () => {
    mocks.createMention.mockRejectedValue(new Error('Forbidden'))
    const wrapper = await mountView(true, true)
    teleprompter(wrapper).vm.$emit('create-mention', { lineIndex: 0, name: 'Jan', context: 'x' })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Could not create mention.')
    wrapper.unmount()
  })
})
