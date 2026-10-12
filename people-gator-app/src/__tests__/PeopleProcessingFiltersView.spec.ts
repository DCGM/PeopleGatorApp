import { flushPromises, mount } from '@vue/test-utils'
import { computed, ref, type Ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { processingFilterError, type PeopleProcessingFilters } from '@/viewmodels/people-filters'

vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: (kind: string) => ({
    options: ref([
      { id: `${kind}-1`, label: `${kind} One` },
      { id: `${kind}-2`, label: `${kind} Two` },
    ]),
    labels: ref({ [`${kind}-1`]: `${kind} One`, [`${kind}-2`]: `${kind} Two` }),
    isLoading: ref(false),
    error: ref(null),
    hasMore: ref(false),
    isLoadingMore: ref(false),
    loadMore: vi.fn(),
    retry: vi.fn(),
  }),
}))
vi.mock('@/viewmodels/people-search', () => ({
  usePeopleSearch: (
    _term: unknown,
    _assignment: unknown,
    _pageSize: unknown,
    filters: Ref<PeopleProcessingFilters>,
  ) => ({
    error: ref(null),
    filterError: computed(() => processingFilterError(filters.value)),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn(),
    people: ref([]),
    resultCount: ref(0),
  }),
}))
import PeopleSearchView from '@/views/PeopleSearchView.vue'

async function mountedView(query: Record<string, string | string[]> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'people-search', component: PeopleSearchView }],
  })
  await router.push({ name: 'people-search', query })
  await router.isReady()
  const wrapper = mount(PeopleSearchView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('people filter controls and URL restoration', () => {
  it('restores every filter, supports individual removal and clearing all filters', async () => {
    const { wrapper, router } = await mountedView({
      q: 'Ada',
      assignment: 'mentions',
      touched_from: '2026-01-02T12:00:00Z',
      document: ['document-1', 'document-2'],
      touched_by: 'user-1',
      api_key: 'api-key-1',
    })
    expect(wrapper.find<HTMLInputElement>('input[type="datetime-local"]').element.value).not.toBe(
      '',
    )
    expect(wrapper.text()).toContain('Document: document One')
    expect(wrapper.text()).toContain('User: user One')
    expect(wrapper.text()).toContain('API key: api-key One')
    const remove = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label') === 'Remove Document: document One')!
    await remove.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.document).toEqual(['document-2'])
    expect(router.currentRoute.value.query.touched_by).toEqual(['user-1'])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada' })
    wrapper.unmount()
  })

  it('selects multiple options and restores state on browser navigation', async () => {
    const { wrapper, router } = await mountedView()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Documents')!
      .trigger('click')
    const choices = wrapper.findAll('input[type="checkbox"]')
    await choices[0]!.setValue(true)
    await choices[1]!.setValue(true)
    await flushPromises()
    expect(router.currentRoute.value.query.document).toEqual(['document-1', 'document-2'])
    await router.push({
      name: 'people-search',
      query: { touched_by: 'user-2', touched_to: '2026-01-02T12:00:00Z' },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('User: user Two')
    expect(
      wrapper.findAll<HTMLInputElement>('input[type="datetime-local"]')[1]!.element.value,
    ).not.toBe('')
    expect(
      wrapper
        .findAll('input[type="checkbox"]')
        .every((input) => !(input.element as HTMLInputElement).checked),
    ).toBe(true)
    router.back()
    await flushPromises()
    expect(wrapper.text()).toContain('Document: document One')
    wrapper.unmount()
  })
  it('persists local date/time changes as UTC and shows invalid ranges', async () => {
    const { wrapper, router } = await mountedView()
    const times = wrapper.findAll<HTMLInputElement>('input[type="datetime-local"]')
    await times[0]!.setValue('2026-01-02T13:45')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_from).toBe(
      new Date('2026-01-02T13:45').toISOString(),
    )
    await times[1]!.setValue('2026-01-01T13:45')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('before or equal')
    wrapper.unmount()
  })
})
