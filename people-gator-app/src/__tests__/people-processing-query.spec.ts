import { QueryClient, VueQueryPlugin, type InfiniteData } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ list: vi.fn(), search: vi.fn() }))
vi.mock('@/query/entities', () => ({ fetchEntities: mocks.list }))
vi.mock('@/client', () => ({ searchEntitiesGetApiV1SearchEntitiesGet: mocks.search }))
vi.mock('@/query/faces', () => ({ fetchFaces: vi.fn() }))
vi.mock('@/query/text-mentions', () => ({ fetchTextMentions: vi.fn() }))
import { usePeopleSearch } from '@/viewmodels/people-search'
import {
  emptySharedFilters,
  sharedFilterError,
  sharedFiltersQuery,
  utcToLocalTime,
  type SharedFilters,
} from '@/viewmodels/shared-filters'

function use(term: string | ReturnType<typeof ref<string>>, assignment: 'all' | 'mentions', filters: ReturnType<typeof ref<SharedFilters>>) {
  return usePeopleSearch(
    term as never,
    assignment,
    12,
    computed(() => sharedFiltersQuery(filters.value!)),
    computed(() => !sharedFilterError(filters.value!)),
  )
}

function page(cursor: string | null = null) {
  return { items: [], limit: 12, total_count: 42, cursor }
}

describe('people processing queries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue(page())
    mocks.search.mockResolvedValue({ data: page() })
  })

  it('sends the same filters to browsing and text search, with filter-aware pagination', async () => {
    const term = ref('')
    const filters = ref<SharedFilters>(emptySharedFilters())
    let result!: ReturnType<typeof usePeopleSearch>
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    mocks.list.mockResolvedValueOnce(page('old-cursor'))
    const wrapper = mount(
      defineComponent({
        setup() {
          result = use(term, 'mentions', filters)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    await flushPromises()
    await result.loadMore()
    expect(mocks.list.mock.lastCall?.[0]).toMatchObject({ cursor: 'old-cursor' })
    filters.value = {
      ...emptySharedFilters(),
      touchedFrom: utcToLocalTime('2026-01-02T12:00:00Z'),
      documentIds: ['doc'],
      userIds: ['user'],
      apiKeyIds: ['key'],
    }
    await flushPromises()
    const expected = {
      'filter.last_touched_from': '2026-01-02T12:00:00.000Z',
      'filter.document_source_id': ['doc'],
      'filter.last_touched_by_user_id': ['user'],
      'filter.last_touched_by_api_key_id': ['key'],
      'filter.has_mentions': true,
    }
    expect(mocks.list.mock.lastCall?.[0]).toMatchObject({ ...expected, cursor: null })
    expect(result.resultCount.value).toBe(42)
    term.value = 'Ada'
    await flushPromises()
    expect(mocks.search.mock.lastCall?.[0].query).toMatchObject({
      ...expected,
      'query.text': ['Ada'],
      cursor: null,
    })
    expect(result.resultCount.value).toBe(42)
    filters.value = { ...filters.value, documentIds: ['other-doc'] }
    await flushPromises()
    expect(mocks.search.mock.lastCall?.[0].query).toMatchObject({
      'filter.document_source_id': ['other-doc'],
      cursor: null,
    })
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThanOrEqual(4)
    // Revisiting a cached filter must discard its previously loaded second page.
    term.value = ''
    filters.value = emptySharedFilters()
    await flushPromises()
    const originalQuery = queryClient
      .getQueryCache()
      .findAll({ queryKey: ['entities'] })
      .find((query) => !JSON.stringify(query.queryKey).includes('filter.document_source_id'))!
    expect((originalQuery.state.data as InfiniteData<unknown>).pages).toHaveLength(1)
    wrapper.unmount()
    queryClient.clear()
  })

  it('does not send an invalid time range to the API', async () => {
    const filters = ref<SharedFilters>({
      ...emptySharedFilters(),
      touchedFrom: '2026-02-02T12:00',
      touchedTo: '2026-01-01T12:00',
    })
    let result!: ReturnType<typeof usePeopleSearch>
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(
      defineComponent({
        setup() {
          result = use('', 'all', filters)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    await flushPromises()
    expect(mocks.list).not.toHaveBeenCalled()
    expect(sharedFilterError(filters.value)).toContain('before or equal')
    expect(result.isLoading.value).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })
})
