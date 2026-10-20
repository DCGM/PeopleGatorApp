import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { activityGroups, localDayBounds } from '@/viewmodels/page-activity'
const user = '00000000-0000-4000-8000-000000000001'
const records = [
  {
    id: 'face-a',
    kind: 'face' as const,
    label: 'First face',
    touchedAt: '2026-01-01T12:00:00Z',
    userId: user,
  },
  {
    id: 'mention-a',
    kind: 'mention' as const,
    label: 'Irena',
    touchedAt: '2026-01-01T13:00:00Z',
    userId: user,
  },
  { id: 'face-b', kind: 'face' as const, label: 'Historical face', touchedAt: null, userId: null },
]
vi.mock('@/viewmodels/page-activity', async (original) => ({
  ...(await original<typeof import('@/viewmodels/page-activity')>()),
  usePageActivity: () => ({
    items: ref(records),
    loading: ref(false),
    error: ref(null),
    retry: vi.fn<() => void>(),
  }),
}))
vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: computed(() => ({ [user]: 'Preview reviewer' })) }),
}))
import PageActivityPanel from '@/components/custom/PageActivityPanel.vue'
describe('page annotation activity', () => {
  it('groups both annotation kinds, leaves unknown history explicit and computes local inclusive day bounds', () => {
    const groups = activityGroups(records, 'user')
    expect(groups[0]).toMatchObject({ key: user, faces: 1, mentions: 1 })
    expect(groups[1]).toMatchObject({ key: '', faces: 1, mentions: 0 })
    const bounds = localDayBounds('2026-03-29')
    expect(bounds.touchedFrom).toMatch(/^2026-03-29T00:00:00/)
    expect(bounds.touchedTo).toMatch(/^2026-03-29T23:59:59.999999$/)
  })
  it('filters the scan by day and user without losing other criteria or the return journey', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: PageActivityPanel }],
    })
    await router.push({
      path: '/',
      query: {
        panel: 'activity',
        origin_text: 'Irena',
        origin_return: '/people?q=Irena',
        link_state: 'verified',
      },
    })
    const wrapper = mount(PageActivityPanel, {
      props: { sourceId: 'page' },
      global: { plugins: [router] },
    })
    const day = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label')?.startsWith('Filter day '))!
    await day.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.evidence_from).toBeDefined()
    expect(router.currentRoute.value.query.evidence_to).toBeDefined()
    await router.push({ query: { ...router.currentRoute.value.query, activity_group: 'user' } })
    await flushPromises()
    await wrapper.get('button[aria-label="Filter user Preview reviewer"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.evidence_user).toEqual([user])
    expect(router.currentRoute.value.query.link_state).toEqual(['verified'])
    expect(wrapper.text()).toContain('User not recorded')
    expect(wrapper.text()).toContain('Historical face')
    expect(
      wrapper.findAll('button').filter((button) => button.text() === 'Clear activity filters'),
    ).toHaveLength(1)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear activity filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.evidence_user).toBeUndefined()
    expect(router.currentRoute.value.query.evidence_from).toBeUndefined()
    expect(router.currentRoute.value.query.origin_return).toBe('/people?q=Irena')
    wrapper.unmount()
  })
})
