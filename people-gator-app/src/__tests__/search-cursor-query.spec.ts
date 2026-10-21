import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  searchDocuments: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchEntities: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchFaces: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchPages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))

vi.mock('@/query/media', () => ({ fetchDocuments: vi.fn() }))

vi.mock('@/client', () => ({
  searchDocumentsGetApiV1SearchDocumentsGet: mocks.searchDocuments,
  searchEntitiesGetApiV1SearchEntitiesGet: mocks.searchEntities,
  searchFacesGetApiV1SearchFacesGet: mocks.searchFaces,
  searchPagesGetApiV1SearchPagesGet: mocks.searchPages,
}))

import {
  useDocumentSearchQuery,
  useEntitySearchQuery,
  useFaceSearchQuery,
  usePageSearchQuery,
} from '@/query/search'

type TestQuery = {
  fetchNextPage: () => Promise<unknown>
}

type SearchCase = readonly [
  name: string,
  apiMock: (typeof mocks)[keyof typeof mocks],
  useSearchQuery: () => TestQuery,
  request: Record<string, unknown>,
]

const searchCases: SearchCase[] = [
  [
    'documents',
    mocks.searchDocuments,
    () => useDocumentSearchQuery(ref({ 'query.text': ['Ada'], limit: 5, cursor: 'start' })),
    { 'query.text': ['Ada'], limit: 5 },
  ],
  [
    'entities',
    mocks.searchEntities,
    () => useEntitySearchQuery(ref({ 'query.text': ['Ada'], limit: 5, cursor: 'start' })),
    { 'query.text': ['Ada'], limit: 5 },
  ],
  [
    'faces',
    mocks.searchFaces,
    () => useFaceSearchQuery(ref({ 'query.face_id': ['face-1'], limit: 5, cursor: 'start' })),
    { 'query.face_id': ['face-1'], limit: 5 },
  ],
  [
    'pages',
    mocks.searchPages,
    () => usePageSearchQuery(ref({ 'query.text': ['Ada'], limit: 5, cursor: 'start' })),
    { 'query.text': ['Ada'], limit: 5 },
  ],
]

function mountQuery(setup: () => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Harness = defineComponent({
    setup() {
      setup()
      return () => h('div')
    },
  })
  return mount(Harness, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
}

describe('search queries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const mock of Object.values(mocks)) {
      mock.mockResolvedValue({
        data: {
          items: [],
          total_count: 2,
          limit: 5,
          cursor: 'next',
        },
      })
    }
  })

  it.each(searchCases)(
    'uses supplied and returned cursors for %s',
    async (_name, apiMock, useSearchQuery, request) => {
      let query: TestQuery | undefined
      const wrapper = mountQuery(() => {
        query = useSearchQuery()
      })
      await flushPromises()

      expect(apiMock).toHaveBeenNthCalledWith(1, {
        query: { ...request, cursor: 'start' },
        signal: expect.any(AbortSignal),
        throwOnError: true,
      })

      await query?.fetchNextPage()

      expect(apiMock).toHaveBeenNthCalledWith(2, {
        query: { ...request, cursor: 'next' },
        signal: expect.any(AbortSignal),
        throwOnError: true,
      })
      wrapper.unmount()
    },
  )
})

describe('document result cursors', () => {
  it('uses list/search filters, resets revisited cursors and ignores obsolete responses', async () => {
    const { useDocumentResultsQuery } = await import('@/query/search/documents')
    const { fetchDocuments } = await import('@/query/media')
    const term = ref('')
    const filters = ref({ 'filter.library': ['a'] })
    let result!: ReturnType<typeof useDocumentResultsQuery>
    let release!: (value: unknown) => void
    const list = vi.mocked(fetchDocuments)
    list.mockResolvedValue({ items: [], total_count: 2, limit: 5, cursor: 'a-next' })
    mocks.searchDocuments.mockImplementation((...args: unknown[]) =>
      (
        (args[0] as { query: Record<string, unknown> }).query['query.text'] as string[] | undefined
      )?.[0] === 'old'
        ? new Promise((resolve) => {
            release = resolve
          })
        : Promise.resolve({ data: { items: [], total_count: 1, limit: 5, cursor: null } }),
    )
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(
      defineComponent({
        setup() {
          result = useDocumentResultsQuery(() => ({
            query: term.value,
            filters: filters.value,
            limit: 5,
          }))
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    await flushPromises()
    await result.fetchNextPage()
    expect(list.mock.lastCall?.[0]).toMatchObject({ 'filter.library': ['a'], cursor: 'a-next' })
    filters.value = { 'filter.library': ['b'] }
    await flushPromises()
    expect(list.mock.lastCall?.[0]).toMatchObject({ 'filter.library': ['b'], cursor: null })
    filters.value = { 'filter.library': ['a'] }
    await flushPromises()
    expect(result.data.value?.pages).toHaveLength(1)
    term.value = 'old'
    await flushPromises()
    term.value = 'new'
    await flushPromises()
    expect(mocks.searchDocuments.mock.lastCall?.[0]).toMatchObject({
      query: { 'query.text': ['new'], 'filter.library': ['a'], cursor: null },
    })
    release({ data: { items: [], total_count: 999, limit: 5, cursor: null } })
    await flushPromises()
    expect(result.data.value?.pages[0]?.totalCount).toBe(1)
    term.value = '  '
    await flushPromises()
    expect(result.data.value?.pages).toHaveLength(1)
    wrapper.unmount()
    queryClient.clear()
  })
})

it.each(['faces', 'entities'] as const)(
  'restarts %s entity discovery after source or entity changes',
  async (kind) => {
    const params = ref({
      'query.entity_id': 'person-a',
      'query.entity_annotations': ['faces'] as Array<'faces' | 'name'>,
      limit: 2,
    })
    const api = kind === 'faces' ? mocks.searchFaces : mocks.searchEntities
    api.mockImplementation((...args: unknown[]) => {
      const query = (args[0] as { query: Record<string, unknown> }).query
      return Promise.resolve({
        data: { items: [], total_count: 4, limit: 2, cursor: query.cursor ? null : 'next' },
      })
    })
    let result!: ReturnType<typeof useFaceSearchQuery> | ReturnType<typeof useEntitySearchQuery>
    const wrapper = mountQuery(() => {
      result = kind === 'faces' ? useFaceSearchQuery(params) : useEntitySearchQuery(params)
    })
    await flushPromises()
    await result.fetchNextPage()
    expect(result.data.value?.pages).toHaveLength(2)
    params.value = { ...params.value, 'query.entity_annotations': ['name'] }
    await flushPromises()
    expect(api.mock.lastCall?.[0]).toMatchObject({
      query: { 'query.entity_id': 'person-a', 'query.entity_annotations': ['name'], cursor: null },
    })
    expect(result.data.value?.pages).toHaveLength(1)
    params.value = { ...params.value, 'query.entity_annotations': ['faces'] }
    await flushPromises()
    expect(result.data.value?.pages).toHaveLength(1)
    params.value = { ...params.value, 'query.entity_id': 'person-b' }
    await flushPromises()
    expect(api.mock.lastCall?.[0]).toMatchObject({
      query: { 'query.entity_id': 'person-b', cursor: null },
    })
    wrapper.unmount()
  },
)
