import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent } from 'vue'
import { createMemoryHistory, createRouter, useRoute } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
type ApiCall = (request: {
  path: { entity_id: string }
  query: Record<string, string | string[] | boolean | undefined>
}) => Promise<unknown>
const api = vi.hoisted(() => ({
  faces: vi.fn<ApiCall>(),
  mentions: vi.fn<ApiCall>(),
  entity: vi.fn<ApiCall>(),
}))
vi.mock('@/client', () => ({
  listFacesRouteApiV1FacesGet: api.faces,
  listTextMentionsRouteApiV1TextMentionsGet: api.mentions,
  getEntityRouteApiV1EntitiesEntityIdGet: api.entity,
}))
import { useSharedFilters, relatedQuery } from '@/viewmodels/shared-filters'
import { usePersonDetail } from '@/viewmodels/person-detail'
const one = '00000000-0000-4000-8000-000000000001',
  two = '00000000-0000-4000-8000-000000000002'
const Harness = defineComponent({
  setup() {
    const route = useRoute(),
      evidence = useSharedFilters()
    const detail = usePersonDetail(
      () => String(route.params.personId),
      () => evidence.filters.value.linkStates,
      evidence.params,
      computed(() => !evidence.error.value),
    )
    return {
      detail,
      summary: computed(
        () =>
          `${detail.faceCount.value} matching of ${detail.entity.value?.entity_link_stats?.faces?.total ?? 0} faces`,
      ),
    }
  },
  template: '<p>{{ summary }}</p><button @click="detail.loadMoreFaces()">More</button>',
})
describe('copied profile URLs and evidence requests', () => {
  it('keeps fixed person scope, server counts/cursors, filter edits and Back/Forward', async () => {
    api.entity.mockImplementation(({ path }) =>
      Promise.resolve({
        data: {
          entity_id: path.entity_id,
          name: 'Irena',
          aliases: [],
          entity_link_stats: { faces: { total: 7 } },
        },
      }),
    )
    api.faces.mockImplementation(({ query }) =>
      Promise.resolve({
        data: {
          items: [],
          total_count: [query['filter.last_touched_by_api_key_id']].flat().includes(two) ? 0 : 2,
          limit: 100,
          cursor: query.return_total_count && !query.cursor ? 'next' : null,
        },
      }),
    )
    api.mentions.mockResolvedValue({
      data: { items: [], total_count: 0, limit: 100, cursor: null },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/people/:personId', name: 'person-detail', component: Harness }],
    })
    await router.push(
      `/people/${one}?link_state=manual&link_state=verified&api_key=${one}&document=${two}&touched_by=${one}&q=Irena`,
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mount(Harness, {
      global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
    })
    await flushPromises()
    const evidenceRequests = () =>
      api.faces.mock.calls.map(([request]) => request.query).filter((q) => q.return_total_count)
    expect(evidenceRequests().slice(-1)[0]).toMatchObject({
      'filter.entity_id': [one],
      'filter.entity_link_state': ['manual', 'verified'],
      // The profile's faces apply the shared criteria to each face itself.
      'filter.last_touched_by_api_key_id': [one],
      'filter.document_source_id': [two],
      'filter.last_touched_by_user_id': [one],
      cursor: null,
      return_total_count: true,
    })
    expect(Object.keys(evidenceRequests().slice(-1)[0]!).some((key) => key.includes('evidence'))).toBe(false)
    expect(evidenceRequests().slice(-1)[0]).not.toHaveProperty('query.text')
    expect(wrapper.text()).toContain('2 matching of 7 faces')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(evidenceRequests().slice(-1)[0]?.cursor).toBe('next')
    const original = router.currentRoute.value.fullPath
    await router.push({ query: { ...router.currentRoute.value.query, api_key: two } })
    await flushPromises()
    expect(evidenceRequests().slice(-1)[0]?.cursor).toBeNull()
    expect(wrapper.text()).toContain('0 matching of 7 faces')
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(original)
    expect(evidenceRequests().slice(-1)[0]?.cursor).toBeNull()
    expect(wrapper.text()).toContain('2 matching of 7 faces')
    router.forward()
    await flushPromises()
    expect(wrapper.text()).toContain('0 matching of 7 faces')
    const destination = relatedQuery(router.currentRoute.value)
    expect(destination.api_key).toEqual([two])
    expect(destination).not.toHaveProperty('q')
    await router.push({ name: 'person-detail', params: { personId: two }, query: destination })
    await flushPromises()
    expect(evidenceRequests().slice(-1)[0]?.['filter.entity_id']).toEqual([two])
    wrapper.unmount()
    client.clear()
  })
})
