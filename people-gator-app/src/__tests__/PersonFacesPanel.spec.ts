import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PersonFacesPanel from '@/components/custom/PersonFacesPanel.vue'
import type { PersonFace } from '@/viewmodels/person-detail.types'
const api = vi.hoisted(() => ({
  patch: vi.fn(),
  portrait: vi.fn(),
  scopes: ['people-gator:annotate'],
}))
vi.mock('@/client', () => ({
  patchFaceBatchRouteApiV1FacesBatchPatch: api.patch,
  patchEntityRouteApiV1EntitiesEntityIdPatch: api.portrait,
}))
vi.mock('@/query/client', () => ({
  getAccessToken: async () => `header.${btoa(JSON.stringify({ scopes: api.scopes }))}.sig`,
}))
vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: computed(() => ({})) }),
}))
const faces: PersonFace[] = ['automatic', 'manual', 'verified', 'automatic'].map(
  (linkState, index) => ({
    id: `f${index}`,
    linkState,
    portrait: '',
    portraitLoading: false,
    confidence: 99,
    library: 'library',
    documentId: 'document',
    pageId: 'page',
    pageLabel: '1',
    position: { x: 0, y: 0, width: 1, height: 1 },
  }),
) as PersonFace[]
const cleanup: (() => void)[] = []
afterEach(() => cleanup.splice(0).forEach((fn) => fn()))
beforeEach(() => {
  vi.clearAllMocks()
  api.scopes = ['people-gator:annotate']
  api.patch.mockResolvedValue({ data: [] })
  api.portrait.mockResolvedValue({
    data: { entity_id: 'person', thumbnail_face_id: 'f0', thumbnail_mode: 'manual' },
  })
})
async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/people/:personId', name: 'person-detail', component: { template: '<div />' } },
      { path: '/people', name: 'people-search', component: { template: '<div />' } },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/people/person')
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const wrapper = mount(PersonFacesPanel, {
    props: { faces, personName: 'Irena', personId: 'person' },
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  })
  cleanup.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  await flushPromises()
  return { wrapper, router, queryClient }
}
describe('assigned face selection and review', () => {
  it('supports checkbox, click-to-add and Shift ranges, verifies only unverified links and refreshes dependent views', async () => {
    const { wrapper, queryClient } = await render()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    expect(wrapper.findAll('[data-person-face-card] a.group')).toHaveLength(4)
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    expect(wrapper.find('[data-person-face-card] a.group').exists()).toBe(false)
    await wrapper.get('[aria-label="Add face f1 to selection"]').trigger('click')
    await wrapper
      .get('[aria-label="Select face f2 for review"]')
      .trigger('click', { shiftKey: true })
    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
    await wrapper.get('[aria-label="Face f1 is selected"]').trigger('click')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Verify selected (2)')!
      .trigger('click')
    await flushPromises()
    expect(api.patch.mock.calls[0]![0].body).toEqual([
      { detection_id: 'f0', entity_link_state: 'verified' },
      { detection_id: 'f1', entity_link_state: 'verified' },
    ])
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe('2 faces verified.')
    expect(
      invalidate.mock.calls.map(
        ([args]) => (typeof args === 'function' ? args() : args)?.queryKey?.[0],
      ),
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
  it('unassigns without deletion, retains selection on failure and blocks concurrent updates', async () => {
    const { wrapper } = await render()
    await wrapper.get('[aria-label="Select face f2 for review"]').trigger('click')
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Verify selected (0)')!
        .attributes('disabled'),
    ).toBeDefined()
    let reject!: (error: Error) => void
    api.patch.mockImplementationOnce(
      () =>
        new Promise((_resolve, failure) => {
          reject = failure
        }),
    )
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Unassign selected')!
      .trigger('click')
    await flushPromises()
    expect(
      wrapper.get('[aria-label="Remove face f2 from review"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper
        .get('[role="toolbar"]')
        .findAll('button')
        .every((button) => button.attributes('disabled') !== undefined),
    ).toBe(true)
    reject(new Error('Try again'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('review the selection and try again')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Unassign selected')!
      .trigger('click')
    await flushPromises()
    expect(api.patch.mock.calls[1]![0].body).toEqual([
      { detection_id: 'f2', entity_id: null, entity_link_state: null },
    ])
    expect(wrapper.text()).toContain('1 face unassigned.')
  })
  it('prunes removed results, retains selection through pagination and clears on filter/navigation changes', async () => {
    const { wrapper, router } = await render()
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    await wrapper.setProps({ faces: faces.slice(0, 2) })
    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
    await wrapper.setProps({ faces })
    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
    await router.replace('/people/person?link_state=manual')
    await flushPromises()
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    await wrapper.setProps({ faces: faces.slice(1) })
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
  })
  it('leaves source inspection available for viewers without annotation permission', async () => {
    api.scopes = ['people-gator:browse']
    const { wrapper } = await render()
    expect(wrapper.find('[data-face-selection-target="control"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-person-face-card] a.group')).toHaveLength(4)
  })
  it('reports partially missing batch results and refreshes cached evidence', async () => {
    const { wrapper, queryClient } = await render()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    api.patch.mockResolvedValueOnce({ data: [null] })
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Verify selected (1)')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not update all')
    expect(invalidate).toHaveBeenCalled()
  })
  it('sets exactly one selected face as portrait and refreshes identity views', async () => {
    const { wrapper, queryClient } = await render()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    const portraitButton = () =>
      wrapper.findAll('button').find((button) => button.text() === 'Use as portrait')!
    expect(portraitButton().exists()).toBe(true)
    await wrapper.get('[aria-label="Add face f1 to selection"]').trigger('click')
    expect(portraitButton()).toBeUndefined()
    await wrapper.get('[aria-label="Remove face f1 from review"]').trigger('click')
    await portraitButton().trigger('click')
    await flushPromises()
    expect(api.portrait.mock.lastCall?.[0]).toMatchObject({
      path: { entity_id: 'person' },
      body: { thumbnail_face_id: 'f0' },
    })
    expect(api.patch).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toBe('Portrait saved.')
    expect(queryClient.getQueryData(['entities', 'detail', 'person'])).toMatchObject({
      thumbnail_face_id: 'f0',
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['entities', 'list'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['search'] })
    await wrapper.setProps({ thumbnailFaceId: 'f0', thumbnailMode: 'manual' })
    expect(wrapper.findAll('[data-person-portrait]')).toHaveLength(1)
    api.portrait.mockResolvedValueOnce({
      data: { entity_id: 'person', thumbnail_face_id: 'f0', thumbnail_mode: 'automatic' },
    })
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Use automatic')!
      .trigger('click')
    await flushPromises()
    expect(api.portrait.mock.lastCall?.[0].body).toEqual({ thumbnail_face_id: null })
    expect(wrapper.get('[role="status"]').text()).toBe('Automatic portrait.')
    expect(queryClient.getQueryData(['entities', 'detail', 'person'])).toMatchObject({
      thumbnail_mode: 'automatic',
    })
  })

  it('blocks competing actions during portrait saving and retains the selection on failure', async () => {
    const { wrapper } = await render()
    await wrapper.get('[aria-label="Select face f0 for review"]').trigger('click')
    let reject!: (error: Error) => void
    api.portrait.mockImplementationOnce(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail
        }),
    )
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Use as portrait')!
      .trigger('click')
    await flushPromises()
    expect(
      wrapper
        .get('[role="toolbar"]')
        .findAll('button')
        .every((button) => button.attributes('disabled') !== undefined),
    ).toBe(true)
    reject(new Error('Try again'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Try again')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Use as portrait')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Portrait saved.')
  })
})

it('collapses to two measured rows and exposes pagination only after expansion', async () => {
  const { wrapper } = await render()
  await wrapper.setProps({ collapsible: true, hasMore: true })
  // A zero-width jsdom grid has one column; browser coverage exercises real widths.
  expect(wrapper.findAll('[data-person-face-card]')).toHaveLength(2)
  const toggle = wrapper.findAll('button').find((button) => button.text() === 'Show all faces')!
  expect(toggle.attributes('aria-expanded')).toBe('false')
  await toggle.trigger('click')
  expect(wrapper.findAll('[data-person-face-card]')).toHaveLength(4)
  expect(toggle.attributes('aria-expanded')).toBe('true')
  await toggle.trigger('click')
  expect(wrapper.findAll('[data-person-face-card]')).toHaveLength(2)
})
