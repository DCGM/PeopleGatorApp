import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { AxiosError, type AxiosResponse } from 'axios'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  combineTiers,
  peopleTiers,
  tierSort,
  useScanPeople,
  type PeopleSearchInput,
} from '@/viewmodels/scan-people'
import type { EntityResponse } from '@/client'
import type { PeopleOrder, PeopleScope } from '@/viewmodels/scan-sidebar'

const api = vi.hoisted(() => ({ entities: vi.fn(), search: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listEntitiesRouteApiV1EntitiesGet: api.entities,
  searchEntitiesGetApiV1SearchEntitiesGet: api.search,
}))

const person = (id: string, extra: Record<string, unknown> = {}) =>
  ({ entity_id: id, name: id, ...extra }) as unknown as EntityResponse
const tier = (ids: string[][], hasNextPage = false, error: unknown = null) => ({
  pages: ids.map((page) => ({ items: page.map((id) => person(id)) })),
  hasNextPage,
  isFetching: false,
  error,
})

describe('People tiers (#103)', () => {
  it('nests page, document and others for context order only', () => {
    expect(peopleTiers('all', 'context')).toEqual(['page', 'document', 'all'])
    expect(peopleTiers('document', 'context')).toEqual(['page', 'document'])
    expect(peopleTiers('page', 'context')).toEqual(['page'])
    expect(peopleTiers('all', 'relevance')).toEqual(['all'])
    expect(peopleTiers('document', 'name')).toEqual(['document'])
    expect(tierSort('context', false)).toEqual({ field: 'name', direction: 'asc' })
    expect(tierSort('context', true)).toEqual({ field: 'relevance', direction: 'desc' })
    expect(tierSort('last_touched_at', false)).toEqual({
      field: 'last_touched_at',
      direction: 'desc',
    })
  })

  it('shows a later tier only after earlier tiers are exhausted, each person once', () => {
    const page = tier([['ada']])
    const document = tier([['ada', 'bea'], ['cyril']], true)
    const all = tier([['ada', 'dora']])
    expect(combineTiers([page, document, all])).toEqual({
      items: ['ada', 'bea', 'cyril'].map((id, index) => ({
        record: person(id),
        tier: index === 0 ? 0 : 1,
      })),
      active: 1,
    })
    const exhausted = { ...document, hasNextPage: false }
    const combined = combineTiers([page, exhausted, all])
    expect(combined.items.map(({ record }) => record.entity_id)).toEqual([
      'ada',
      'bea',
      'cyril',
      'dora',
    ])
    expect(combined.active).toBe(3)
    // A failed or still-loading tier holds back every later tier.
    expect(combineTiers([page, { ...exhausted, error: new Error('x') }, all]).active).toBe(1)
    expect(combineTiers([page, { ...exhausted, pages: undefined }, all]).active).toBe(1)
  })
})

describe('useScanPeople (#103)', () => {
  beforeEach(() => vi.clearAllMocks())
  function mountPeople(options: {
    scope?: PeopleScope
    order?: PeopleOrder
    search?: PeopleSearchInput
  }) {
    const scope = ref<PeopleScope>(options.scope ?? 'all')
    const order = ref<PeopleOrder>(options.order ?? 'context')
    const search = ref<PeopleSearchInput>(options.search ?? { text: '' })
    let model!: ReturnType<typeof useScanPeople>
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(
      defineComponent({
        setup() {
          model = useScanPeople({
            sources: { page: 'page-source', document: 'document-source' },
            scope,
            order,
            search,
            pageFaces: [],
            transcription: [],
            pageSourceId: 'page-source',
          })
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    return { model: () => model, scope, order, search, wrapper, client }
  }

  it('lists page, then document, then other people across cursor batches without duplicates', async () => {
    api.entities.mockImplementation(({ query }) => {
      // Membership lookups list which requested people are in the document.
      if (query['filter.entity_id'])
        return Promise.resolve({
          data: {
            items: (query['filter.entity_id'] as string[])
              .filter((id) => ['ada', 'bea', 'cyril', 'eve'].includes(id))
              .map((id) => person(id)),
            cursor: null,
          },
        })
      const scope = query['filter.page_source_id']
        ? 'page'
        : query['filter.document_source_id']
          ? 'document'
          : 'all'
      const data = {
        page: [{ items: [person('ada')], cursor: null, total_count: 1 }],
        document: [
          { items: [person('ada'), person('bea')], cursor: 'd2', total_count: 3 },
          { items: [person('cyril')], cursor: null, total_count: 3 },
        ],
        all: [
          {
            items: [person('bea'), person('dora', { entity_link_stats: { faces: { total: 3 } } })],
            cursor: null,
            total_count: 5,
          },
        ],
      }[scope]
      return Promise.resolve({ data: data[query.cursor ? 1 : 0] })
    })
    const { model, wrapper, client } = mountPeople({})
    await flushPromises()
    for (const call of api.entities.mock.calls)
      expect(call[0].query).toMatchObject({
        'filter.entity_type': ['person'],
        sort: 'name',
        sort_direction: 'asc',
      })
    expect(model().people.value.map((item) => item.id)).toEqual(['ada', 'bea'])
    expect(model().totalCount.value).toBe(5)
    expect(model().hasNextPage.value).toBe(true)
    await model().loadMore()
    await flushPromises()
    expect(model().people.value.map((item) => item.id)).toEqual(['ada', 'bea', 'cyril', 'dora'])
    await flushPromises()
    const inDocument = (id: string) =>
      model()
        .people.value.find((item) => item.id === id)
        ?.matchSources?.some((source) => source.type === 'in-document')
    // Page and document tiers are members; others are checked by a lookup.
    expect(['ada', 'bea', 'cyril', 'dora'].map(inDocument)).toEqual([true, true, true, false])
    // Linked face totals come from each record's link statistics.
    expect(model().people.value.map((item) => item.linkedFaces)).toEqual([0, 0, 0, 3])
    const lookups = api.entities.mock.calls.filter(([call]) => call.query['filter.entity_id'])
    expect(lookups).toHaveLength(1)
    expect(lookups[0]![0].query).toMatchObject({
      'filter.document_source_id': ['document-source'],
      'filter.entity_id': ['dora'],
    })
    expect(model().people.value[0]?.sourceId).toBe('page-source')
    expect(model().hasNextPage.value).toBe(false)
    expect(api.search).not.toHaveBeenCalled()
    wrapper.unmount()
    client.clear()
  })

  it('keeps default document browsing local across tier cursor batches', async () => {
    api.entities.mockImplementation(({ query }) => {
      expect(query['filter.page_source_id'] || query['filter.document_source_id']).toBeTruthy()
      const page = query['filter.page_source_id']
      return Promise.resolve({
        data: page
          ? { items: [person('page-person')], cursor: null, total_count: 1 }
          : query.cursor
            ? { items: [person('document-only')], cursor: null, total_count: 3 }
            : {
                items: [person('mention-only'), person('page-person')],
                cursor: 'next',
                total_count: 3,
              },
      })
    })
    const { model, wrapper, client } = mountPeople({ scope: 'document' })
    await flushPromises()
    expect(model().people.value.map((item) => item.id)).toEqual(['page-person', 'mention-only'])
    expect(model().totalCount.value).toBe(3)
    await model().loadMore()
    await flushPromises()
    expect(model().people.value.map((item) => item.id)).toEqual([
      'page-person',
      'mention-only',
      'document-only',
    ])
    expect(model().hasNextPage.value).toBe(false)
    expect(api.search).not.toHaveBeenCalled()
    wrapper.unmount()
    client.clear()
  })

  it('uses one global relevance cursor rather than prioritizing local tiers during search', async () => {
    api.search.mockImplementation(({ query }) => {
      expect(query).toMatchObject({
        sort: 'relevance',
        sort_direction: 'desc',
        'query.text': ['Hana'],
      })
      expect(query).not.toHaveProperty('filter.page_source_id')
      expect(query).not.toHaveProperty('filter.document_source_id')
      return Promise.resolve({
        data: query.cursor
          ? { items: [person('page-match', { score: 0.7 })], cursor: null, total_count: 2 }
          : { items: [person('outside-match', { score: 0.9 })], cursor: 'next', total_count: 2 },
      })
    })
    api.entities.mockResolvedValue({ data: { items: [], cursor: null } })
    const { model, wrapper, client } = mountPeople({
      scope: 'all',
      order: 'relevance',
      search: { text: 'Hana' },
    })
    await flushPromises()
    await model().loadMore()
    await flushPromises()
    expect(model().people.value.map((item) => item.id)).toEqual(['outside-match', 'page-match'])
    expect(model().totalCount.value).toBe(2)
    expect(api.search).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    client.clear()
  })

  it('combines name text and the attached face in one ranked search per scope', async () => {
    api.search.mockResolvedValue({
      data: {
        items: [
          person('ada', {
            score: 0.03,
            text_score: 0.8,
            face_score: 0.9,
            matched_detection_ids: ['f'],
          }),
        ],
        cursor: null,
        total_count: 1,
      },
    })
    const { model, wrapper, client } = mountPeople({
      scope: 'document',
      order: 'relevance',
      search: { text: ' Ada ', face: { id: 'face-a', embeddingModel: 'model' } },
    })
    await flushPromises()
    expect(api.search).toHaveBeenCalledTimes(1)
    expect(api.search.mock.calls[0]![0].query).toMatchObject({
      'filter.entity_type': ['person'],
      'filter.document_source_id': ['document-source'],
      'query.text': ['Ada'],
      'query.face_id': ['face-a'],
      'query.face_embedding_model': 'model',
      sort: 'relevance',
      sort_direction: 'desc',
    })
    expect(model().totalCount.value).toBe(1)
    const [ada] = model().people.value
    expect(ada).toMatchObject({ id: 'ada', faceId: 'f', referenceFaceId: 'face-a' })
    expect(ada?.matchSources?.map((source) => source.type)).toEqual([
      'text-search',
      'face-match',
      'in-document',
    ])
    expect(api.entities).not.toHaveBeenCalled()
    wrapper.unmount()
    client.clear()
  })

  it('reports a face the API cannot search with, not other failures (#134)', async () => {
    const rejected = (status: number, code?: string) =>
      new AxiosError('failed', 'ERR_BAD_REQUEST', undefined, undefined, {
        status,
        data: code ? { detail: { code, message: 'x' } } : {},
      } as AxiosResponse)
    const face = { id: 'zero', embeddingModel: 'model' }
    api.search.mockRejectedValue(rejected(422, 'invalid_search'))
    const unusable = mountPeople({ order: 'relevance', search: { text: '', face } })
    await flushPromises()
    expect(unusable.model().faceRejected.value).toBe(true)
    expect(unusable.model().error.value).toBeInstanceOf(AxiosError)
    unusable.wrapper.unmount()
    unusable.client.clear()

    api.search.mockRejectedValue(rejected(500))
    const outage = mountPeople({ order: 'relevance', search: { text: '', face } })
    await flushPromises()
    expect(outage.model().error.value).toBeInstanceOf(AxiosError)
    expect(outage.model().faceRejected.value).toBe(false)
    outage.wrapper.unmount()
    outage.client.clear()

    api.search.mockRejectedValue(rejected(422, 'invalid_search'))
    const text = mountPeople({ order: 'relevance', search: { text: 'Ada' } })
    await flushPromises()
    expect(text.model().faceRejected.value).toBe(false)
    text.wrapper.unmount()
    text.client.clear()
  })
})
