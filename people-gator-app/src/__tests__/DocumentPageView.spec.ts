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
  reset: vi.fn(),
  gallery: vi.fn(),
  replace: vi.fn(),
  deleteFace: vi.fn(),
  patchFace: vi.fn(),
  assignFace: vi.fn(),
  unassignFace: vi.fn(),
  createAndAssign: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: mocks.route,
  useRouter: () => ({ replace: mocks.replace }),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  deleteFaceRouteApiV1FacesDetectionIdDelete: mocks.deleteFace,
  patchFaceRouteApiV1FacesDetectionIdPatch: mocks.patchFace,
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
    pageDimensions: ref({ width: 800, height: 1100 }),
    similarPeople: ref([]),
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
              DocumentPageOverlay: {
                name: 'DocumentPageOverlay',
                props: ['faces'],
                template: '<div><slot name="actions" :face="faces[0]" /></div>',
              },
              DocumentTeleprompter: true,
              FaceGallery: true,
              LoadableImage: true,
              IdentityFacePreview: true,
              RouterLink: RouterLinkStub,
              SimilarPeopleResults: true,
              SimilarPeopleSearch: true,
              PageActivityPanel: true,
              PageStatisticsPanel: true,
              TabsList: true,
              TabsTrigger: true,
            }
          : {}),
        AlertDialog: { name: 'AlertDialog', props: ['open'], template: '<div><slot /></div>' },
        AlertDialogContent: { template: '<div><slot /></div>' },
        AlertDialogFooter: { template: '<div><slot /></div>' },
        Tabs: { template: '<div><slot /></div>' },
        TabsContent: { template: '<div><slot /></div>' },
      },
    },
  })
  await settleFocus()
  return wrapper
}
describe('evidence selection viewport focus', () => {
  it('focuses gallery, overlay, toolbar and keyboard face selections, including reselection', async () => {
    const wrapper = await mountView()
    for (const component of ['FaceGallery', 'DocumentPageOverlay']) {
      wrapper
        .findComponent({ name: component })
        .vm.$emit(component === 'FaceGallery' ? 'select' : 'select-face', 'a')
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
    const gallery = wrapper.findComponent({ name: 'FaceGallery' })
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
      query: { link_state: 'manual' },
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
    expect(mocks.reset).toHaveBeenCalledWith({ animate: false })
    expect(transcription.props('selectedEntityKey')).toBeNull()
    expect(transcription.props('selectedLineIndex')).toBe(0)
    wrapper.unmount()
  })
})

it('keeps the selected reference and assignment panel when workspace filters hide its gallery entry', async () => {
  route.query = { person: 'a', candidate_mode: 'face' }
  const reference = ref<Face | null>(face('a'))
  mocks.workspace.mockReturnValue({
    ...mocks.workspace.getMockImplementation()!(),
    referenceFace: reference,
  })
  const wrapper = await mountView()
  faces.value = []
  await flushPromises()
  expect(wrapper.findComponent({ name: 'CurrentFacePanel' }).props('face')).toMatchObject({
    id: 'a',
  })
  expect(
    wrapper.findComponent({ name: 'SimilarPeopleSearch' }).props('selectedFace'),
  ).toMatchObject({ id: 'a' })
  expect(route.query.person).toBe('a')
  wrapper.unmount()
})

describe('shared detection actions', () => {
  it('confirms deletion, preserves a rejected detection and clears selection/route only on success', async () => {
    mocks.deleteFace
      .mockRejectedValueOnce(new Error('Forbidden'))
      .mockResolvedValueOnce({ data: null })
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    const card = wrapper.findComponent({ name: 'CurrentFacePanel' })
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    expect(overlay.props('actionsEnabled')).toBe(true)
    card.vm.$emit('delete')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    // The scan actions stay hidden behind the confirmation.
    expect(overlay.props('actionsEnabled')).toBe(false)
    expect(mocks.deleteFace).not.toHaveBeenCalled()
    await wrapper.findComponent({ name: 'Button' }).trigger('click')
    await flushPromises()
    expect(card.props('face')).toMatchObject({ id: 'a' })
    // The dialog alone reports the failure and stays open for a retry.
    expect(card.props('actionError')).toBe('')
    expect(wrapper.text()).toContain('Could not delete detection. Try again.')
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    await wrapper.findComponent({ name: 'Button' }).trigger('click')
    await flushPromises()
    expect(mocks.deleteFace).toHaveBeenLastCalledWith({
      path: { detection_id: 'a' },
      throwOnError: true,
    })
    expect(card.props('face')).toBeNull()
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
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    wrapper.findComponent({ name: 'CurrentFacePanel' }).vm.$emit('delete')
    await flushPromises()
    await wrapper.findComponent({ name: 'Button' }).trigger('click')
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
  it('offers Delete only for a face on this scan, not an off-page reference', async () => {
    referenceFace.value = face('elsewhere')
    route.query = { person: 'elsewhere' }
    const wrapper = await mountView()
    const card = wrapper.findComponent({ name: 'CurrentFacePanel' })
    expect(card.props('face')).toMatchObject({ id: 'elsewhere' })
    expect(card.props('canDelete')).toBe(false)
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    expect(card.props('canDelete')).toBe(true)
    wrapper.unmount()
  })
  it('clears a failed link update when another face is selected', async () => {
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    assignmentError.value = new Error('Forbidden')
    await flushPromises()
    const card = wrapper.findComponent({ name: 'CurrentFacePanel' })
    expect(card.props('actionError')).toBe('Could not update link.')
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'b')
    await flushPromises()
    expect(card.props('actionError')).toBe('')
    wrapper.unmount()
  })
  it('keeps face and line navigation from detection boxes and their actions', async () => {
    const wrapper = await mountView()
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    const container = document.createElement('div')
    container.innerHTML = `
      <button data-region-type="face"></button>
      <div data-detection-actions role="dialog"><button id="action"></button></div>
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

// Render the real action buttons and hold requests open to exercise concurrency.
describe('detection mutation coordination', () => {
  it.each(['CurrentFacePanel', 'DocumentPageOverlay'])(
    'shares pending/error state when Verify starts in %s',
    async (source) => {
      faces.value = faces.value.map((item) => ({ ...item, linkState: 'manual' }))
      let rejectVerification!: (error: Error) => void
      mocks.patchFace.mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectVerification = reject
          }),
      )
      const wrapper = await mountView(true)
      const card = wrapper.findComponent({ name: 'CurrentFacePanel' })
      const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
      const candidates = wrapper.findComponent({ name: 'SimilarPeopleResults' })
      wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
      await flushPromises()
      await wrapper
        .findComponent({ name: source })
        .get('[aria-label="Verify this link"]')
        .trigger('click')
      await flushPromises()
      expect(mocks.patchFace).toHaveBeenCalledTimes(1)
      for (const control of [card, overlay]) {
        for (const button of control.findAll('button[aria-label]')) {
          expect(button.attributes('disabled')).toBeDefined()
        }
      }
      expect(candidates.props('assignmentPending')).toBe(true)
      // Stale events cannot bypass the guard at the mutation boundary.
      candidates.vm.$emit('assign', { id: 'someone-else' })
      card.vm.$emit('unassign')
      card.vm.$emit('create', { name: 'New person' })
      card.vm.$emit('delete')
      overlay.findComponent({ name: 'FaceActionButtons' }).vm.$emit('verify')
      await flushPromises()
      expect(mocks.assignFace).not.toHaveBeenCalled()
      expect(mocks.unassignFace).not.toHaveBeenCalled()
      expect(mocks.createAndAssign).not.toHaveBeenCalled()
      expect(mocks.deleteFace).not.toHaveBeenCalled()
      expect(mocks.patchFace).toHaveBeenCalledTimes(1)
      expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(false)
      rejectVerification(new Error('Forbidden'))
      await flushPromises()
      expect(card.text()).toContain('Could not verify link.')
      expect(overlay.text()).toContain('Could not verify link.')
      expect(candidates.props('assignmentPending')).toBe(false)
      expect(card.get('[aria-label="Verify this link"]').attributes('disabled')).toBeUndefined()
      wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'b')
      await flushPromises()
      expect(card.text()).not.toContain('Could not verify link.')
      mocks.patchFace.mockResolvedValueOnce({ data: {} })
      await card.get('[aria-label="Verify this link"]').trigger('click')
      await flushPromises()
      expect(mocks.patchFace).toHaveBeenLastCalledWith({
        path: { detection_id: 'b' },
        body: { entity_link_state: 'verified' },
        throwOnError: true,
      })
      expect(candidates.props('assignmentPending')).toBe(false)
      wrapper.unmount()
    },
  )

  it('disables both Verify controls during assignment, creation and deletion', async () => {
    faces.value = faces.value.map((item) => ({ ...item, linkState: 'manual' }))
    const wrapper = await mountView(true)
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    const card = wrapper.findComponent({ name: 'CurrentFacePanel' })
    const overlay = wrapper.findComponent({ name: 'DocumentPageOverlay' })
    const candidates = wrapper.findComponent({ name: 'SimilarPeopleResults' })
    const expectBusy = () => {
      for (const control of [card, overlay]) {
        expect(control.get('[aria-label="Verify this link"]').attributes('disabled')).toBeDefined()
      }
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
    card.vm.$emit('create', { name: 'New person' })
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
    card.vm.$emit('delete')
    await flushPromises()
    await wrapper.get('button[data-slot="button"][class*="bg-destructive"]').trigger('click')
    await flushPromises()
    expectBusy()
    await card.get('[aria-label="Verify this link"]').trigger('click')
    overlay.findComponent({ name: 'FaceActionButtons' }).vm.$emit('verify')
    await flushPromises()
    expect(mocks.patchFace).not.toHaveBeenCalled()
    rejectDeletion(new Error('Forbidden'))
    await flushPromises()
    expect(candidates.props('assignmentPending')).toBe(false)
    wrapper.unmount()
  })
})
