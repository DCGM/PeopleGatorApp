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
}))
vi.mock('vue-router', () => ({ useRoute: mocks.route, useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('@/composables/link-state-filter', () => ({ useLinkStateFilter: () => ref([]) }))
vi.mock('@/query/media', () => ({
  useDocumentLookupQuery: () => ({ isPending: ref(false), error: ref(null), data: ref(null) }),
}))
vi.mock('@/query/translation', () => ({
  useTranslationQuery: () => ({ data: ref(null), isFetching: ref(false) }),
}))
vi.mock('@/viewmodels/document-workspace', () => ({ useDocumentWorkspace: mocks.workspace }))
vi.mock('@panzoom/panzoom', () => ({
  default: () => ({
    zoom: mocks.zoom,
    pan: mocks.pan,
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
  await new Promise(resolve => requestAnimationFrame(resolve))
  await flushPromises()
}
async function mountView() {
  const wrapper = shallowMount(DocumentPageView, {
    global: {
      stubs: {
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
