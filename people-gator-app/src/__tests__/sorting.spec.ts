import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listDocuments: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchDocuments: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listDocumentsRouteApiV1DocumentsGet: mocks.listDocuments,
  searchDocumentsGetApiV1SearchDocumentsGet: mocks.searchDocuments,
}))

import SortControl from '@/components/custom/SortControl.vue'
import { Select } from '@/components/ui/select'
import {
  listSortParams,
  readSort,
  sortStrategies,
  sortUrl,
  useRouteSort,
  type SortState,
} from '@/lib/sorting'
import { useDocumentResultsQuery } from '@/query/search/documents'
import { activityGroups } from '@/viewmodels/page-activity'
import {
  DOCUMENT_BROWSE_DEFAULT,
  DOCUMENT_SORTS,
  FACE_SORT_KEYS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'

const keys = { field: 'sort', direction: 'dir' }
const browse = scoredOptions(DOCUMENT_SORTS, false)

describe('shared sort state', () => {
  it('reads URL values and recovers invalid or inapplicable ones to a documented default', () => {
    expect(readSort({ sort: 'page_count' }, keys, browse, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      field: 'page_count',
      direction: 'desc',
    })
    expect(readSort({ sort: 'name', dir: 'desc' }, keys, browse, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      field: 'name',
      direction: 'desc',
    })
    expect(readSort({ sort: 'name', dir: 'up' }, keys, browse, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      field: 'name',
      direction: 'asc',
    })
    // Relevance needs a score: browsing resolves it to the browse default.
    expect(readSort({ sort: 'relevance' }, keys, browse, DOCUMENT_BROWSE_DEFAULT)).toEqual(
      DOCUMENT_BROWSE_DEFAULT,
    )
    expect(readSort({ sort: 'pg_demo_sources.id' }, keys, browse, DOCUMENT_BROWSE_DEFAULT)).toEqual(
      DOCUMENT_BROWSE_DEFAULT,
    )
    // An explicit choice that still applies survives switching to search.
    expect(readSort({ sort: 'name' }, keys, DOCUMENT_SORTS, RELEVANCE)).toEqual({
      field: 'name',
      direction: 'asc',
    })
  })

  it('keeps links short and never sends relevance to an ordinary list', () => {
    expect(sortUrl(DOCUMENT_BROWSE_DEFAULT, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      sort: undefined,
      dir: undefined,
    })
    expect(sortUrl({ field: 'name', direction: 'desc' }, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      sort: 'name',
      dir: 'desc',
    })
    expect(sortUrl({ field: 'page_count', direction: 'desc' }, DOCUMENT_BROWSE_DEFAULT)).toEqual({
      sort: 'page_count',
      dir: undefined,
    })
    expect(listSortParams(RELEVANCE)).toEqual({})
    expect(listSortParams({ field: 'name', direction: 'asc' })).toEqual({
      sort: 'name',
      sort_direction: 'asc',
    })
  })

  it('stores independent panel orders in history, resetting cursors', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push({ path: '/', query: { cursor: 'old', sort: 'name' } })
    let faces!: ReturnType<typeof useRouteSort>
    let documents!: ReturnType<typeof useRouteSort>
    mount(
      defineComponent({
        setup() {
          faces = useRouteSort(
            FACE_SORT_KEYS,
            [{ value: 'confidence', label: 'C', kind: 'number' }],
            {
              field: 'confidence',
              direction: 'asc',
            },
          )
          documents = useRouteSort(keys, browse, DOCUMENT_BROWSE_DEFAULT)
          return () => h('div')
        },
      }),
      { global: { plugins: [router] } },
    )
    faces.value = { field: 'confidence', direction: 'desc' }
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      sort: 'name',
      face_sort: 'confidence',
      face_dir: 'desc',
    })
    expect(documents.value).toEqual({ field: 'name', direction: 'asc' })
    router.back()
    await flushPromises()
    expect(faces.value).toEqual({ field: 'confidence', direction: 'asc' })
  })
})

describe('SortControl', () => {
  it('offers each field and direction as one combined strategy', async () => {
    expect(sortStrategies(browse.slice(0, 2)).map((item) => item.label)).toEqual([
      'Name · A–Z',
      'Name · Z–A',
      'Library · A–Z',
      'Library · Z–A',
    ])
    expect(
      sortStrategies(browse.filter((option) => option.value === 'last_touched_at')).map(
        (item) => item.label,
      ),
    ).toEqual(['Last processing · Newest first', 'Last processing · Oldest first'])

    const sort = ref<SortState>({ field: 'name', direction: 'asc' })
    const wrapper = mount(SortControl, {
      props: {
        options: browse,
        modelValue: sort.value,
        'onUpdate:modelValue': (value: SortState) => {
          sort.value = value
          void wrapper.setProps({ modelValue: value })
        },
      },
    })
    expect(wrapper.text()).toContain('Sort: Name · A–Z')
    // A single control: no separate direction button.
    expect(wrapper.findAll('button[aria-label^="Order:"]')).toHaveLength(0)
    wrapper.findComponent(Select).vm.$emit('update:modelValue', 'name:desc')
    await flushPromises()
    expect(sort.value).toEqual({ field: 'name', direction: 'desc' })
    wrapper.findComponent(Select).vm.$emit('update:modelValue', 'page_count:desc')
    await flushPromises()
    expect(sort.value).toEqual({ field: 'page_count', direction: 'desc' })
    expect(wrapper.text()).toContain('Sort: Pages · Highest first')
  })
})

describe('document results sorting', () => {
  beforeEach(() => {
    mocks.listDocuments
      .mockReset()
      .mockResolvedValue({ data: { items: [], limit: 2, cursor: null } })
    mocks.searchDocuments
      .mockReset()
      .mockResolvedValue({ data: { items: [], limit: 2, cursor: null } })
  })

  it('applies the order in the API before pagination and starts a new sequence on change', async () => {
    const params = ref({
      query: '',
      filters: {},
      limit: 2,
      sort: { field: 'page_count', direction: 'desc' } as SortState<
        'page_count' | 'relevance' | 'name'
      >,
    })
    mount(
      defineComponent({
        setup() {
          useDocumentResultsQuery(params)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
    await flushPromises()
    expect(mocks.listDocuments.mock.calls[0]![0]).toMatchObject({
      query: { sort: 'page_count', sort_direction: 'desc', cursor: null },
    })
    params.value = { ...params.value, query: 'Ada', sort: RELEVANCE }
    await flushPromises()
    expect(mocks.searchDocuments.mock.calls[0]![0]).toMatchObject({
      query: { 'query.text': ['Ada'], sort: 'relevance', sort_direction: 'desc', cursor: null },
    })
    // A relevance choice is never sent to the ordinary list.
    params.value = { ...params.value, query: '' }
    await flushPromises()
    const calls = mocks.listDocuments.mock.calls
    const last = calls[calls.length - 1]![0] as { query: Record<string, unknown> }
    expect(last.query.sort).toBeUndefined()
  })
})

describe('activity order', () => {
  const items = [
    { id: 'b', kind: 'face' as const, label: 'B', touchedAt: '2026-01-02T10:00:00Z', userId: 'u2' },
    { id: 'a', kind: 'mention' as const, label: 'A', touchedAt: null, userId: 'u1' },
    { id: 'c', kind: 'face' as const, label: 'C', touchedAt: '2026-01-02T11:00:00Z', userId: 'u1' },
    { id: 'd', kind: 'face' as const, label: 'D', touchedAt: null, userId: null },
  ]
  const labels: Record<string, string> = { u1: 'Zora', u2: 'Ada' }

  it('orders user groups by label with unknown editors last in both directions', () => {
    for (const groups of ['asc', 'desc'] as const) {
      const result = activityGroups(items, 'user', { groups, items: 'desc' }, (key) => labels[key]!)
      expect(result.map((group) => group.key)).toEqual(
        groups === 'asc' ? ['u2', 'u1', ''] : ['u1', 'u2', ''],
      )
    }
  })

  it('orders edits chronologically with unknown times last in both directions', () => {
    for (const direction of ['asc', 'desc'] as const) {
      const [user] = activityGroups(items, 'user', { groups: 'asc', items: direction }, (key) =>
        key === 'u1' ? 'A' : 'B',
      )
      expect(user!.records.map((item) => item.id)).toEqual(['c', 'a'])
    }
    const [, unknownDay] = activityGroups(items, 'time', { groups: 'desc', items: 'asc' })
    expect(unknownDay).toMatchObject({ key: '' })
  })
})
