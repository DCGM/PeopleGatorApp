import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { mount, shallowMount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { reactive, ref, nextTick, type Ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
}))
vi.mock('@/composables/can-annotate', () => ({
  useCanAnnotate: () => ref(true),
  useCanDeleteDetection: () => ref(true),
}))
vi.mock('@/composables/link-state-filter', () => ({ useLinkStateFilter: () => ref([]) }))
vi.mock('@/query/media', () => ({
  useDocumentLookupQuery: () => ({ isPending: ref(false), error: ref(null), data: ref(null) }),
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
  mocks.gallery.mockReturnValue({
    items: ref([]),
    totalCount: ref(null),
    isLoading: ref(false),
    error: ref(null),
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
async function mountView(renderActions = false) {
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
              // Like the real overlay: one card, for the selected face only.
              DocumentPageOverlay: {
                name: 'DocumentPageOverlay',
                props: ['faces', 'selectedFaceId', 'actionsEnabled'],
                template: `<div><template v-for="face in faces" :key="face.id"><slot
                  v-if="actionsEnabled && face.id === selectedFaceId" name="card" :face="face"
                /></template></div>`,
              },
              DocumentTeleprompter: true,
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
  it('focuses gallery, overlay, toolbar and keyboard face selections, including reselection', async () => {
    const wrapper = await mountView()
    for (const component of ['ScanFacesPanel', 'DocumentPageOverlay']) {
      wrapper
        .findComponent({ name: component })
        .vm.$emit(component === 'ScanFacesPanel' ? 'select' : 'select-face', 'a')
      await settleFocus()
    }
    expect(mocks.pan).toHaveBeenCalledTimes(2)
    wrapper.findComponent({ name: 'DocumentControls' }).vm.$emit('next-face')
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
    const [, , , , order] = mocks.gallery.mock.calls[0]!
    expect(mocks.gallery.mock.calls[0]).toHaveLength(5)
    expect(order.value).toEqual({ field: 'page_number', direction: 'asc' })
    const location = wrapper.findComponent({ name: 'DocumentPageGallery' }).props('location')
    route.query = { person: 'a', line: 'l2', link_state: 'manual', page_link_state: 'verified' }
    expect(location({ library: 'lib', documentId: 'doc', pageId: 'two' })).toEqual({
      name: 'document-page',
      params: { libraryId: 'lib', documentId: 'doc', pageId: 'two' },
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
      if (button.attributes('aria-label') !== 'Search people by this face')
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
    // Toolbar navigation counts and boundaries follow the visible sequence.
    const controls = wrapper.findComponent({ name: 'DocumentControls' })
    expect(controls.props('lineCount')).toBe(2)
    expect(controls.props('selectedLineIndex')).toBe(1)
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
        expect(
          panels[0]!.querySelector('[aria-labelledby="page-transcription-title"]'),
        ).not.toBeNull()
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

  it('searches by the selected face: one attachment, no name text, Similarity, same scope', async () => {
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
      candidate_sort: 'relevance',
      people_scope: 'document',
    })
    // Unlike Link/Reassign, Search leaves focus where it is, even once People opens.
    route.query = { ...route.query, panel: undefined } as unknown as Record<string, string>
    await flushPromises()
    expect(mocks.focusPeople).not.toHaveBeenCalled()
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
      candidate_sort: 'relevance',
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
