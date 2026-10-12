import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  users: vi.fn(),
  keys: vi.fn(),
  documents: vi.fn(),
  searchDocuments: vi.fn(),
}))
vi.mock('@/client', () => ({
  listUserFilterOptionsRouteApiV1UserFilterOptionsGet: mocks.users,
  listApiKeysRouteApiV1ApiKeysGet: mocks.keys,
}))
vi.mock('@/query/media', () => ({ fetchDocuments: mocks.documents }))
vi.mock('@/query/search/documents', () => ({ fetchDocumentSearch: mocks.searchDocuments }))
import { usePeopleFilterOptions, type FilterOptionKind } from '@/query/people-filter-options'

function harness(kind: FilterOptionKind) {
  const search = ref('')
  let result!: ReturnType<typeof usePeopleFilterOptions>
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePeopleFilterOptions(kind, search)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  return {
    search,
    result,
    cleanup: () => {
      wrapper.unmount()
      queryClient.clear()
    },
  }
}

describe('searchable filter options', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each(['user', 'api-key'] as const)(
    'searches all %s records and resets the option cursor',
    async (kind) => {
      const request = kind === 'user' ? mocks.users : mocks.keys
      const item =
        kind === 'user'
          ? { user_id: 'original', display_name: 'Original user' }
          : { api_key_id: 'original', display_name: 'Original importer', identifier: 'importer' }
      request
        .mockResolvedValueOnce({ data: { items: [item], cursor: 'next-options' } })
        .mockResolvedValue({ data: { items: [], cursor: null } })
      const { search, result, cleanup } = harness(kind)
      await flushPromises()
      expect(result.options.value[0]?.id).toBe('original')
      await result.loadMore()
      expect(request.mock.lastCall?.[0].query.cursor).toBe('next-options')
      search.value = ' Needle '
      await flushPromises()
      expect(request.mock.lastCall?.[0].query).toMatchObject({ q: 'Needle', cursor: null })
      expect(result.options.value).toEqual([])
      expect(result.labels.value.original).toContain('Original')
      cleanup()
    },
  )

  it('uses internal document source IDs and sends document searches to the server', async () => {
    mocks.documents.mockResolvedValue({
      items: [{ source_id: 'internal-source', library: 'mzk', document_id: 'archive-id' }],
      cursor: null,
    })
    mocks.searchDocuments.mockResolvedValue({ items: [], cursor: null })
    const { search, result, cleanup } = harness('document')
    await flushPromises()
    expect(result.options.value).toEqual([{ id: 'internal-source', label: 'mzk / archive-id' }])
    search.value = 'archive-id'
    await flushPromises()
    expect(mocks.searchDocuments.mock.lastCall?.[0]).toMatchObject({
      'query.text': ['archive-id'],
      cursor: null,
    })
    expect(result.labels.value['internal-source']).toBe('mzk / archive-id')
    cleanup()
  })
})
