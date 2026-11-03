import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import PeopleSearchView from '@/views/PeopleSearchView.vue'

const state = vi.hoisted(() => ({ merge: vi.fn(), clear: vi.fn(), toggle: vi.fn(), add: vi.fn() }))
const allowed = ref(true),
  busy = ref(false),
  message = ref('')
const selectedIds = ref(new Set(['c', 'a']))
const selected = ref([
  { id: 'c', name: 'Cia' },
  { id: 'a', name: 'Ada' },
])
vi.mock('@/viewmodels/people-merge', () => ({
  usePeopleMerge: () => ({
    ...state,
    allowed,
    busy,
    message,
    selected,
    selectedIds,
  }),
}))
vi.mock('@/viewmodels/people-counts', async (original) => ({
  ...(await original<typeof import('@/viewmodels/people-counts')>()),
  usePeopleCounts: () => ({ params: ref({}), error: ref(null) }),
}))
vi.mock('@/viewmodels/shared-filters', () => ({
  useSharedFilters: () => ({ params: ref({}), error: ref(null) }),
  relatedQuery: () => ({}),
}))
vi.mock('@/viewmodels/people-search', () => ({
  usePeopleSearch: () => ({
    people: ref([
      { id: 'a', name: 'Ada' },
      { id: 'b', name: 'Bea' },
      { id: 'c', name: 'Cia' },
    ]),
    error: ref(null),
    isFetching: ref(false),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    resultCount: ref(1),
    loadMore: vi.fn(),
  }),
}))
vi.mock('@/composables/automatic-pagination', () => ({ useAutomaticPagination: vi.fn() }))
async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PeopleSearchView }],
  })
  await router.push('/')
  return mount(PeopleSearchView, {
    global: {
      plugins: [router],
      stubs: {
        RouterLink: true,
        PeopleSearchBar: true,
        PeopleCard: true,
        PeopleCardSkeleton: true,
      },
    },
  })
}
beforeEach(() => {
  vi.clearAllMocks()
  allowed.value = true
  busy.value = false
  message.value = ''
  selectedIds.value = new Set(['c', 'a'])
  selected.value = [
    { id: 'c', name: 'Cia' },
    { id: 'a', name: 'Ada' },
  ]
})
it('shows exactly the two named merge actions then Clear and submits without a dialog', async () => {
  const wrapper = await setup()
  const buttons = wrapper.get('[role="toolbar"]').findAll('button')
  expect(buttons.map((b) => b.text())).toEqual([
    'Last selected (Ada)',
    'First selected (Cia)',
    'Clear',
  ])
  expect(buttons[0]!.find('svg').exists()).toBe(true)
  expect(buttons[1]!.find('svg').exists()).toBe(true)
  await buttons[0]!.trigger('click')
  expect(state.merge).toHaveBeenLastCalledWith('last')
  await buttons[1]!.trigger('click')
  expect(state.merge).toHaveBeenLastCalledWith('first')
  await buttons[2]!.trigger('click')
  expect(state.clear).toHaveBeenCalledOnce()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.get('[aria-label="Remove Ada from merge"]').attributes('aria-pressed')).toBe(
    'true',
  )
  wrapper.unmount()
})
it('disables selection and actions during pending and exposes error recovery feedback', async () => {
  busy.value = true
  const wrapper = await setup()
  expect(wrapper.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  expect(wrapper.get('[role="toolbar"]').get('[role="status"]').text()).toBe('Merging…')
  busy.value = false
  message.value = 'Merge failed. Check your connection and try again.'
  await wrapper.vm.$nextTick()
  expect(wrapper.get('[role="toolbar"]').get('[role="alert"]').text()).toContain('try again')
  expect(wrapper.get('[role="toolbar"]').text()).toContain('2 people selected')
  wrapper.unmount()
})
it('hides merge selection and actions from non-admin users', async () => {
  allowed.value = false
  const wrapper = await setup()
  expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="Select Ada for merge"]').exists()).toBe(false)
  wrapper.unmount()
})

it('uses additive card clicks in selection mode and leaves removal to the corner control', async () => {
  const wrapper = await setup()
  expect(wrapper.find('[aria-label="Open Ada"]').exists()).toBe(false)
  await wrapper.get('[aria-label="Ada is selected"]').trigger('click')
  expect(state.add).toHaveBeenLastCalledWith('a', expect.objectContaining({ shiftKey: false }))
  expect(state.toggle).not.toHaveBeenCalled()
  await wrapper.get('[aria-label="Add Bea to selection"]').trigger('click', { shiftKey: true })
  expect(state.add).toHaveBeenLastCalledWith('b', expect.objectContaining({ shiftKey: true }))
  await wrapper.get('[aria-label="Remove Ada from merge"]').trigger('click')
  expect(state.toggle).toHaveBeenLastCalledWith('a', expect.anything())
  wrapper.unmount()
})

it('opens cards normally until the first person is selected', async () => {
  selectedIds.value = new Set()
  selected.value = []
  const wrapper = await setup()
  expect(wrapper.find('[aria-label="Open Ada"]').exists()).toBe(true)
  expect(wrapper.find('[aria-label="Add Ada to selection"]').exists()).toBe(false)
  const control = wrapper.get('[aria-label="Select Ada for merge"]')
  expect(control.attributes('aria-pressed')).toBe('false')
  await control.trigger('click')
  expect(state.toggle).toHaveBeenLastCalledWith('a', expect.anything())
  wrapper.unmount()
})
