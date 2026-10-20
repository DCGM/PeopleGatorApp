import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listPages: vi.fn<(options: { query: Record<string, unknown> }) => Promise<unknown>>(),
  pageImage: vi.fn<(options: { path: { page_source_id: string } }) => Promise<unknown>>(),
}))

vi.mock('@/client', () => ({
  listPagesRouteApiV1PagesGet: mocks.listPages,
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: mocks.pageImage,
}))

import {
  pageGalleryLabel,
  pageGalleryQuery,
  useDocumentPageGallery,
} from '@/viewmodels/document-page-gallery'

const LIBRARY = 'preview-mzk'
const DOCUMENT = '00000000-0000-4000-8000-00000000d0c0'
const page = (index: number, overrides: Record<string, string> = {}) => ({
  source_id: `source-${index}`,
  source_type: 'page',
  url: `https://preview.invalid/${index}`,
  library: LIBRARY,
  document_id: DOCUMENT,
  page_id: `${String(index).padStart(8, '0')}-0000-4000-8000-000000000000`,
  ...overrides,
})

function respond(batches: Record<string, { items: unknown[]; cursor?: string | null }>) {
  mocks.listPages.mockImplementation(async ({ query }) => {
    const batch = batches[String(query.cursor ?? 'first')]
    if (!batch) throw new Error(`unexpected cursor ${String(query.cursor)}`)
    return { data: { ...batch, limit: query.limit, total_count: 5 } }
  })
}

function mountGallery(currentPageId: string, batchSize = 2) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const current = ref(currentPageId)
  let gallery!: ReturnType<typeof useDocumentPageGallery>
  const wrapper = mount(
    defineComponent({
      setup() {
        gallery = useDocumentPageGallery(LIBRARY, DOCUMENT, current, batchSize)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return { wrapper, current, gallery: () => gallery }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn((blob: Blob) => `blob:${blob.size}`),
    revokeObjectURL: vi.fn(),
  })
  mocks.pageImage.mockImplementation(async ({ path }) => {
    if (path.page_source_id === 'source-2') throw new Error('missing media')
    return { data: new Blob(['x'.repeat(Number(path.page_source_id.split('-')[1]))]) }
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('document page gallery', () => {
  it('lists only registered pages of the exact library and document, without evidence filters', async () => {
    respond({
      first: {
        items: [page(1), page(9, { library: 'preview-nlk' }), page(8, { document_id: 'other' })],
        cursor: null,
      },
    })
    const { wrapper, gallery } = mountGallery(page(1).page_id)
    await flushPromises()
    expect(mocks.listPages).toHaveBeenCalledTimes(1)
    expect(mocks.listPages.mock.calls[0]![0].query).toEqual({
      'filter.library': [LIBRARY],
      'filter.document_id': [DOCUMENT],
      limit: 2,
      return_total_count: true,
      cursor: null,
    })
    expect(gallery().items.value.map((item) => item.sourceId)).toEqual(['source-1'])
    wrapper.unmount()
  })

  it('loads further batches until the current page appears, without duplicates', async () => {
    respond({
      first: { items: [page(1), page(2)], cursor: 'c1' },
      c1: { items: [page(2), page(3)], cursor: 'c2' },
      c2: { items: [page(4), page(5)], cursor: null },
    })
    const { wrapper, gallery, current } = mountGallery(page(3).page_id)
    await flushPromises()
    expect(mocks.listPages).toHaveBeenCalledTimes(2)
    const items = gallery().items.value
    expect(items.map((item) => item.sourceId)).toEqual(['source-1', 'source-2', 'source-3'])
    expect(items.filter((item) => item.current).map((item) => item.sourceId)).toEqual(['source-3'])
    expect(gallery().hasNextPage.value).toBe(true)

    gallery().loadMore()
    await flushPromises()
    expect(gallery().items.value).toHaveLength(5)
    expect(gallery().hasNextPage.value).toBe(false)
    expect(gallery().totalCount.value).toBe(5)

    current.value = page(5).page_id
    await flushPromises()
    expect(mocks.listPages).toHaveBeenCalledTimes(3)
    expect(gallery().items.value.find((item) => item.current)?.sourceId).toBe('source-5')
    wrapper.unmount()
  })

  it('keeps pages navigable when their thumbnails are missing', async () => {
    respond({ first: { items: [page(1), page(2)], cursor: null } })
    const { wrapper, gallery } = mountGallery(page(1).page_id)
    await flushPromises()
    const [first, second] = gallery().items.value
    expect(first).toMatchObject({ thumbnailUrl: 'blob:1', thumbnailFailed: false })
    expect(second).toMatchObject({
      pageId: page(2).page_id,
      thumbnailUrl: '',
      thumbnailLoading: false,
      thumbnailFailed: true,
    })
    expect(mocks.pageImage).toHaveBeenCalledWith(
      expect.objectContaining({ query: { width: 256 } }),
    )
    wrapper.unmount()
  })

  it('reports a failed page list and recovers on retry', async () => {
    mocks.listPages.mockRejectedValueOnce(new Error('offline'))
    const { wrapper, gallery } = mountGallery(page(1).page_id)
    await flushPromises()
    expect(gallery().error.value).toBeTruthy()
    expect(gallery().items.value).toEqual([])
    respond({ first: { items: [page(1)], cursor: null } })
    await gallery().retry()
    await flushPromises()
    expect(gallery().error.value).toBeNull()
    expect(gallery().items.value.map((item) => item.current)).toEqual([true])
    wrapper.unmount()
  })

  it('labels pages with their archive identifier and drops page-specific selections', () => {
    expect(pageGalleryLabel(page(3).page_id)).toBe('00000003')
    expect(
      pageGalleryQuery({
        person: 'face',
        selectedPerson: 'entity',
        line: 'l1',
        link_state: ['manual', 'verified'],
        evidence_user: 'user',
        translate: 'on',
        panel: 'activity',
      }),
    ).toEqual({
      link_state: ['manual', 'verified'],
      evidence_user: 'user',
      translate: 'on',
      panel: 'activity',
    })
  })
})
