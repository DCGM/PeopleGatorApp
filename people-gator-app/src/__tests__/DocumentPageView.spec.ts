import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { shallowMount, flushPromises } from '@vue/test-utils'
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
    assignmentStatus: ref('idle'),
    assignmentError: ref(null),
    referenceFace: ref(null),
    transcription: lines,
    page: ref({ page_id: 'one' }),
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
async function mountView() {
  const wrapper = shallowMount(DocumentPageView, {
    global: {
      plugins: [
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
        ],
      ],
      stubs: {
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
    expect(order.value).toEqual({ field: 'page_id', direction: 'asc' })
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
    card.vm.$emit('delete')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    expect(mocks.deleteFace).not.toHaveBeenCalled()
    await wrapper.findComponent({ name: 'AlertDialogAction' }).trigger('click')
    await flushPromises()
    expect(card.props('face')).toMatchObject({ id: 'a' })
    expect(card.props('actionError')).toBe('Could not delete detection.')
    expect(wrapper.findComponent({ name: 'AlertDialog' }).props('open')).toBe(true)
    await wrapper.findComponent({ name: 'AlertDialogAction' }).trigger('click')
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
  it('routes card verification through the existing verify mutation', async () => {
    mocks.patchFace.mockResolvedValue({
      data: { detection_id: 'a', entity_link_state: 'verified' },
    })
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'FaceGallery' }).vm.$emit('select', 'a')
    await flushPromises()
    wrapper.findComponent({ name: 'CurrentFacePanel' }).vm.$emit('verify')
    await flushPromises()
    expect(mocks.patchFace).toHaveBeenCalledWith({
      path: { detection_id: 'a' },
      body: { entity_link_state: 'verified' },
      throwOnError: true,
    })
    wrapper.unmount()
  })
})
