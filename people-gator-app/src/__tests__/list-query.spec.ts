import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref, type Ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listDocuments: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listEntities: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listFaces: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listImages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listPages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listSources: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listTextMentions: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listUsers: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))

vi.mock('@/client', () => ({
  listDocumentsRouteApiV1DocumentsGet: mocks.listDocuments,
  listEntitiesRouteApiV1EntitiesGet: mocks.listEntities,
  listFacesRouteApiV1FacesGet: mocks.listFaces,
  listImagesRouteApiV1ImagesGet: mocks.listImages,
  listPagesRouteApiV1PagesGet: mocks.listPages,
  listSourcesRouteApiV1SourcesGet: mocks.listSources,
  listTextMentionsRouteApiV1TextMentionsGet: mocks.listTextMentions,
  listUsersRouteApiV1UsersGet: mocks.listUsers,
}))

import { useEntityListQuery } from '@/query/entities'
import { useFaceListQuery } from '@/query/faces'
import {
  useDocumentListQuery,
  useImageListQuery,
  usePageListQuery,
  useSourceListQuery,
} from '@/query/media'
import { useTextMentionListQuery } from '@/query/text-mentions'
import { useUserListQuery } from '@/query/users'

type TestParams = {
  limit: number
  cursor: string | null
}

type TestQuery = {
  fetchNextPage: () => Promise<unknown>
}

type ListCase = readonly [
  name: string,
  apiMock: (typeof mocks)[keyof typeof mocks],
  useListQuery: (params: Ref<TestParams>) => TestQuery,
]

const listCases: ListCase[] = [
  ['documents', mocks.listDocuments, (params) => useDocumentListQuery(params)],
  ['entities', mocks.listEntities, (params) => useEntityListQuery(params)],
  ['faces', mocks.listFaces, (params) => useFaceListQuery(params)],
  ['images', mocks.listImages, (params) => useImageListQuery(params)],
  ['pages', mocks.listPages, (params) => usePageListQuery(params)],
  ['sources', mocks.listSources, (params) => useSourceListQuery(params)],
  ['text mentions', mocks.listTextMentions, (params) => useTextMentionListQuery(params)],
  ['users', mocks.listUsers, (params) => useUserListQuery(params)],
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

describe('object list queries', () => {
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

  it.each(listCases)(
    'uses supplied and returned cursors for %s',
    async (_name, apiMock, useListQuery) => {
      let query: TestQuery | undefined
      const wrapper = mountQuery(() => {
        query = useListQuery(ref({ limit: 5, cursor: 'start' }))
      })
      await flushPromises()

      expect(apiMock).toHaveBeenNthCalledWith(1, {
        query: { limit: 5, cursor: 'start' },
        signal: expect.any(AbortSignal),
        throwOnError: true,
      })

      await query?.fetchNextPage()

      expect(apiMock).toHaveBeenNthCalledWith(2, {
        query: { limit: 5, cursor: 'next' },
        signal: expect.any(AbortSignal),
        throwOnError: true,
      })
      wrapper.unmount()
    },
  )
})
