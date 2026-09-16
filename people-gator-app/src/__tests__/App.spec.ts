import { describe, it, expect, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import TopBar from '../components/custom/TopBar.vue'
import router from '../router'

vi.mock('@panzoom/panzoom', () => ({
  default: vi.fn(() => ({
    destroy: vi.fn(),
    reset: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    zoomWithWheel: vi.fn(),
  })),
}))

describe('App', () => {
  it('keeps the logo when the optional top bar title is omitted', () => {
    const wrapper = mount(TopBar, { global: { plugins: [router] } })

    expect(wrapper.get('nav').text()).toContain('PG')
    expect(wrapper.get('nav').text()).not.toContain('People Gator')
  })

  it('renders document controls inside the contextual top bar area', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    const topBar = wrapper.get('nav')

    expect(topBar.text()).not.toContain('People Gator')
    expect(topBar.find('[aria-label="Previous line"]').exists()).toBe(true)
    expect(wrapper.get('main').find('[aria-label="Previous line"]').exists()).toBe(false)
  })

  it('keeps document pagination in the route query', async () => {
    await router.push('/documents?q=history&page=2')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const secondPage = wrapper.get('[aria-label="Page 2"]')

    expect(secondPage.attributes('aria-current')).toBe('page')

    await wrapper.get('[aria-label="Page 1"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'history' })
  })

  it('paginates people results and links cards to person details', async () => {
    await router.push('/people?page=2')

    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.get('[aria-label="Page 2"]').attributes('aria-current')).toBe('page')
    expect(wrapper.findAll('a[href^="/people/"]')).toHaveLength(12)

    await wrapper.get('[aria-label="Page 1"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({})
  })

  it('previews a similar person without replacing the current face or line', async () => {
    await router.push(
      '/libraries/library/documents/document/pages/page?person=face-01&selectedPerson=anna-novakova&line=line-anna',
    )

    const wrapper = mount(App, { global: { plugins: [router] } })
    expect(
      wrapper.get('[aria-label="Preview Anna Nováková on this page"]').attributes('aria-pressed'),
    ).toBe('true')

    await wrapper.get('[aria-label="Preview Josef Svoboda on this page"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({
      person: 'face-01',
      selectedPerson: 'josef-svoboda',
      line: 'line-anna',
      translate: 'off',
    })
    expect(wrapper.get('[aria-labelledby="selected-person-title"] h3').text()).toContain(
      'Anna Nováková',
    )
    expect(wrapper.get('[aria-label="Select Josef Svoboda"]').classes()).toContain('ring-accent/70')
    expect(
      wrapper.get('[aria-label="Preview Josef Svoboda on this page"]').attributes('aria-pressed'),
    ).toBe('true')
  })

  it('treats entity fragments on adjacent transcription lines as one entity', async () => {
    await router.push('/libraries/library/documents/document/pages/page?line=line-anna')

    const wrapper = mount(App, { global: { plugins: [router] } })
    await wrapper.get('[aria-label="Preview Marie Dvořáková on this page"]').trigger('click')
    await flushPromises()

    const relatedFragments = wrapper.findAll('mark[title="Person: Marie Dvořáková"]')
    expect(relatedFragments).toHaveLength(2)
    expect(relatedFragments.every((fragment) => fragment.attributes('style').includes('var(--accent)'))).toBe(true)
    expect(router.currentRoute.value.query.line).toBe('line-library')

    await relatedFragments[1]!.trigger('click')
    await flushPromises()

    const selectedFragments = wrapper.findAll('mark[title="Person: Marie Dvořáková"]')
    expect(selectedFragments.every((fragment) => fragment.attributes('style').includes('var(--secondary)'))).toBe(true)
    expect(router.currentRoute.value.query.line).toBe('line-exhibition')
  })

  it('does not select a face when the route has no person query', async () => {
    await router.push('/libraries/library/documents/document/pages/page?line=line-anna')

    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.get('[aria-labelledby="selected-person-title"]').text()).toContain(
      'No face selected',
    )
    expect(wrapper.get('[aria-label="Select Anna Nováková"]').attributes('aria-pressed')).toBe(
      'false',
    )
    expect(wrapper.get('[aria-label="Select Josef Svoboda"]').attributes('aria-pressed')).toBe(
      'false',
    )
    expect(wrapper.get('[aria-label="Select Unknown person"]').attributes('aria-pressed')).toBe(
      'false',
    )
    expect(router.currentRoute.value.query.person).toBeUndefined()

    await wrapper.get('[aria-label="Select Anna Nováková"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.person).toBe('face-01')
    expect(wrapper.get('[aria-label="Select Anna Nováková"]').attributes('aria-pressed')).toBe(
      'true',
    )

    await wrapper.get('[aria-label="Clear face selection"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.person).toBeUndefined()
    expect(router.currentRoute.value.query.selectedPerson).toBeUndefined()
    expect(wrapper.get('[aria-labelledby="selected-person-title"]').text()).toContain(
      'No face selected',
    )
  })

  it('defines all application pages', () => {
    expect(router.resolve({ name: 'document-search' }).path).toBe('/documents')
    expect(router.resolve({ name: 'people-search' }).path).toBe('/people')
    expect(
      router.resolve({
        name: 'document-page',
        params: { libraryId: 'library', documentId: 'document', pageId: 'page' },
      }).path,
    ).toBe('/libraries/library/documents/document/pages/page')
    expect(router.resolve({ name: 'person-detail', params: { personId: 'person' } }).path).toBe(
      '/people/person',
    )
  })
})
