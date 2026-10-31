import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readPeopleCounts, usePeopleCounts, PEOPLE_COUNT_KEYS } from '@/viewmodels/people-counts'
import { restartPeoplePages } from '@/query/people-count-invalidation'
import { PEOPLE_SORTS } from '@/viewmodels/sort-options'
import { sortStrategies } from '@/lib/sorting'
import PeopleCountControl from '@/components/custom/PeopleCountControl.vue'

// Popover stays inline in jsdom; form/input/button behavior uses real components.
vi.mock('@/components/ui/popover', () => ({
  Popover: { template: '<div><slot /></div>' },
  PopoverTrigger: { template: '<div><slot /></div>' },
  PopoverContent: { template: '<div><slot /></div>' },
}))

describe('people count filters', () => {
  it('preserves zero and bounds, flags malformed/inverted URLs and leaves unknown keys alone', () => {
    const counts = readPeopleCounts({
      min_faces_total_count: '0',
      max_faces_total_count: '0',
      min_mentions_total_count: '3',
      q: 'Ada',
    })
    expect(counts.error).toBeUndefined()
    expect(counts.params).toEqual({
      'filter.min_faces_total_count': 0,
      'filter.max_faces_total_count': 0,
      'filter.min_mentions_total_count': 3,
    })
    expect(counts.tags.map((t) => t.label)).toEqual(['Faces ≥ 0', 'Faces ≤ 0', 'Text mentions ≥ 3'])
    for (const raw of ['', '-1', '1.0', 'true', '9007199254740992', ['1', '2']])
      expect(readPeopleCounts({ max_faces_total_count: raw }).error).toBeTruthy()
    expect(
      readPeopleCounts({ min_mentions_total_count: '5', max_mentions_total_count: '2' }).error,
    ).toContain('minimum')
  })

  it('has both numeric strategies and starts highest first', () => {
    for (const field of ['faces_total_count', 'mentions_total_count', 'annotations_total_count'])
      expect(
        sortStrategies(PEOPLE_SORTS)
          .filter((s) => s.field === field)
          .map((s) => s.direction),
      ).toEqual(['desc', 'asc'])
  })

  it('updates URL bounds together, removes individual bounds and restores history', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/people', component: { template: '<div />' } }],
    })
    await router.push('/people?q=Ada&sort=faces_total_count&dir=asc&cursor=old')
    let counts!: ReturnType<typeof usePeopleCounts>
    const wrapper = mount(
      defineComponent({
        setup() {
          counts = usePeopleCounts()
          return () => h('div')
        },
      }),
      { global: { plugins: [router] } },
    )
    counts.set('faces', '0', '0')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      q: 'Ada',
      sort: 'faces_total_count',
      dir: 'asc',
      min_faces_total_count: '0',
      max_faces_total_count: '0',
    })
    counts.remove(counts.tags.value[0]!)
    await flushPromises()
    expect(router.currentRoute.value.query.min_faces_total_count).toBeUndefined()
    expect(counts.params.value['filter.max_faces_total_count']).toBe(0)
    router.back()
    await flushPromises()
    expect(counts.params.value['filter.min_faces_total_count']).toBe(0)
    router.forward()
    await flushPromises()
    expect(counts.params.value['filter.min_faces_total_count']).toBeUndefined()
    wrapper.unmount()
  })

  it('submits exact zero, blocks inverted bounds, and leaves blank bounds unbounded', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/people', component: { template: '<div />' } }],
    })
    await router.push('/people?q=Ada&sort=name')
    const wrapper = mount(PeopleCountControl, {
      props: { category: 'faces', label: 'Faces' },
      global: { plugins: [router] },
    })
    await wrapper.get('[aria-label="Faces minimum"]').setValue('2')
    await wrapper.get('[aria-label="Faces maximum"]').setValue('0')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Minimum')
    expect(router.currentRoute.value.query.max_faces_total_count).toBeUndefined()
    await wrapper.get('[aria-label="Faces minimum"]').setValue('0')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.max_faces_total_count).toBe('0')
    await wrapper.get('[aria-label="Faces maximum"]').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.max_faces_total_count).toBeUndefined()
    wrapper.unmount()
  })

  it('discards browse and search continuation chains on edits without touching detail or navigation', () => {
    const client = new QueryClient()
    const keys = [
      ['entities', 'list', 'infinite', { sort: 'faces_total_count' }],
      ['search', 'entities', 'infinite', { 'query.text': ['Ada'] }],
    ]
    for (const key of keys)
      client.setQueryData(key, {
        pages: [{ items: [1] }, { items: [2] }],
        pageParams: [null, 'stale'],
      })
    client.setQueryData(['entities', 'detail', 'id'], { name: 'Ada' })
    restartPeoplePages(client)
    for (const key of keys)
      expect(client.getQueryData(key)).toEqual({ pages: [{ items: [1] }], pageParams: [null] })
    expect(client.getQueryData(['entities', 'detail', 'id'])).toEqual({ name: 'Ada' })
    expect(PEOPLE_COUNT_KEYS).toHaveLength(4)
  })
})
