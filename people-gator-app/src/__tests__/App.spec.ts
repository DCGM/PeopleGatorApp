import { describe, it, expect } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import router from '../router'

describe('App', () => {
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
