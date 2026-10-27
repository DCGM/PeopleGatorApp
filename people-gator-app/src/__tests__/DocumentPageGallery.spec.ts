import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DocumentPageGallery from '@/components/custom/DocumentPageGallery.vue'
import { pageGalleryQuery, type PageGalleryItem } from '@/viewmodels/document-page-gallery'

const item = (index: number, current = false): PageGalleryItem => ({
  sourceId: `source-${index}`,
  library: 'preview-mzk',
  documentId: 'doc',
  pageId: `page-${index}`,
  label: `page-${index}`,
  current,
  thumbnailUrl: index === 2 ? '' : `blob:${index}`,
  thumbnailLoading: false,
  thumbnailFailed: index === 2,
})

async function mountGallery(props: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: defineComponent(() => () => null),
      },
    ],
  })
  await router.push({
    name: 'document-page',
    params: { libraryId: 'preview-mzk', documentId: 'doc', pageId: 'page-1' },
    query: { person: 'face', line: 'l1', link_state: 'manual', evidence_user: 'user' },
  })
  const wrapper = mount(DocumentPageGallery, {
    attachTo: document.body,
    props: {
      items: [item(1, true), item(2), item(3)],
      totalCount: 3,
      location: (target: PageGalleryItem) => ({
        name: 'document-page',
        params: { libraryId: target.library, documentId: target.documentId, pageId: target.pageId },
        query: pageGalleryQuery(router.currentRoute.value.query),
      }),
      ...props,
    },
    global: { plugins: [router] },
  })
  return { wrapper, router }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('DocumentPageGallery', () => {
  it('exposes the API document target beside the title, without nesting page links', async () => {
    const url = 'https://archive.example/document-from-api'
    const { wrapper } = await mountGallery({ documentUrl: url })
    const link = wrapper.get('a[target="_blank"]')
    expect(link.attributes('href')).toBe(url)
    expect(link.attributes('aria-label')).toContain('document in Digitální knihovna (new tab)')
    expect(link.element.parentElement?.querySelector('h2')?.textContent).toContain('Document pages')
    expect(wrapper.find('a a').exists()).toBe(false)
    await wrapper.setProps({ documentUrl: undefined })
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('names every page link and marks only the current page', async () => {
    const { wrapper } = await mountGallery()
    const nav = wrapper.get('nav')
    expect(nav.attributes('aria-labelledby')).toBe('document-pages-title')
    expect(wrapper.get('#document-pages-title').text()).toContain('Document pages')
    expect(wrapper.get('#document-pages-title').text()).toContain('3 pages')
    const links = wrapper.findAll('a')
    expect(links.map((link) => link.attributes('aria-label'))).toEqual([
      'Page page-1, current page',
      'Page page-2',
      'Page page-3',
    ])
    expect(links.map((link) => link.attributes('aria-current'))).toEqual([
      'page',
      undefined,
      undefined,
    ])
    expect(links[1]!.text()).toContain('No preview')
    wrapper.unmount()
  })

  it('opens another page in the workspace, keeping filters and dropping page selections', async () => {
    const { wrapper, router } = await mountGallery()
    await wrapper.findAll('a')[2]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.pageId).toBe('page-3')
    expect(router.currentRoute.value.query).toEqual({
      link_state: 'manual',
      evidence_user: 'user',
    })
    wrapper.unmount()
  })

  it('keeps gallery keys away from the viewer shortcuts', async () => {
    const { wrapper } = await mountGallery()
    const listener = vi.fn()
    window.addEventListener('keydown', listener)
    await wrapper.findAll('a')[1]!.trigger('keydown', { key: 'ArrowRight' })
    window.removeEventListener('keydown', listener)
    expect(listener).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('offers more pages and a retry for a failed page list', async () => {
    const { wrapper } = await mountGallery({ hasNextPage: true })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('load-more')).toHaveLength(1)

    await wrapper.setProps({ error: true, hasNextPage: true })
    expect(wrapper.get('[role=alert]').text()).toContain('Could not load document pages.')
    expect(wrapper.findAll('button').map((button) => button.text())).toEqual(['Retry pages'])
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    wrapper.unmount()
  })

  it('shows loading placeholders and announces a single-page document', async () => {
    const { wrapper } = await mountGallery({ items: [], totalCount: null, loading: true })
    expect(wrapper.text()).toContain('Loading document pages…')
    expect(wrapper.findAll('li[aria-hidden=true]')).toHaveLength(3)
    await wrapper.setProps({ items: [item(1, true)], totalCount: 1, loading: false })
    expect(wrapper.text()).toContain('1 page')
    expect(wrapper.text()).toContain('This document has one registered page.')
    wrapper.unmount()
  })
})
