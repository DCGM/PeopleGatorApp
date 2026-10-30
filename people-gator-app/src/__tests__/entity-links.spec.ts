import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EntityLinkStateBadge from '@/components/custom/EntityLinkStateBadge.vue'
import EntityLinkStateFilter from '@/components/custom/EntityLinkStateFilter.vue'
import EntityLinkStatistics from '@/components/custom/EntityLinkStatistics.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import VerifyEntityLink from '@/components/custom/VerifyEntityLink.vue'
import { useLinkStateFilter } from '@/composables/link-state-filter'
import { useFaceListQuery, useDeleteFaceMutation } from '@/query/faces'
import { usePageResultsQuery } from '@/query/search/pages'
import { usePersonDetail } from '@/viewmodels/person-detail'
import type { EntityLinkState } from '@/client'

const api = vi.hoisted(() => ({
  pagesList: vi.fn(),
  pagesSearch: vi.fn(),
  faces: vi.fn(),
  mentions: vi.fn(),
  entity: vi.fn(),
  patchFace: vi.fn(),
  deleteFace: vi.fn(),
  patchMention: vi.fn(),
  page: vi.fn(),
}))
vi.mock('@/client', () => ({
  listFacesRouteApiV1FacesGet: api.faces,
  deleteFaceRouteApiV1FacesDetectionIdDelete: api.deleteFace,
  listPagesRouteApiV1PagesGet: api.pagesList,
  searchPagesGetApiV1SearchPagesGet: api.pagesSearch,
  listTextMentionsRouteApiV1TextMentionsGet: api.mentions,
  getEntityRouteApiV1EntitiesEntityIdGet: api.entity,
  patchFaceRouteApiV1FacesDetectionIdPatch: api.patchFace,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch: api.patchMention,
  getPageRouteApiV1PagesPageSourceIdGet: api.page,
}))
vi.mock('@/query/client', () => ({
  getAccessToken: async () =>
    `header.${btoa(JSON.stringify({ scopes: ['people-gator:annotate'] }))}.sig`,
}))
vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: ref({}) }),
}))
const cleanup: (() => void)[] = []
const counts = { automatic: 2, manual: 3, verified: 5, unassigned: 0, total: 10 }
function renderQuery(setup: () => () => ReturnType<typeof h>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = mount(defineComponent({ setup }), {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  cleanup.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  return { wrapper, queryClient }
}
beforeEach(() => {
  vi.clearAllMocks()
  api.faces.mockResolvedValue({ data: { items: [], limit: 100, total_count: 0, cursor: null } })
  api.mentions.mockResolvedValue({ data: { items: [], limit: 100, total_count: 0, cursor: null } })
  api.entity.mockResolvedValue({
    data: { entity_id: 'ada', name: 'Ada', entity_link_stats: { faces: counts, mentions: counts } },
  })
})
afterEach(() =>
  cleanup
    .splice(0)
    .reverse()
    .forEach((fn) => fn()),
)

describe('entity link review', () => {
  it('shows an icon and an accessible label for each state, with local and UTC verification time', () => {
    for (const state of ['automatic', 'manual', 'verified', null] as const) {
      const wrapper = mount(EntityLinkStateBadge, {
        props: {
          linkState: state,
          compact: true,
          verifiedBy: 'reviewer-id',
          verifiedAt: '2026-10-13T12:00:00Z',
        },
      })
      const badge = wrapper.get('[data-slot="badge"]')
      expect(badge.text()).toBe('')
      expect(badge.get('svg').attributes('aria-hidden')).toBe('true')
      expect(badge.attributes('tabindex')).toBe('0')
      expect(badge.attributes('aria-label')).toBeTruthy()
      if (state === 'verified') {
        expect(badge.attributes('title')).toContain('reviewer-id')
        expect(badge.attributes('title')).toContain('UTC: 2026-10-13T12:00:00Z')
      }
      wrapper.unmount()
    }
  })

  it('supports OR selections and distinguishes all assigned states from All', async () => {
    const selected = ref<EntityLinkState[]>([])
    const wrapper = mount(
      defineComponent({
        setup: () => () =>
          h(EntityLinkStateFilter, {
            toolbar: true,
            modelValue: selected.value,
            'onUpdate:modelValue': (value) => {
              selected.value = value
            },
          }),
      }),
    )
    cleanup.push(() => wrapper.unmount())
    for (const label of ['Automatic', 'Manual', 'Verified'])
      await wrapper.get(`[aria-label="${label}"]`).trigger('click')
    expect(selected.value).toEqual(['automatic', 'manual', 'verified'])
    for (const label of ['Automatic', 'Manual', 'Verified'])
      expect(wrapper.get(`[aria-label="${label}"]`).attributes('aria-pressed')).toBe('true')
    await wrapper.get('button:not([data-slot="toggle-group-item"])').trigger('click')
    expect(selected.value).toEqual([])
    await wrapper.get('[aria-label="Manual"]').trigger('click')
    await wrapper.get('[aria-label="Manual"]').trigger('click')
    expect(selected.value).toEqual([])
  })

  it('restores repeated URL states on back/forward and preserves other query parameters', async () => {
    let selected: ReturnType<typeof useLinkStateFilter>
    const harness = defineComponent({
      setup() {
        selected = useLinkStateFilter()
        return () => h('div')
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/scan/:id', component: harness }],
    })
    await router.push('/scan/1?line=L4&translate=on&link_state=automatic&link_state=verified')
    const wrapper = mount(harness, { global: { plugins: [router] } })
    cleanup.push(() => wrapper.unmount())
    expect(selected!.value).toEqual(['automatic', 'verified'])
    selected!.value = ['manual']
    await flushPromises()
    expect(router.currentRoute.value.query.line).toBe('L4')
    expect(router.currentRoute.value.query.translate).toBe('on')
    expect(router.currentRoute.value.query.link_state).toEqual(['manual'])
    router.back()
    await flushPromises()
    expect(selected!.value).toEqual(['automatic', 'verified'])
    router.forward()
    await flushPromises()
    expect(selected!.value).toEqual(['manual'])
  })

  it('uses the same server filter for both person lists without fetching discovery references', async () => {
    const states = ref<EntityLinkState[]>(['verified'])
    let detail: ReturnType<typeof usePersonDetail>
    renderQuery(() => {
      detail = usePersonDetail('ada', states)
      return () => h('div')
    })
    await flushPromises()
    expect(
      api.faces.mock.calls.some(
        ([args]) =>
          args.query['filter.entity_link_state']?.[0] === 'verified' &&
          args.query['filter.entity_id'][0] === 'ada',
      ),
    ).toBe(true)
    expect(
      api.faces.mock.calls.some(([args]) => args.query['filter.entity_link_state'] === undefined),
    ).toBe(false)
    expect(api.mentions.mock.calls[0]![0].query['filter.entity_link_state']).toEqual(['verified'])
    expect(detail!.entity.value?.entity_link_stats?.faces?.total).toBe(10)
    expect(detail!.faceCount.value).toBe(0)
    states.value = ['automatic', 'manual']
    await flushPromises()
    expect(
      api.mentions.mock.calls[api.mentions.mock.calls.length - 1]![0].query[
        'filter.entity_link_state'
      ],
    ).toEqual(['automatic', 'manual'])
  })

  it('starts a new cursor chain when the state changes and ignores a late old response', async () => {
    const states = ref<EntityLinkState[]>(['automatic'])
    let resolveOld: (value: unknown) => void = () => {}
    api.faces.mockImplementation(({ query }) =>
      query['filter.entity_link_state'][0] === 'automatic'
        ? new Promise((resolve) => {
            resolveOld = resolve
          })
        : Promise.resolve({
            data: {
              items: [{ detection_id: 'verified-face' }],
              limit: 1,
              total_count: 1,
              cursor: null,
            },
          }),
    )
    let query: ReturnType<typeof useFaceListQuery>
    renderQuery(() => {
      query = useFaceListQuery(
        computed(() => ({ limit: 1, 'filter.entity_link_state': states.value })),
      )
      return () => h('div')
    })
    await flushPromises()
    states.value = ['verified']
    await flushPromises()
    expect(api.faces.mock.calls[api.faces.mock.calls.length - 1]![0].query.cursor).toBeNull()
    resolveOld({ data: { items: [{ detection_id: 'old-face' }], limit: 1, cursor: 'old-next' } })
    await flushPromises()
    expect(query!.data.value?.pages[0]?.items[0]?.detection_id).toBe('verified-face')
  })

  it('forwards link states through scan browsing/search and restarts their cursor chains', async () => {
    const states = ref<EntityLinkState[]>(['verified'])
    const term = ref('')
    api.pagesList.mockResolvedValue({
      data: { items: [{ source_id: 'p1' }], limit: 1, total_count: 2, cursor: 'next' },
    })
    api.pagesSearch.mockResolvedValue({
      data: { items: [], limit: 1, total_count: 0, cursor: null },
    })
    let query: ReturnType<typeof usePageResultsQuery>
    renderQuery(() => {
      query = usePageResultsQuery(
        computed(() => ({ query: term.value, 'filter.entity_link_state': states.value, limit: 1 })),
      )
      return () => h('div')
    })
    await flushPromises()
    expect(api.pagesList.mock.calls[0]![0].query['filter.entity_link_state']).toEqual(['verified'])
    await query!.fetchNextPage()
    await flushPromises()
    expect(api.pagesList.mock.calls[1]![0].query.cursor).toBe('next')
    states.value = ['manual']
    await flushPromises()
    const browse = api.pagesList.mock.calls[api.pagesList.mock.calls.length - 1]![0].query
    expect(browse['filter.entity_link_state']).toEqual(['manual'])
    expect(browse.cursor).toBeNull()
    term.value = 'Ada'
    await flushPromises()
    expect(api.pagesSearch.mock.calls[0]![0].query['filter.entity_link_state']).toEqual(['manual'])
    states.value = ['automatic', 'verified']
    await flushPromises()
    const ranked = api.pagesSearch.mock.calls[api.pagesSearch.mock.calls.length - 1]![0].query
    expect(ranked['filter.entity_link_state']).toEqual(['automatic', 'verified'])
    expect(ranked.cursor).toBeNull()
  })

  it('keeps multiline mentions accessible and selectable without hover tooltips', async () => {
    const wrapper = mount(DocumentTeleprompter, {
      props: {
        selectedLineIndex: 0,
        selectedEntityKey: null,
        relatedEntityId: null,
        transcription: [
          {
            id: 'L1',
            text: 'Ada',
            position: { left: 0, top: 0, width: 1, height: 1 },
            entities: [
              {
                mention_id: 'm1',
                entity_id: 'ada',
                label: 'person',
                text: 'Ada',
                line_id: 'L1',
                start_index: 0,
                end_index: 3,
                linkState: 'verified',
                firstFragment: true,
              },
            ],
          },
          {
            id: 'L2',
            text: 'Novak and Ada Novak',
            position: { left: 0, top: 0, width: 1, height: 1 },
            entities: [
              {
                mention_id: 'm1',
                entity_id: 'ada',
                label: 'person',
                text: 'Novak',
                line_id: 'L2',
                start_index: 0,
                end_index: 5,
                linkState: 'verified',
                firstFragment: false,
              },
              {
                mention_id: 'm2',
                entity_id: 'ada',
                label: 'person',
                text: 'Ada Novak',
                line_id: 'L2',
                start_index: 10,
                end_index: 19,
                linkState: 'manual',
                firstFragment: true,
              },
            ],
          },
        ],
      },
    })
    cleanup.push(() => wrapper.unmount())
    expect(wrapper.findAll('[data-face-status-badge]')).toHaveLength(2)
    expect(wrapper.findAll('mark').map((mark) => mark.text())).toEqual([
      'Ada',
      'Novak',
      'Ada Novak',
    ])
    expect(wrapper.find('[title]').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'UiTooltip' }).exists()).toBe(false)
    const mention = wrapper.findAll('mark')[2]!
    expect(mention.attributes('aria-label')).toContain('Ada Novak:')
    expect(mention.attributes('tabindex')).toBe('0')
    await mention.trigger('mouseenter')
    expect(mention.attributes('style')).toContain('outline:')
    await mention.trigger('mouseleave')
    for (const event of ['click', 'keydown.enter', 'keydown.space']) {
      await mention.trigger(event)
    }
    expect(wrapper.emitted('select-entity')).toHaveLength(3)
    expect(wrapper.emitted('select-entity')![0]![0]).toBe(1)
    expect(wrapper.emitted('select-entity')![0]![1]).toMatchObject({ mention_id: 'm2' })
    await wrapper.setProps({ selectedEntityKey: 'm2' })
    expect(mention.attributes('style')).toContain('outline:')
  })

  it.each([false, true])(
    'verifies links and recovers from failure with inline=%s',
    async (inline) => {
      api.patchFace
        .mockRejectedValueOnce(new Error('Try again'))
        .mockResolvedValueOnce({ data: { detection_id: 'f1', entity_link_state: 'verified' } })
      const { wrapper, queryClient } = renderQuery(
        () => () => h(VerifyEntityLink, { id: 'f1', kind: 'face', linkState: 'manual', inline }),
      )
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
      await flushPromises()
      await wrapper.get('button').trigger('click')
      await flushPromises()
      expect(wrapper.get('[role="alert"]').text()).toContain('Could not verify')
      expect(invalidate).not.toHaveBeenCalled()
      await wrapper.get('button').trigger('click')
      await flushPromises()
      const keys = invalidate.mock.calls.map(
        ([args]) => (typeof args === 'function' ? args() : args)?.queryKey?.[0],
      )
      expect(keys).toEqual(
        expect.arrayContaining([
          'faces',
          'text-mentions',
          'entities',
          'pages',
          'documents',
          'sources',
          'search',
        ]),
      )
      expect(api.patchFace.mock.calls[api.patchFace.mock.calls.length - 1]![0].body).toEqual({
        entity_link_state: 'verified',
      })
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    },
  )

  it('keeps a verified inline action empty while retaining verification details in ordinary use', async () => {
    const inline = ref(true)
    const { wrapper } = renderQuery(
      () => () =>
        h(VerifyEntityLink, {
          id: 'f1',
          kind: 'face',
          linkState: 'verified',
          inline: inline.value,
          verifiedBy: 'reviewer',
          verifiedAt: '2026-10-13T12:00:00Z',
        }),
    )
    await flushPromises()
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
    expect(api.patchFace).not.toHaveBeenCalled()
    inline.value = false
    await flushPromises()
    expect(wrapper.text()).toContain('Verified by reviewer')
    expect(wrapper.text()).toContain('UTC: 2026-10-13T12:00:00Z')
  })

  it('displays server totals and unassigned counts independently of loaded thumbnails', () => {
    const wrapper = mount(EntityLinkStatistics, {
      props: {
        stats: { faces: { ...counts, unassigned: 4, total: 14 }, mentions: counts },
        unassigned: true,
      },
    })
    expect(wrapper.text()).toContain('Unassigned 4')
    expect(wrapper.text()).toContain('Total 14')
    expect(wrapper.findAll('[aria-label="Verified: 5 faces"]')).toHaveLength(1)
    wrapper.unmount()
  })

  it('shows titled person annotation groups without a competing total', () => {
    const wrapper = mount(EntityLinkStatistics, {
      props: {
        stats: { faces: { ...counts, total: 14 }, mentions: { ...counts, verified: 0 } },
        layout: 'person',
      },
    })
    const groups = wrapper.findAll('dd')
    expect(wrapper.findAll('dt').map((title) => title.text())).toEqual([
      'Face annotations',
      'Mention annotations',
    ])
    expect(groups[0]!.classes()).toEqual(
      expect.arrayContaining(['flex-row-reverse', 'justify-between', 'font-mono']),
    )
    expect(
      groups[0]!.findAll('[tabindex="0"]').map((item) => item.attributes('aria-label')),
    ).toEqual([
      `Automatic: ${counts.automatic} faces`,
      `Manual: ${counts.manual} faces`,
      'Verified: 5 faces',
    ])
    expect(wrapper.find('[aria-label="Verified: 0 mentions"]').text()).toBe('0')
    expect(wrapper.text()).not.toContain('Total')
    wrapper.unmount()
  })
})

it('preserves a rejected deletion, then removes cached detail/crops and refreshes affected lists', async () => {
  api.deleteFace.mockRejectedValueOnce(new Error('Forbidden')).mockResolvedValueOnce({ data: null })
  const { wrapper, queryClient } = renderQuery(() => {
    const mutation = useDeleteFaceMutation()
    return () =>
      h(
        'button',
        { onClick: () => mutation.mutate('f1') },
        mutation.error.value ? 'Failed' : 'Delete',
      )
  })
  queryClient.setQueryData(['faces', 'detail', 'f1'], { detection_id: 'f1' })
  queryClient.setQueryData(['face-crops', 'aligned', 'f1', 128], new Blob())
  queryClient.setQueryData(['faces', 'detail', 'other'], { detection_id: 'other' })
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toBe('Failed')
  expect(queryClient.getQueryData(['faces', 'detail', 'f1'])).toBeDefined()
  expect(invalidate).not.toHaveBeenCalled()
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(api.deleteFace).toHaveBeenLastCalledWith({
    path: { detection_id: 'f1' },
    throwOnError: true,
  })
  expect(queryClient.getQueryData(['faces', 'detail', 'f1'])).toBeUndefined()
  expect(queryClient.getQueryData(['face-crops', 'aligned', 'f1', 128])).toBeUndefined()
  expect(queryClient.getQueryData(['faces', 'detail', 'other'])).toBeDefined()
  expect(
    invalidate.mock.calls.map(([arg]) => (typeof arg === 'function' ? arg() : arg)?.queryKey?.[0]),
  ).toEqual(
    expect.arrayContaining([
      'faces',
      'entities',
      'pages',
      'documents',
      'sources',
      'images',
      'search',
    ]),
  )
})
