import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'
import { resolveMentionTargets } from '@/query/mention-review'
const api = vi.hoisted(() => ({ list: vi.fn(), groups: vi.fn(), patch: vi.fn() }))
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
      routes: [{ path: '/', component: { template: '<div />' } }],
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
    expect(wrapper.get('[role=toolbar]').text()).toContain('1 occurrences')
    await parent().trigger('click')
    expect(parent().attributes('aria-checked')).toBe('true')
    expect(child('m1').attributes('aria-checked')).toBe('true')
    expect(child('m2').attributes('aria-checked')).toBe('true')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Load more occurrences')!
      .trigger('click')
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
