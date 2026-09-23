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
