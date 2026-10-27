import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import DocumentTable from '@/components/custom/DocumentTable.vue'
import { defaultDocumentColumns } from '@/viewmodels/document-table'
import type { DocumentResponse } from '@/client'

const media = vi.hoisted(() => ({ image: vi.fn() }))
vi.mock('@/client', () => ({ getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: media.image }))
beforeEach(() => {
  media.image.mockReset()
  media.image.mockResolvedValue({ data: new Blob(['page'], { type: 'image/jpeg' }) })
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:first-page', revokeObjectURL: vi.fn() })
})
const documents: DocumentResponse[] = [
  {
    source_id: 'source-a',
    source_type: 'document',
    url: 'https://example.test',
    library: 'Archive',
    document_id: 'archive-id',
    name: '  ',
    registered_page_count: 2,
    first_page_source_id: 'first-page-source',
    linked_entity_count: 1,
    last_touched_by_user_name: 'Reviewer',
    last_touched_by_user_id: 'user',
    last_touched_by_api_key_id: null,
    entity_link_stats: {
      faces: { total: 4, automatic: 1, verified: 1, manual: 1, unassigned: 1 },
      mentions: { total: 2, automatic: 1, unassigned: 1 },
    },
  },
]
const cleanups: (() => void)[] = []
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  vi.unstubAllGlobals()
})
async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/documents', component: { template: '<div />' } },
      { path: '/scans', name: 'document-search', component: { template: '<div />' } },
    ],
  })
  await router.push('/documents?view=table&library=Archive&link_state=verified')
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 60_000 } },
  })
  const visibility = ref(defaultDocumentColumns())
  const wrapper = mount(DocumentTable, {
    props: {
      documents,
      visibility: visibility.value,
      'onUpdate:visibility': (value) => {
        visibility.value = value
        void wrapper.setProps({ visibility: value })
      },
    },
    attachTo: document.body,
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  })
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  return { wrapper, router, visibility }
}
describe('document table', () => {
  it('renders one row per document, full summaries, unknowns and navigation', async () => {
    const { wrapper } = await render()
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.findAll('tbody td').map((cell) => cell.text())).toEqual([
      'Document archive-id',
      'Archive',
      '2',
      'Unknown',
      '6',
      '2',
      '1',
      '1',
      '2',
      '1',
    ])
    expect(wrapper.findAll('th')[0]!.text()).toBe('Document name')
    expect(wrapper.findAll('tbody a')).toHaveLength(1)
    const link = wrapper.get('tbody a')
    expect(link.attributes('href')).toBe(
      '/scans?library=Archive&link_state=verified&document=source-a',
    )
    expect(link.attributes('aria-label')).toContain('archive-id')
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0')
  })
  it('shows and hides every data field including name, retains identity navigation and restores defaults', async () => {
    const { wrapper, visibility } = await render()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const labels = () => [...document.querySelectorAll('label')]
    const name = labels().find((label) => label.textContent?.includes('Document name'))!
    ;(name.querySelector('[role="checkbox"]') as HTMLElement).click()
    await flushPromises()
    expect(visibility.value.name).toBe(false)
    expect(wrapper.findAll('th').map((cell) => cell.text())).not.toContain('Document name')
    expect(wrapper.get('tbody a').text()).toBe('Archive · archive-id')
    for (const label of labels()) {
      const checkbox = label.querySelector('[role="checkbox"]') as HTMLElement
      if (checkbox.getAttribute('data-state') === 'checked') {
        checkbox.click()
        await flushPromises()
      }
    }
    await flushPromises()
    expect(wrapper.findAll('th').map((cell) => cell.text())).toEqual(['Document'])
    expect(wrapper.get('tbody a').attributes('aria-label')).toContain('Archive')
    const restore = [...document.querySelectorAll('button')].find(
      (button) => button.textContent === 'Restore defaults',
    )!
    restore.click()
    await flushPromises()
    expect(visibility.value).toEqual(defaultDocumentColumns())
    expect(wrapper.findAll('th').map((cell) => cell.text())).toContain('Document name')
    // Appending results changes data, never field selections.
    await wrapper.setProps({
      documents: [...documents, { ...documents[0]!, source_id: 'second', name: 'Second' }],
    })
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(visibility.value).toEqual(defaultDocumentColumns())
  })
  it('uses the document ID link when the name is hidden without an extra column', async () => {
    const { wrapper, router } = await render()
    await wrapper.setProps({
      visibility: { ...defaultDocumentColumns(), name: false, document_id: true },
    })
    expect(wrapper.findAll('th').map((cell) => cell.text())).not.toContain('Document')
    expect(wrapper.findAll('tbody a')).toHaveLength(1)
    expect(wrapper.get('tbody a').text()).toBe('archive-id')
    await wrapper.get('tbody a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: ['Archive'],
      link_state: ['verified'],
      document: 'source-a',
    })
  })
  it('opens a named document from the first cell', async () => {
    const { wrapper, router } = await render()
    await wrapper.setProps({ documents: [{ ...documents[0]!, name: 'Named ledger' }] })
    expect(wrapper.get('tbody td a').text()).toBe('Named ledger')
    await wrapper.get('tbody td a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-search')
    expect(router.currentRoute.value.query.document).toBe('source-a')
  })
  it('loads just one thumbnail when First page is enabled and reuses it across toggles', async () => {
    const { wrapper, visibility } = await render()
    expect(media.image).not.toHaveBeenCalled()
    expect(wrapper.find('img').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const toggle = [...document.querySelectorAll('label')]
      .find((label) => label.textContent?.includes('First page'))!
      .querySelector('[role="checkbox"]') as HTMLElement
    expect(toggle.closest('label')?.textContent).toContain('First page')
    toggle.click()
    await flushPromises()
    expect(visibility.value.first_page).toBe(true)
    expect(media.image).toHaveBeenCalledTimes(1)
    expect(media.image).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { page_source_id: 'first-page-source' },
        query: { width: 256 },
      }),
    )
    expect(wrapper.findAll('tbody img')).toHaveLength(1)
    expect(wrapper.get('tbody img').attributes('alt')).toBe(
      'First registered page of Document archive-id',
    )
    toggle.click()
    await flushPromises()
    expect(wrapper.find('img').exists()).toBe(false)
    toggle.click()
    await flushPromises()
    expect(media.image).toHaveBeenCalledTimes(1)
    await wrapper.setProps({
      documents: [{ ...documents[0]!, first_page_source_id: null, registered_page_count: 0 }],
    })
    await flushPromises()
    expect(wrapper.text()).toContain('No pages')
    expect(media.image).toHaveBeenCalledTimes(1)
  })
  it('overlays the source link as NDK and expands its name on keyboard focus', async () => {
    const { wrapper, router } = await render()
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), first_page: true } })
    await flushPromises()
    const link = wrapper.get('[data-slot="document-source-link"]')
    expect(link.text()).toBe('NDK')
    expect(link.attributes('href')).toBe(documents[0]!.url)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(link.attributes('aria-label')).toContain('Národní digitální knihovna')
    await link.trigger('focus')
    await flushPromises()
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain(
      'Národní digitální knihovna',
    )
    expect(router.currentRoute.value.path).toBe('/documents')
    expect(wrapper.get('tbody td:first-child a').attributes('href')).toContain('/scans?')
    expect(media.image).toHaveBeenCalledTimes(1)
  })
  it('shows a short fallback when the registered first page has no stored image', async () => {
    media.image.mockRejectedValue({ isAxiosError: true, response: { status: 404 } })
    const { wrapper } = await render()
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), first_page: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('No preview')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(media.image).toHaveBeenCalledTimes(1)
  })
  it('offers only supported server sort fields and flips their indicated direction', async () => {
    const { wrapper } = await render()
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), document_id: true } })
    expect(
      wrapper.findAll('thead button').map((button) => button.attributes('aria-label')),
    ).toEqual([
      'Sort by Document name',
      'Sort by Library',
      'Sort by Document ID',
      'Sort by Pages',
      'Sort by Last modified',
    ])
    expect(wrapper.get('th[aria-sort="ascending"]').text()).toBe('Document name')
    for (const [label, field, natural] of [
      ['Pages', 'page_count', 'desc'],
      ['Library', 'library', 'asc'],
      ['Document ID', 'document_id', 'asc'],
      ['Last modified', 'last_touched_at', 'desc'],
      ['Document name', 'name', 'asc'],
    ]) {
      const button = wrapper.get(`button[aria-label="Sort by ${label}"]`)
      await button.trigger('click')
      expect(wrapper.emitted('update:sort')?.slice(-1)[0]).toEqual([{ field, direction: natural }])
      expect(button.element.closest('th')?.getAttribute('aria-sort')).toBe(
        natural === 'asc' ? 'ascending' : 'descending',
      )
      expect(button.find('svg').exists()).toBe(true)
      const flipped = natural === 'asc' ? 'desc' : 'asc'
      await button.trigger('click')
      expect(wrapper.emitted('update:sort')?.slice(-1)[0]).toEqual([{ field, direction: flipped }])
      expect(button.element.closest('th')?.getAttribute('aria-sort')).toBe(
        flipped === 'asc' ? 'ascending' : 'descending',
      )
      expect(wrapper.findAll('th[aria-sort]')).toHaveLength(1)
    }
  })
})
