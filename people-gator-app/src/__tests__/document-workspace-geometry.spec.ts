import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError, type AxiosResponse } from 'axios'
import { computed, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import { fetchPageLayout, fetchPageMentionSpans } from '@/query/pages'
import { useDocumentWorkspace } from '@/viewmodels/document-workspace'

const api = vi.hoisted(() => ({
  page: vi.fn(), image: vi.fn(), layout: vi.fn(), spans: vi.fn(),
  faces: vi.fn(), entities: vi.fn(), mentions: vi.fn(), crop: vi.fn(),
}))
vi.mock('@/client', async importOriginal => ({
  ...await importOriginal<typeof import('@/client')>(),
  lookupPageRouteApiV1PagesLookupGet: api.page,
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: api.image,
  getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet: api.layout,
  getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet: api.spans,
  listFacesRouteApiV1FacesGet: api.faces,
  listEntitiesRouteApiV1EntitiesGet: api.entities,
  listTextMentionsRouteApiV1TextMentionsGet: api.mentions,
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet: api.crop,
}))
const cleanup: (() => void)[] = []
const httpError = (status: number) => new AxiosError('media unavailable', undefined, undefined, undefined, { status } as AxiosResponse)

beforeEach(() => {
  vi.resetAllMocks()
  let id = 0
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => `blob:scan-${++id}`)
    static revokeObjectURL = vi.fn()
  })
  api.page.mockImplementation(({ query }) => Promise.resolve({ data: { source_id: query.page_id } }))
  api.image.mockImplementation(() => Promise.resolve({ data: new Blob(['scan']) }))
  api.layout.mockRejectedValue(httpError(404))
  api.spans.mockRejectedValue(httpError(404))
  api.faces.mockResolvedValue({ data: { items: [{
    detection_id: 'face', entity_id: null, entity_link_state: null, embeddings: [], confidence: 1,
    bounding_box: { x: 300, y: 400, width: 200, height: 250 },
  }], limit: 100, cursor: null } })
  for (const mock of [api.entities, api.mentions]) mock.mockResolvedValue({ data: { items: [], limit: 100, cursor: null } })
  api.crop.mockResolvedValue({ data: new Blob(['crop']) })
})
afterEach(() => {
  cleanup.splice(0).reverse().forEach(fn => fn())
  vi.unstubAllGlobals()
})

async function workspace() {
  const pageId = ref('first-page')
  let model!: ReturnType<typeof useDocumentWorkspace>
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(defineComponent({ setup() {
    model = useDocumentWorkspace('library', 'document', pageId, null, '')
    const props = computed(() => ({
      pageBounds: { left: 10, top: 20, width: 480, height: 720 },
      faces: model.faces.value, transcription: [], selectedLineIndex: 0,
      selectedFaceId: null, selectedPersonId: null, selectedCandidateFaceId: null,
    }))
    return () => h(DocumentPageOverlay, props.value)
  } }), { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  cleanup.push(() => { wrapper.unmount(); queryClient.clear() })
  await flushPromises()
  return { model, wrapper, pageId }
}

async function loadImage(model: ReturnType<typeof useDocumentWorkspace>, width: number, height: number, src = model.pageImageUrl.value) {
  const image = document.createElement('img')
  image.src = src
  Object.defineProperties(image, { naturalWidth: { value: width }, naturalHeight: { value: height } })
  const event = new Event('load')
  Object.defineProperty(event, 'target', { value: image })
  model.pageImageLoaded(event)
  await nextTick()
}

describe('scan geometry without OCR', () => {
  it('uses original image pixels and renders face boxes despite missing OCR', async () => {
    const { model, wrapper } = await workspace()
    expect(api.image.mock.lastCall?.[0].query).toBeUndefined()
    expect(model.error.value).toBeNull()
    expect(model.transcription.value).toEqual([])
    expect(wrapper.find('[data-region-type="face"]').exists()).toBe(false)
    await loadImage(model, 1200, 1800)
    expect(model.pageDimensions.value).toEqual({ width: 1200, height: 1800 })
    const style = (wrapper.get('[data-region-type="face"]').element as HTMLElement).style
    for (const [key, value] of Object.entries({ left: 130, top: 180, width: 80, height: 100 })) {
      expect(parseFloat(style.getPropertyValue(key))).toBeCloseTo(value)
    }
  })

  it('retains OCR coordinates while requesting a resized scan when a layout exists', async () => {
    api.layout.mockResolvedValue({ data: { page_size: [3600, 2400], regions: [], reading_order: {} } })
    api.spans.mockResolvedValue({ data: [] })
    const { model, wrapper } = await workspace()
    expect(api.image.mock.lastCall?.[0].query).toEqual({ width: 1024 })
    await loadImage(model, 1024, 1536)
    expect(model.pageDimensions.value).toEqual({ width: 2400, height: 3600 })
    expect(wrapper.get('[data-region-type="face"]').attributes('style')).toContain('left: 70px')
  })

  it('clears fallback dimensions on page changes and ignores a previous image load', async () => {
    const { model, wrapper, pageId } = await workspace()
    await loadImage(model, 1200, 1800)
    const oldSrc = model.pageImageUrl.value
    pageId.value = 'second-page'
    await flushPromises()
    expect(wrapper.find('[data-region-type="face"]').exists()).toBe(false)
    await loadImage(model, 1200, 1800, oldSrc)
    expect(wrapper.find('[data-region-type="face"]').exists()).toBe(false)
    await loadImage(model, 1800, 1200)
    expect(model.pageDimensions.value).toEqual({ width: 1800, height: 1200 })
    expect(parseFloat((wrapper.get('[data-region-type="face"]').element as HTMLElement).style.left)).toBeCloseTo(90)
  })

  it('treats only missing OCR as optional and preserves authentication and storage errors', async () => {
    expect(await fetchPageLayout('page')).toBeNull()
    expect(await fetchPageMentionSpans('page')).toEqual([])
    for (const status of [401, 403, 500, 502]) {
      api.layout.mockRejectedValue(httpError(status))
      api.spans.mockRejectedValue(httpError(status))
      await expect(fetchPageLayout('page')).rejects.toMatchObject({ response: { status } })
      await expect(fetchPageMentionSpans('page')).rejects.toMatchObject({ response: { status } })
    }
  })
})
