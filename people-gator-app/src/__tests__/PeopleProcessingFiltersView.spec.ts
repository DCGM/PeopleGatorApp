import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { readSharedFilters, utcToLocalTime } from '@/viewmodels/shared-filters'

// Option IDs are UUIDs: copied non-UUID selections are shown as invalid instead.
const codes: Record<string, string> = {
  document: 'd',
  page: 'e',
  user: 'a',
  'api-key': 'b',
  library: 'c',
}
const id = (kind: string, n: number) => `00000000-0000-4000-8000-00000000${codes[kind]}00${n}`
const options = (kind: string) => [
  { id: id(kind, 1), label: `${kind} One` },
  { id: id(kind, 2), label: `${kind} Two` },
]
const labels = (kind: string) => Object.fromEntries(options(kind).map((o) => [o.id, o.label]))

const desktopViewport = ref(true)
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useMediaQuery: () => desktopViewport,
}))
beforeEach(() => {
  desktopViewport.value = true
})

vi.mock('@/query/people-filter-options', () => ({
  useActorLabels: (kind: string) => ({ labels: ref(labels(kind)) }),
  useSourceLabels: (kind: string) => ({ labels: ref(labels(kind)), missing: ref([]) }),
  usePeopleFilterOptions: (kind: string) => ({
    options: ref(options(kind)),
    labels: ref(labels(kind)),
    isLoading: ref(false),
    error: ref(null),
    hasMore: ref(false),
    isLoadingMore: ref(false),
    loadMore: vi.fn<() => void>(),
    retry: vi.fn<() => void>(),
  }),
}))
vi.mock('@/viewmodels/people-search', () => ({
  usePeopleSearch: () => ({
    error: ref(null),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn<() => void>(),
    people: ref([]),
    resultCount: ref(0),
  }),
}))
import PeopleSearchView from '@/views/PeopleSearchView.vue'
import FilterDateTimePicker from '@/components/custom/FilterDateTimePicker.vue'

const body = () => new DOMWrapper(document.body)
beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
    setTimeout(() => callback(0), 0),
  )
  HTMLElement.prototype.scrollIntoView = vi.fn<() => void>()
})
afterEach(() => {
  document.body.innerHTML = ''
})
afterAll(() => vi.unstubAllGlobals())

async function mountedView(query: Record<string, string | string[]> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'people-search', component: PeopleSearchView }],
  })
  await router.push({ name: 'people-search', query })
  await router.isReady()
  const wrapper = mount(PeopleSearchView, {
    attachTo: document.body,
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('people filter controls and URL restoration', () => {
  it('shows only search on mobile and preserves filters when opening, closing and resizing', async () => {
    desktopViewport.value = false
    const { wrapper, router } = await mountedView({
      q: 'Novak',
      assignment: 'faces',
      document: id('document', 1),
      touched_by: id('user', 1),
      api_key: id('api-key', 1),
    })
    const search = wrapper.get<HTMLInputElement>('input[aria-label="Search people"]')
    const originalQuery = { ...router.currentRoute.value.query }
    expect(search.element.value).toBe('Novak')
    expect(wrapper.find('button[aria-label="Documents"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Active filters"]').exists()).toBe(true)
    const toggle = wrapper.get('button[aria-label="Show filters"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.find('svg.lucide-sliders-horizontal').exists()).toBe(true)
    await toggle.trigger('click')
    await flushPromises()
    expect(wrapper.get('button[aria-label="Assignment"]').text()).toContain('Assigned faces')
    expect(wrapper.find('button[aria-label="Documents"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Modified by"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Modified via key"]').exists()).toBe(true)
    expect(wrapper.findAllComponents(FilterDateTimePicker)).toHaveLength(2)
    expect(wrapper.find('[aria-label="Active filters"]').exists()).toBe(true)
    expect(toggle.find('svg.lucide-sliders-horizontal').exists()).toBe(true)
    await toggle.trigger('click')
    await flushPromises()
    expect(wrapper.find('button[aria-label="Documents"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Active filters"]').exists()).toBe(true)
    expect(router.currentRoute.value.query).toEqual(originalQuery)
    await search.setValue('Ada')
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('Ada')
    expect(router.currentRoute.value.query.assignment).toBe(originalQuery.assignment)
    expect(readSharedFilters(router.currentRoute.value.query)).toEqual(
      readSharedFilters(originalQuery),
    )
    desktopViewport.value = true
    await flushPromises()
    expect(wrapper.find('button[aria-label="Documents"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Active filters"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Modified by"]').exists()).toBe(true)
    desktopViewport.value = false
    await flushPromises()
    expect(wrapper.find('button[aria-label="Documents"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('restores every filter, supports individual removal and clearing all filters', async () => {
    const { wrapper, router } = await mountedView({
      q: 'Ada',
      assignment: 'mentions',
      link_state: ['verified'],
      touched_from: '2026-01-02T12:00:00Z',
      document: [id('document', 1), id('document', 2)],
      touched_by: id('user', 1),
      api_key: id('api-key', 1),
    })
    expect(wrapper.findAllComponents(FilterDateTimePicker)).toHaveLength(2)
    expect(wrapper.text()).toContain('Document: document One')
    expect(wrapper.text()).toContain('Modified by: user One')
    expect(wrapper.text()).toContain('Modified via key: api-key One')
    const remove = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label') === 'Remove Document: document One')!
    await remove.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.document).toEqual([id('document', 2)])
    expect(router.currentRoute.value.query.touched_by).toEqual([id('user', 1)])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada' })
    wrapper.unmount()
  })

  it('preserves page scope when changing search and assignment', async () => {
    const { wrapper, router } = await mountedView({ page: id('page', 1) })
    await wrapper.get('input[aria-label="Search people"]').setValue('Ada')
    await flushPromises()
    expect(router.currentRoute.value.query.page).toBe(id('page', 1))
    wrapper.findComponent({ name: 'PeopleSearchBar' }).vm.$emit('update:assignment', 'mentions')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({
      page: id('page', 1),
      assignment: 'mentions',
      q: 'Ada',
    })
    wrapper.unmount()
  })

  it('selects multiple options and restores state on browser navigation', async () => {
    const { wrapper, router } = await mountedView()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Documents')!
      .trigger('click')
    await flushPromises()
    const choices = body().findAll('[role="option"]')
    await choices[0]!.trigger('click')
    await choices[1]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.document).toEqual([id('document', 1), id('document', 2)])
    await router.push({
      name: 'people-search',
      query: { touched_by: id('user', 2), touched_to: '2026-01-02T12:00:00Z' },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Modified by: user Two')
    expect(wrapper.findAllComponents(FilterDateTimePicker)[1]!.get('button').text()).not.toContain(
      'Pick date and time',
    )
    expect(
      body()
        .findAll('[role="option"]')
        .every((option) => option.attributes('aria-selected') === 'false'),
    ).toBe(true)
    router.back()
    await flushPromises()
    expect(wrapper.text()).toContain('Document: document One')
    wrapper.unmount()
  })
  it('persists calendar and time changes as UTC and shows invalid ranges', async () => {
    const { wrapper, router } = await mountedView({
      touched_from: '2026-01-02T12:00:00.123Z',
      touched_to: '2026-01-04T12:00:00Z',
    })
    const pickers = wrapper.findAllComponents(FilterDateTimePicker)
    await pickers[0]!.get('button').trigger('click')
    await flushPromises()
    expect(body().find('[data-value="2026-01-03"]').exists()).toBe(true)
    await body().get('[data-value="2026-01-03"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_from).toBe(
      new Date(
        `2026-01-03T${utcToLocalTime('2026-01-02T12:00:00.123Z').split('T')[1]}`,
      ).toISOString(),
    )
    await body().get<HTMLInputElement>('input[type="time"]').setValue('13:45:12.345')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_from).toBe(
      new Date('2026-01-03T13:45:12.345').toISOString(),
    )
    await body()
      .findAll('button')
      .find((button) => button.text() === 'Done')!
      .trigger('click')
    await pickers[1]!.get('button').trigger('click')
    await flushPromises()
    await body().get('[data-value="2026-01-01"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('before or equal')
    await body()
      .findAll('button')
      .find((button) => button.text() === 'Clear')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_to).toBeUndefined()
    expect(router.currentRoute.value.query.touched_from).toBeDefined()
    wrapper.unmount()
  })
  it('keeps server search results selectable by keyboard and supports removing selections', async () => {
    const { wrapper, router } = await mountedView()
    const trigger = wrapper.get('button[aria-label="Modified by"]')
    await trigger.trigger('click')
    await flushPromises()
    const search = body().get<HTMLInputElement>('input[role="combobox"]')
    await search.setValue('server-side query')
    await flushPromises()
    expect(body().findAll('[role="option"]')).toHaveLength(2)
    await search.trigger('keydown', { key: 'ArrowDown' })
    await search.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(router.currentRoute.value.query.touched_by).toHaveLength(1)
    const selected = body().get('[role="option"][aria-selected="true"]')
    await selected.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_by).toBeUndefined()
    await search.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })
  it('keeps all desktop controls and badges visible with no collapse action', async () => {
    const { wrapper, router } = await mountedView({
      assignment: 'faces',
      touched_by: id('user', 1),
      api_key: id('api-key', 1),
    })
    const controls = wrapper.get('[aria-label="Search people filter controls"]')
    expect(controls.get('button[aria-label="Assignment"]').text()).toContain('Assigned faces')
    for (const label of ['Libraries', 'Documents', 'Pages', 'Modified by', 'Modified via key'])
      expect(controls.find(`button[aria-label="${label}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-slot="collapsible-trigger"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="Active filters"]').text()).toContain('Assigned faces')
    await wrapper.get('button[aria-label="Remove Modified by: user One"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.touched_by).toBeUndefined()
    expect(router.currentRoute.value.query.assignment).toBe('faces')
    wrapper.unmount()
  })

  it('expands invalid restored time filters so they can be corrected', async () => {
    const { wrapper } = await mountedView({
      touched_from: '2026-01-03T12:00:00Z',
      touched_to: '2026-01-01T12:00:00Z',
    })
    expect(wrapper.findAllComponents(FilterDateTimePicker)).toHaveLength(2)
    expect(wrapper.get('[role="alert"]').text()).toContain('before or equal')
    wrapper.unmount()
  })
  it('has one clear-all action for shared and People-only filters and preserves search, sort and witnesses', async () => {
    const { wrapper, router } = await mountedView({
      q: 'Irena',
      sort: 'name',
      touched_from: '2026-01-01T00:00:00Z',
      link_state: 'verified',
      assignment: 'faces',
      api_key: id('api-key', 1),
      page: id('page', 1),
      origin_matched_face: id('page', 2),
    })
    expect(wrapper.text()).toContain('Page: page One')
    expect(
      wrapper.findAll('button').filter((button) => button.text() === 'Clear all filters'),
    ).toHaveLength(1)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      q: 'Irena',
      sort: 'name',
      origin_matched_face: id('page', 2),
    })
    expect(
      wrapper.findAll('button').filter((button) => button.text() === 'Clear all filters'),
    ).toHaveLength(0)
    expect(wrapper.text()).not.toContain('Origin ·')
    expect(wrapper.text()).not.toContain('Return to originating view')
    wrapper.unmount()
  })
})
