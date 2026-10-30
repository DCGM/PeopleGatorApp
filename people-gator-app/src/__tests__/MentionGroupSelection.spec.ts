import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'
import { resolveMentionTargets } from '@/query/mention-review'
const api = vi.hoisted(() => ({ list: vi.fn(), groups: vi.fn(), patch: vi.fn() }))
// jsdom has no layout: reveal each list end by invoking its automatic pagination.
const pagination = vi.hoisted(
  () => [] as Array<{ hasNextPage: { value: boolean }; loadMore: () => Promise<unknown> }>,
)
vi.mock('@/composables/automatic-pagination', () => ({
  useAutomaticPagination: (options: (typeof pagination)[number]) => pagination.push(options),
}))
async function revealListEnds() {
  await Promise.all(pagination.filter((o) => o.hasNextPage.value).map((o) => o.loadMore()))
}
vi.mock('@/composables/can-annotate', async () => {
  const { ref } = await import('vue')
  return { useCanAnnotate: () => ref(true) }
})
vi.mock('@/viewmodels/person-mentions', async () => {
  const { computed, toValue } = await import('vue')
  return {
    useMentionViews: (records: Parameters<typeof toValue>[0]) =>
      computed(() =>
        (toValue(records) as { mention_id: string }[]).map((record) => ({
          id: record.mention_id,
          excerpt: 'Ada signed',
          matchedText: 'Ada',
          pageId: '',
          sourceLoading: false,
        })),
      ),
  }
})
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listTextMentionGroupsRouteApiV1TextMentionGroupsGet: api.groups,
  listTextMentionsRouteApiV1TextMentionsGet: api.list,
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch: api.patch,
}))
beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockImplementation(async ({ query }) => ({
    data: {
      items: (query.cursor ? ['m3'] : ['m1', 'm2']).map((mention_id) => ({ mention_id })),
      cursor: query.cursor ? null : 'last',
      total_count: 3,
      limit: 2,
    },
  }))
  api.patch.mockImplementation(async ({ body }) => ({ data: body }))
})
it.each(['mention', 'document', 'page'] as const)(
  'shares tri-state parent/child selection in expanded and compact %s groups',
  async (mode) => {
    api.groups.mockResolvedValue({
      data: {
        items: [
          {
            name: 'Ada',
            occurrence_count: 3,
            ...(mode !== 'mention' && {
              source_kind: mode,
              source_id: 'source',
              library: 'NDK',
              document_id: 'doc',
              ...(mode === 'page' && { page_id: 'page' }),
            }),
          },
        ],
        cursor: null,
        total_count: 1,
        limit: 25,
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/scans', name: 'document-search', component: { template: '<div />' } },
        {
          path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
          name: 'document-page',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(PersonMentionGroups, {
      props: {
        mode,
        filters: { 'filter.entity_id': ['person'] },
        groupSort: { field: 'text', direction: 'asc' },
        occurrenceSort: { field: 'text', direction: 'asc' },
        personId: 'person',
        linkStates: [],
      },
      global: {
        plugins: [router, [VueQueryPlugin, { queryClient: client }]],
        stubs: { RouterLink: RouterLinkStub },
      },
    })
    await flushPromises()
    const parent = () => wrapper.get('[aria-label="Select group Ada"]')
    const child = (id: string) => wrapper.get(`[aria-label="Select mention ${id}"]`)
    expect(parent().attributes('aria-checked')).toBe('false')
    expect(child('m1').attributes('aria-checked')).toBe('false')
    await child('m1').trigger('click')
    expect(parent().attributes('aria-checked')).toBe('mixed')
    expect(wrapper.get('[role=toolbar]').text()).toContain('1 mention selected')
    await parent().trigger('click')
    expect(parent().attributes('aria-checked')).toBe('true')
    expect(child('m1').attributes('aria-checked')).toBe('true')
    expect(child('m2').attributes('aria-checked')).toBe('true')
    expect(wrapper.findAll('button').some((b) => b.text().startsWith('Load more'))).toBe(false)
    await revealListEnds()
    await flushPromises()
    expect(child('m3').attributes('aria-checked')).toBe('true')
    await child('m2').trigger('click')
    expect(parent().attributes('aria-checked')).toBe('mixed')
    expect(parent().find('svg').exists()).toBe(true)
    await wrapper.setProps({ compact: true, filters: { 'filter.entity_id': ['person'] } })
    expect(wrapper.find('[aria-label="Select mention m1"]').exists()).toBe(false)
    expect(parent().attributes('aria-checked')).toBe('mixed')
    await wrapper.setProps({ compact: false })
    await flushPromises()
    expect(child('m1').attributes('aria-checked')).toBe('true')
    expect(child('m2').attributes('aria-checked')).toBe('false')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Verify')!
      .trigger('click')
    await flushPromises()
    expect(
      api.patch.mock.calls.flatMap(([arg]) =>
        arg.body.map((item: { mention_id: string }) => item.mention_id),
      ),
    ).toEqual(['m1', 'm3'])
    expect(parent().attributes('aria-checked')).toBe('false')
    await parent().trigger('click')
    await parent().trigger('click')
    expect(child('m1').attributes('aria-checked')).toBe('false')
    expect(wrapper.find('[role=toolbar]').exists()).toBe(false)
    await child('m1').trigger('click')
    await wrapper.setProps({ filters: { 'filter.entity_id': ['other-person'] } })
    await flushPromises()
    expect(parent().attributes('aria-checked')).toBe('false')
    wrapper.unmount()
    client.clear()
  },
)
it('combines selected groups and individual occurrences, applying exclusions after cursor deduplication', async () => {
  const ids = await resolveMentionTargets({
    scopes: [{ 'filter.name': ['Ada'] }],
    ids: ['standalone', 'm3'],
    excludeIds: ['m2'],
  })
  expect(ids).toEqual(['m1', 'm3', 'standalone'])
  expect(api.list.mock.calls).toHaveLength(2)
})

it('adds forward and reverse flat ranges, includes appended rows and clears stale anchors', async () => {
  const { default: ReviewList } = await import('@/components/custom/PersonMentionReviewList.vue')
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/scans', name: 'document-search', component: { template: '<div />' } },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/')
  const client = new QueryClient()
  const mentions = (ids: string[]) =>
    ids.map((id) => ({
      id,
      excerpt: 'Ada signed',
      matchedText: 'Ada',
      pageId: '',
    })) as import('@/viewmodels/person-detail.types').PersonMention[]
  const wrapper = mount(ReviewList, {
    props: {
      mentions: mentions(['m1', 'm2', 'm3', 'm4', 'm5']),
      personId: 'person',
      linkStates: [],
    },
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  const click = (id: string, shiftKey = false) =>
    wrapper.get(`[aria-label="Select mention ${id}"]`).trigger('click', { shiftKey })
  const ids = () =>
    wrapper
      .findAll('[aria-checked=true]')
      .map((node) => node.attributes('aria-label')!.replace('Select mention ', ''))
  await click('m2')
  await click('m5', true)
  expect(ids()).toEqual(['m2', 'm3', 'm4', 'm5'])
  await click('m1', true)
  expect(ids()).toEqual(['m1', 'm2', 'm3', 'm4', 'm5'])
  await wrapper
    .get('[role=toolbar]')
    .findAll('button')
    .find((b) => b.text() === 'Clear')!
    .trigger('click')
  await click('m4', true)
  expect(ids()).toEqual(['m4'])
  await wrapper.setProps({ mentions: mentions(['m1', 'm2', 'm3', 'm4', 'm5', 'm6']) })
  await click('m6', true)
  expect(ids()).toEqual(['m4', 'm5', 'm6'])
  await wrapper.setProps({ mentions: mentions(['m1', 'm2', 'm3', 'm5', 'm6']) })
  await click('m1', true)
  expect(ids()).toEqual(['m1', 'm5', 'm6'])
  await router.push('/?mention_sort=source')
  await flushPromises()
  await click('m2', true)
  expect(ids()).toEqual(['m2'])
  wrapper.unmount()
  client.clear()
})

it.each(['mention', 'document', 'page'] as const)(
  'selects occurrence ranges across %s boundaries and whole compact group ranges',
  async (mode) => {
    api.groups.mockResolvedValue({
      data: {
        items: ['a', 'b'].map((name) => ({
          name,
          source_id: mode === 'mention' ? null : name,
          source_kind: mode,
          ...(mode !== 'mention' && { library: 'NDK', document_id: 'doc' }),
          ...(mode === 'page' && { page_id: name }),
          occurrence_count: 2,
        })),
        limit: 25,
        cursor: null,
        total_count: 2,
      },
    })
    api.list.mockImplementation(async ({ query }) => {
      const name = (query['filter.name'] ??
        query['filter.source_id'] ??
        query['filter.document_source_id'])[0]
      return {
        data: {
          items: [1, 2].map((i) => ({ mention_id: `${name}${i}` })),
          cursor: null,
          limit: 20,
        },
      }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/scans', name: 'document-search', component: { template: '<div />' } },
        {
          path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
          name: 'document-page',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/')
    const client = new QueryClient()
    const wrapper = mount(PersonMentionGroups, {
      props: {
        mode,
        personId: 'person',
        filters: { 'filter.entity_id': ['person'] },
        groupSort: { field: 'text', direction: 'asc' },
        occurrenceSort: { field: 'text', direction: 'asc' },
        linkStates: [],
      },
      global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
    })
    await flushPromises()
    const click = (kind: string, id: string, shiftKey = false) =>
      wrapper.get(`[aria-label="Select ${kind} ${id}"]`).trigger('click', { shiftKey })
    const ids = () =>
      wrapper
        .findAll('[aria-label^="Select mention"][aria-checked=true]')
        .map((node) => node.attributes('aria-label')!.replace('Select mention ', ''))
    const clear = () =>
      wrapper
        .get('[role=toolbar]')
        .findAll('button')
        .find((b) => b.text() === 'Clear')!
        .trigger('click')
    await click('mention', 'a2')
    await click('mention', 'b2', true)
    expect(ids()).toEqual(['a2', 'b1', 'b2'])
    expect(wrapper.get('[aria-label="Select group a"]').attributes('aria-checked')).toBe('mixed')
    expect(wrapper.get('[aria-label="Select group b"]').attributes('aria-checked')).toBe('true')
    await clear()
    await click('mention', 'b2')
    await click('mention', 'a2', true)
    expect(ids()).toEqual(['a2', 'b1', 'b2'])
    await clear()
    await wrapper.setProps({ compact: true })
    await click('group', 'a')
    await click('group', 'b', true)
    expect(wrapper.get('[role=toolbar]').text()).toContain('4 mentions selected')
    await wrapper.setProps({ compact: false })
    await flushPromises()
    expect(ids()).toEqual(['a1', 'a2', 'b1', 'b2'])
    await wrapper.setProps({ occurrenceSort: { field: 'source', direction: 'asc' } })
    await flushPromises()
    await click('mention', 'b2', true)
    expect(ids()).toEqual(['b2'])
    wrapper.unmount()
    client.clear()
  },
)
