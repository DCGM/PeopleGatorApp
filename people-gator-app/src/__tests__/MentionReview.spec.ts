import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { resolveMentionTargets, useReviewMentionsMutation } from '@/query/mention-review'
import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'
const api = vi.hoisted(() => ({ list: vi.fn(), patch: vi.fn(), groups: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listTextMentionsRouteApiV1TextMentionsGet: api.list,
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch: api.patch,
  listTextMentionGroupsRouteApiV1TextMentionGroupsGet: api.groups,
}))
vi.mock('@/query/client', () => ({
  getAccessToken: async () =>
    `header.${btoa(JSON.stringify({ scopes: ['people-gator:annotate'] }))}.sig`,
}))
beforeEach(() => {
  vi.clearAllMocks()
  api.groups.mockResolvedValue({
    data: { items: [{ name: 'Ada', occurrence_count: 102 }], limit: 25, cursor: null },
  })
  api.patch.mockImplementation(async ({ body }) => ({
    data: body.map((item: { mention_id: string }) => ({ ...item })),
  }))
  api.list.mockImplementation(async ({ query }) => ({
    data: {
      items: query.cursor
        ? [{ mention_id: 'last' }, { mention_id: 'm0' }]
        : Array.from({ length: 100 }, (_, i) => ({ mention_id: `m${i}` })),
      cursor: query.cursor ? null : 'next',
      limit: 100,
    },
  }))
})
it('resolves every filtered cursor and deduplicates before any review write', async () => {
  const scope = {
    'filter.entity_id': ['person'],
    'filter.name': ['Ada'],
    'filter.library': ['one'],
    'filter.entity_link_state': ['manual' as const],
  }
  const ids = await resolveMentionTargets({ scopes: [scope] })
  expect(ids).toHaveLength(101)
  expect(ids[ids.length - 1]).toBe('last')
  expect(api.list.mock.calls[1]![0].query).toMatchObject({ ...scope, cursor: 'next' })
  expect(api.patch).not.toHaveBeenCalled()
})
it('skips already-verified occurrences only when verifying', async () => {
  api.list.mockResolvedValueOnce({
    data: {
      items: [
        { mention_id: 'auto', entity_link_state: 'automatic' },
        { mention_id: 'done', entity_link_state: 'verified' },
      ],
      cursor: null,
      limit: 100,
    },
  })
  const targets = {
    scopes: [{ 'filter.name': ['Ada'] }],
    ids: ['picked', 'loaded-done'],
    verifiedIds: ['loaded-done'],
  }
  expect(await resolveMentionTargets(targets, 'verify')).toEqual(['auto', 'picked'])
  api.list.mockResolvedValueOnce({
    data: {
      items: [{ mention_id: 'done', entity_link_state: 'verified' }],
      cursor: null,
      limit: 100,
    },
  })
  expect(await resolveMentionTargets(targets, 'unlink')).toEqual(['done', 'picked', 'loaded-done'])
})
it('selects exact text independently of expansion and reviews unloaded occurrences', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = mount(PersonMentionGroups, {
    props: {
      filters: { 'filter.entity_id': ['person'], 'filter.library': ['one'] },
      groupSort: { field: 'text', direction: 'asc' },
      occurrenceSort: { field: 'text', direction: 'asc' },
      personId: 'person',
      linkStates: [],
      compact: true,
    },
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  await wrapper.get('[aria-label="Select group Ada"]').trigger('click')
  expect(wrapper.get('[role="toolbar"]').text()).toContain('102 mentions selected')
  expect(api.list).not.toHaveBeenCalled()
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Verify')!
    .trigger('click')
  await flushPromises()
  expect(api.list.mock.calls[0]![0].query).toMatchObject({
    'filter.name': ['Ada'],
    'filter.library': ['one'],
    'filter.entity_id': ['person'],
  })
  expect(api.patch.mock.calls.flatMap((call) => call[0].body)).toHaveLength(101)
  expect(api.patch.mock.calls[api.patch.mock.calls.length - 1]![0].body).toEqual([
    { mention_id: 'last', entity_link_state: 'verified' },
  ])
  await wrapper.get('[aria-label="Select group Ada"]').trigger('click')
  await router.push('/?mention_view=page')
  await flushPromises()
  expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
  wrapper.unmount()
  client.clear()
})
it('reports confirmed chunks on failure and invalidates counts and lists', async () => {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  let mutation: ReturnType<typeof useReviewMentionsMutation>
  const wrapper = mount(
    defineComponent({
      setup() {
        mutation = useReviewMentionsMutation()
        return () => null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  api.patch
    .mockResolvedValueOnce({ data: Array.from({ length: 50 }, () => ({ mention_id: 'ok' })) })
    .mockRejectedValueOnce(new Error('network'))
  await expect(
    mutation!.mutateAsync({
      targets: { ids: Array.from({ length: 60 }, (_, i) => String(i)) },
      action: 'unlink',
    }),
  ).rejects.toThrow('50 of 60 updates confirmed')
  expect(
    invalidate.mock.calls.map(([arg]) => typeof arg === 'object' && arg?.queryKey?.[0]),
  ).toEqual(expect.arrayContaining(['text-mentions', 'entities', 'documents', 'pages', 'search']))
  wrapper.unmount()
  client.clear()
})
