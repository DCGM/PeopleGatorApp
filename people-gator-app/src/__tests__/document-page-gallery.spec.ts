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

import { pageGalleryLabel, useDocumentPageGallery } from '@/viewmodels/document-page-gallery'

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

function mountGallery(
  currentPageId: string,
  batchSize = 2,
  personId = ref(''),
  selectedPersonId = personId,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const current = ref(currentPageId)
  let gallery!: ReturnType<typeof useDocumentPageGallery>
  const wrapper = mount(
    defineComponent({
      setup() {
        gallery = useDocumentPageGallery(
          LIBRARY,
          DOCUMENT,
          current,
          batchSize,
          undefined,
          personId,
          selectedPersonId,
        )
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return { wrapper, current, personId, client, gallery: () => gallery }
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
      // Archive page IDs are an explicit order, never presented as page numbers.
      sort: 'page_number',
      sort_direction: 'asc',
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
    expect(mocks.pageImage).toHaveBeenCalledWith(expect.objectContaining({ query: { width: 256 } }))
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

  it('filters by person on the server and never drains batches to find an excluded current page', async () => {
    respond({
      first: {
        items: [{ ...page(2), entity_link_stats: { faces: { unassigned: 1 } } }],
        cursor: 'next',
      },
      next: { items: [page(3)], cursor: null },
    })
    const { wrapper, gallery, personId, client } = mountGallery(page(99).page_id, 2, ref('nora'))
    await flushPromises()
    expect(mocks.listPages).toHaveBeenCalledTimes(1)
    expect(mocks.listPages.mock.calls[0]![0].query['filter.entity_id']).toEqual(['nora'])
    expect(gallery().items.value[0]?.unassignedFaces).toBe(1)
    expect(gallery().items.value.every((item) => !item.current)).toBe(true)
    gallery().loadMore()
    await flushPromises()
    expect(mocks.listPages).toHaveBeenCalledTimes(2)
    expect(gallery().items.value[1]?.unassignedFaces).toBeNull()
    // Existing mutation invalidation must refresh counts/membership in the strip.
    respond({ first: { items: [], cursor: null } })
    await client.invalidateQueries({ queryKey: ['pages'] })
    await flushPromises()
    expect(gallery().items.value).toEqual([])
    personId.value = ''
    await flushPromises()
    expect(
      mocks.listPages.mock.calls[mocks.listPages.mock.calls.length - 1]![0].query[
        'filter.entity_id'
      ],
    ).toBeUndefined()
    wrapper.unmount()
  })

  it('highlights the selected person across the full strip with one scoped membership query per loaded batch', async () => {
    let matches = [2, 3]
    let fail = false
    mocks.listPages.mockImplementation(async ({ query }) => {
      if (query['filter.source_id']) {
        if (fail) throw new Error('membership unavailable')
        const ids = query['filter.source_id'] as string[]
        return {
          data: {
            items: matches.map((index) => page(index)).filter((p) => ids.includes(p.source_id)),
            cursor: null,
          },
        }
      }
      return { data: { items: [page(1), page(2), page(3)], total_count: 3, cursor: null } }
    })
    const selected = ref('nora')
    const { wrapper, gallery, client } = mountGallery(page(1).page_id, 3, ref(''), selected)
    await flushPromises()
    expect(gallery().items.value.map((item) => item.matchesSelectedPerson)).toEqual([
      false,
      true,
      true,
    ])
    expect(mocks.listPages).toHaveBeenCalledTimes(2)
    expect(mocks.listPages.mock.calls[1]![0].query).toEqual({
      'filter.library': [LIBRARY],
      'filter.document_id': [DOCUMENT],
      'filter.entity_id': ['nora'],
      'filter.source_id': ['source-1', 'source-2', 'source-3'],
      limit: 3,
    })
    expect(mocks.listPages.mock.calls[0]![0].query['filter.entity_id']).toBeUndefined()
    matches = [2]
    await client.invalidateQueries({ queryKey: ['pages'] })
    await flushPromises()
    expect(gallery().items.value.map((item) => item.matchesSelectedPerson)).toEqual([
      false,
      true,
      false,
    ])
    fail = true
    selected.value = 'otto'
    await flushPromises()
    expect(gallery().items.value).toHaveLength(3)
    expect(gallery().items.value.every((item) => item.matchesSelectedPerson === null)).toBe(true)
    expect(gallery().highlightError.value).toBe(true)
    fail = false
    await gallery().retryHighlights()
    await flushPromises()
    expect(gallery().highlightError.value).toBe(false)
    selected.value = ''
    await flushPromises()
    expect(gallery().items.value.every((item) => !item.matchesSelectedPerson)).toBe(true)
    wrapper.unmount()
  })

  it('labels pages with their archive identifier', () => {
    expect(pageGalleryLabel(page(3).page_id)).toBe('00000003')
  })
})
