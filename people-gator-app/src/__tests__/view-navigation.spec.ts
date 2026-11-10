import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter, useRoute } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import TopBar from '@/components/custom/TopBar.vue'
import { sharedFiltersQuery, useSharedFilters } from '@/viewmodels/shared-filters'

vi.mock('@/query/media', () => ({
  useDocumentLookupQuery: () => ({ data: ref(undefined) }),
  usePageLookupQuery: () => ({ data: ref(undefined) }),
}))
vi.mock('@/query/entities', () => ({
  useEntityQuery: () => ({ data: ref(undefined) }),
}))

const query = {
  library: 'preview-mzk',
  document: '00000000-0000-4000-8000-000000000001',
  page: '00000000-0000-4000-8000-000000000002',
  link_state: ['manual', 'verified'],
  touched_by: '00000000-0000-4000-8000-000000000003',
  api_key: 'bad-id',
  touched_from: '2026-01-01T00:00:00Z',
  touched_to: 'invalid-date',
  q: 'Ada',
  cursor: 'old',
  assignment: 'mentions',
  sort: 'name',
  annotations_min: '2',
}
const listings = [
  ['Documents', 'document-list', '/documents'],
  ['People', 'people-search', '/people'],
] as const
const Harness = defineComponent({
  setup() {
    const filters = useSharedFilters()
    const route = useRoute()
    const effective = computed(() => sharedFiltersQuery(filters.filters.value))
    return () =>
      h('div', [
        h(TopBar),
        h(
          'output',
          JSON.stringify({
            effective: effective.value,
            error: filters.error.value,
            query: route.query,
          }),
        ),
      ])
  },
})
async function setup(name: string, params = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...listings.map(([, name, path]) => ({ path, name, component: Harness })),
      {
        path: '/libraries/:libraryId/documents/:documentId',
        name: 'document-pages',
        component: Harness,
      },
      { path: '/people/:personId', name: 'person-detail', component: Harness },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: Harness,
      },
    ],
  })
  await router.push({ name, params, query })
  const wrapper = mount(Harness, { global: { plugins: [router] } })
  return { router, wrapper }
}

describe('fresh application navigation (#109)', () => {
  for (const [, source] of listings) {
    it.each(listings)('opens default %s from filtered ' + source, async (label, destination) => {
      const { router, wrapper } = await setup(source)
      expect(wrapper.get('output').text()).toContain('invalid filter')
      const original = router.currentRoute.value.fullPath
      await wrapper.get(`a[aria-label="${label}"]`).trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe(destination)
      expect(router.currentRoute.value.query).toEqual({})
      expect(wrapper.get('output').text()).toBe('{"effective":{},"query":{}}')
      // Actual browser history restores the explicit filtered URL, not a saved store.
      router.back()
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe(original)
      router.forward()
      await flushPromises()
      expect(router.currentRoute.value.query).toEqual({})
      // Normal leave-and-return navigation stays default.
      for (const [label, name] of listings) {
        await wrapper.get(`a[aria-label="${label}"]`).trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.name).toBe(name)
        expect(router.currentRoute.value.query).toEqual({})
      }
      wrapper.unmount()
    })
  }
  it.each(['document-list', 'people-search'])(
    'logo opens default Documents from %s',
    async (source) => {
      const { router, wrapper } = await setup(source)
      await wrapper.get('a[aria-label="PeopleGator"]').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/documents')
      wrapper.unmount()
    },
  )
  it('People breadcrumb resets filters; source breadcrumbs retain only explicit context', async () => {
    const { router, wrapper } = await setup('person-detail', { personId: 'ada' })
    await wrapper.get('[aria-label="Breadcrumb"] a[title="People"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/people')
    await router.push({
      name: 'document-page',
      params: { libraryId: 'preview-mzk', documentId: 'archive', pageId: 'page' },
      query,
    })
    await flushPromises()
    const link = wrapper.get('[aria-label="Breadcrumb"] a[title="archive"]')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-pages')
    expect(router.currentRoute.value.params).toEqual({
      libraryId: 'preview-mzk',
      documentId: 'archive',
    })
    expect(router.currentRoute.value.query).toEqual({ pages_view: 'expanded' })
    wrapper.unmount()
  })
})
