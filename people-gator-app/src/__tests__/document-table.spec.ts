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
      'Open',
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
    const link = wrapper.get('tbody a')
    expect(link.attributes('href')).toBe(
      '/scans?library=Archive&link_state=verified&document=source-a',
    )
    expect(link.attributes('aria-label')).toContain('archive-id')
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0')
  })
  it('shows and hides every data field including name, retains Open and restores defaults', async () => {
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
  it('loads just one thumbnail when First page is enabled and reuses it across toggles', async () => {
    const { wrapper, visibility } = await render()
    expect(media.image).not.toHaveBeenCalled()
    expect(wrapper.find('img').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const toggle = document
      .querySelector('label')!
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
  it('shows a short fallback when the registered first page has no stored image', async () => {
    media.image.mockRejectedValue({ isAxiosError: true, response: { status: 404 } })
    const { wrapper } = await render()
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), first_page: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('No preview')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(media.image).toHaveBeenCalledTimes(1)
  })
})
