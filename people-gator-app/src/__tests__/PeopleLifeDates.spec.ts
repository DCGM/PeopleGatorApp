import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { toValue, type MaybeRefOrGetter } from 'vue'

// People birth/death date ranges, sorts and life spans (#123).
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
const searchArgs: { filters?: MaybeRefOrGetter<object>; enabled?: MaybeRefOrGetter<boolean> } = {}
const people = ref<object[]>([])
vi.mock('@/viewmodels/people-search', () => ({
  usePeopleSearch: (
    _search: unknown,
    _assignment: unknown,
    _size: unknown,
    filters: MaybeRefOrGetter<object>,
    enabled: MaybeRefOrGetter<boolean>,
  ) => {
    Object.assign(searchArgs, { filters, enabled })
    return {
      error: ref(null),
      hasNextPage: ref(false),
      isFetchingNextPage: ref(false),
      isFetching: ref(false),
      isLoading: ref(false),
      loadMore: vi.fn<() => void>(),
      people,
      resultCount: ref(people.value.length),
    }
  },
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
    routes: [
      { path: '/', name: 'people-search', component: PeopleSearchView },
      { path: '/people/:personId', name: 'person-detail', component: PeopleSearchView },
    ],
  })
  await router.push({ name: 'people-search', query })
  await router.isReady()
  const wrapper = mount(PeopleSearchView, {
    attachTo: document.body,
    global: { plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  await flushPromises()
  return { wrapper, router }
}

const tag = (wrapper: Awaited<ReturnType<typeof mountedView>>['wrapper'], label: string) =>
  wrapper.findAll('small').find((item) => item.text().startsWith(label))
const lifeDatePickers = (wrapper: Awaited<ReturnType<typeof mountedView>>['wrapper']) =>
  wrapper
    .findAllComponents(FilterDateTimePicker)
    .filter((picker) => /^(Born|Died) /.test(picker.props('label')))

describe('people life-date filters', () => {
  beforeEach(() => {
    people.value = []
  })

  it('restores ranges from the URL as API dates and tags', async () => {
    const { wrapper } = await mountedView({ born_from: '1870-01-01', died_to: '1949-12-31' })
    expect(lifeDatePickers(wrapper).map((picker) => picker.props('label'))).toEqual([
      'Born from',
      'Born to',
      'Died from',
      'Died to',
    ])
    expect(toValue(searchArgs.filters)).toMatchObject({
      'filter.birth_date_from': '1870-01-01',
      'filter.death_date_to': '1949-12-31',
    })
    expect(toValue(searchArgs.filters)).not.toHaveProperty('filter.birth_date_to')
    expect(toValue(searchArgs.enabled)).toBe(true)
    expect(tag(wrapper, 'Born from:')?.text()).toContain('1870')
    expect(tag(wrapper, 'Died to:')?.text()).toContain('1949')
    expect(lifeDatePickers(wrapper)[0]!.get('button').text()).toContain('1870')
    expect(lifeDatePickers(wrapper)[1]!.get('button').text()).toContain('Born to: Any')
    wrapper.unmount()
  })

  it('picks a calendar date without a time and removes one tag at a time', async () => {
    const { wrapper, router } = await mountedView({ q: 'Ada', born_from: '1890-03-14' })
    await lifeDatePickers(wrapper)[0]!.get('button').trigger('click')
    await flushPromises()
    expect(body().find('input[type="time"]').exists()).toBe(false)
    await body().get('[data-value="1890-03-20"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.born_from).toBe('1890-03-20')

    await router.push({ query: { ...router.currentRoute.value.query, died_from: '1950-01-01' } })
    await flushPromises()
    await tag(wrapper, 'Born from:')!.get('button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada', died_from: '1950-01-01' })
    expect(tag(wrapper, 'Born from:')).toBeUndefined()
    wrapper.unmount()
  })

  it('clears every range with all filters while keeping search and sort', async () => {
    const { wrapper, router } = await mountedView({
      q: 'Ada',
      sort: 'birth_date',
      born_from: '1870-01-01',
      born_to: '1910-12-31',
      died_to: '1949-12-31',
    })
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada', sort: 'birth_date' })
    wrapper.unmount()
  })

  it('blocks searching with an inverted or malformed range until it is fixed', async () => {
    const { wrapper, router } = await mountedView({
      born_from: '1910-01-01',
      born_to: '1900-01-01',
    })
    expect(wrapper.get('[role="alert"]').text()).toBe(
      'Born: the start date must not be after the end date.',
    )
    expect(toValue(searchArgs.enabled)).toBe(false)
    expect(lifeDatePickers(wrapper)[0]!.get('button').attributes('aria-invalid')).toBe('true')
    await router.push({ query: { died_from: '1950-02-30' } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Enter dates as YYYY-MM-DD.')
    expect(tag(wrapper, 'Died from:')?.text()).toContain('1950-02-30 (invalid)')
    expect(toValue(searchArgs.filters)).not.toHaveProperty('filter.death_date_from')
    await router.push({ query: {} })
    await flushPromises()
    expect(toValue(searchArgs.enabled)).toBe(true)
    wrapper.unmount()
  })

  it('offers surname, birth and death sorts and shows life spans on cards', async () => {
    people.value = [
      { id: '1', name: 'Karel Vrba', lifeSpan: '1890–1962', faces: 0, names: 0, countDetails: [] },
      {
        id: '2',
        name: 'Alena Bartošová',
        lifeSpan: 'b. 1948',
        faces: 0,
        names: 0,
        countDetails: [],
      },
      { id: '3', name: 'Lenka Vesela', lifeSpan: '', faces: 0, names: 0, countDetails: [] },
    ]
    const { wrapper } = await mountedView({ sort: 'surname' })
    const sortControl = wrapper.findAllComponents({ name: 'SortControl' })[0]!
    const options = sortControl.props('options') as { value: string }[]
    expect(options.map((option) => option.value)).toEqual(
      expect.arrayContaining(['name', 'surname', 'birth_date', 'death_date']),
    )
    expect(sortControl.props('modelValue')).toEqual({
      field: 'surname',
      direction: 'asc',
    })
    const cards = wrapper.findAllComponents({ name: 'PeopleCard' })
    expect(cards.map((card) => card.find('p small').text())).toEqual([
      '1890–1962',
      'b. 1948',
      expect.stringContaining('faces'),
    ])
    wrapper.unmount()
  })
})
