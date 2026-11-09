import { mount, flushPromises } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { Combobox } from '@/components/ui/combobox'
import DocumentPageGalleryFilters from '@/components/custom/DocumentPageGalleryFilters.vue'
import { GALLERY_DEFAULT, GALLERY_SORTS } from '@/viewmodels/sort-options'

const state = vi.hoisted(() => ({ missing: false }))
vi.mock('@/query/entities', () => ({
  useEntityQuery: () => ({
    data: computed(() => (state.missing ? undefined : { name: 'Nora Page' })),
    isError: computed(() => state.missing),
  }),
}))
vi.mock('@/query/search/entities', () => ({
  useEntityResultsQuery: () => ({
    data: ref({ pages: [{ items: [{ entity_id: 'nora', name: 'Nora Page' }] }] }),
    isPending: ref(false),
    isError: ref(false),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
  }),
}))
const media = (desktop: boolean) =>
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: desktop,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
beforeEach(() => {
  state.missing = false
  media(true)
})
afterEach(() => vi.unstubAllGlobals())
const mountFilters = (personId = '') =>
  mount(DocumentPageGalleryFilters, {
    props: { personId, sort: GALLERY_DEFAULT, sortOptions: GALLERY_SORTS },
  })

describe('page strip person filter', () => {
  it('selects one person and exposes an individually removable tag', async () => {
    const wrapper = mountFilters()
    wrapper.getComponent(Combobox).vm.$emit('update:modelValue', 'nora')
    expect(wrapper.emitted('update:personId')).toEqual([['nora']])
    await wrapper.setProps({ personId: 'nora' })
    expect(wrapper.get('[aria-label="Filter pages by person"]').text()).toContain('Nora Page')
    await wrapper.get('[aria-label="Remove Person: Nora Page"]').trigger('click')
    expect(wrapper.emitted('update:personId')?.[1]).toEqual([''])
    wrapper.unmount()
  })
  it('keeps unavailable person selections visible and clearable', async () => {
    state.missing = true
    const wrapper = mountFilters('deleted-person')
    expect(wrapper.text()).toContain('Unavailable person (deleted-person)')
    await wrapper
      .get('[aria-label="Remove Person: Unavailable person (deleted-person)"]')
      .trigger('click')
    expect(wrapper.emitted('update:personId')).toEqual([['']])
    wrapper.unmount()
  })
  it('collapses controls on mobile while keeping the active tag accessible', async () => {
    media(false)
    const wrapper = mountFilters('nora')
    const toggle = wrapper.get('[aria-label="Show filters"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[aria-label="Filter pages by person"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Remove Person: Nora Page"]').exists()).toBe(true)
    await toggle.trigger('click')
    await flushPromises()
    expect(wrapper.get('[aria-label="Hide filters"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[aria-label="Filter pages by person"]').text()).toContain('Nora Page')
    expect(wrapper.emitted('update:personId')).toBeUndefined()
    wrapper.unmount()
  })
})
