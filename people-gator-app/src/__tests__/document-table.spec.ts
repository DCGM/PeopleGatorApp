import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import DocumentTable from '@/components/custom/DocumentTable.vue'
import { defaultDocumentColumns, documentColumnSizing } from '@/viewmodels/document-table'
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
      { path: '/documents', name: 'document-list', component: { template: '<div />' } },
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
  it('shows the exact defaults with canonical totals and usable document/library/first-page links', async () => {
    const { wrapper, router } = await render()
    await flushPromises()
    expect(wrapper.findAll('th').map((h) => h.text())).toEqual([
      'First page',
      'Document name',
      'Library',
      'Pages',
      'Linked entities',
      'Annotations',
      'Faces',
      'Mentions',
    ])
    expect(
      wrapper
        .findAll('tbody td')
        .slice(1)
        .map((c) => c.text()),
    ).toEqual(['Document archive-id', 'Archive', '2', '1', '6', '4', '2'])
    expect(wrapper.get('td[data-column="first_page"] a').attributes('href')).toBe(
      '/scans?page=first-page-source',
    )
    expect(wrapper.get('td[data-column="name"] a').attributes('href')).toBe(
      '/scans?document=source-a',
    )
    await wrapper.get('td[data-column="library"] a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ library: 'Archive' })
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0')
    expect(wrapper.text()).not.toContain('Restore column widths')
    expect(wrapper.get('button').find('svg').exists()).toBe(true)
  })
  it('keeps stable compact widths across loading, data, sorting and visibility changes', async () => {
    const { wrapper } = await render()
    const widths = () =>
      Object.fromEntries(
        wrapper
          .findAll('col')
          .map((c) => [c.attributes('data-column'), (c.element as HTMLElement).style.width]),
      )
    const original = widths()
    await wrapper.get('button[aria-label^="Sort by Pages:"]').trigger('click')
    await wrapper.setProps({ documents: [] })
    expect(widths()).toEqual(original)
    await wrapper.setProps({
      documents: [{ ...documents[0]!, name: 'ArchiveReference'.repeat(50) }],
    })
    expect(widths()).toEqual(original)
    for (const cell of wrapper.findAll('tbody td'))
      expect((cell.element as HTMLElement).style.width).toBe(
        original[cell.attributes('data-column')!],
      )
    expect((wrapper.get('table').element as HTMLElement).style.width).toBe(
      `${Object.keys(original).reduce((n, id) => n + documentColumnSizing(id).size, 0)}px`,
    )
    expect(documentColumnSizing('ndk').size).toBe(80)
    expect(documentColumnSizing('total').size).toBe(144)
  })
  it('resizes through keyboard headers without sorting and preserves widths when columns hide', async () => {
    const { wrapper } = await render()
    const handle = () => wrapper.get('[role="separator"][aria-label="Resize Document name column"]')
    const width = () => (wrapper.get('col[data-column="name"]').element as HTMLElement).style.width
    await handle().trigger('keydown', { key: 'ArrowRight' })
    expect(width()).toBe('330px')
    await handle().trigger('keydown', { key: 'Home' })
    await handle().trigger('keydown', { key: 'ArrowLeft' })
    expect(width()).toBe('200px')
    await handle().trigger('keydown', { key: 'End' })
    expect(width()).toBe('720px')
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), name: false } })
    expect(wrapper.get('td[data-column="identity"] a').text()).toBe('Archive · archive-id')
    await wrapper.setProps({ visibility: defaultDocumentColumns() })
    expect(width()).toBe('720px')
    await handle().trigger('keydown', { key: 'Enter' })
    expect(width()).toBe('320px')
    expect(wrapper.emitted('update:sort')).toBeUndefined()
  })
  it('cycles every supported header through ascending, descending and no explicit sort', async () => {
    const { wrapper } = await render()
    for (const [label, field] of [
      ['Document name', 'name'],
      ['Pages', 'page_count'],
      ['Annotations', 'annotations_total_count'],
      ['Faces', 'faces_total_count'],
      ['Mentions', 'mentions_total_count'],
    ]) {
      const button = wrapper.get(`button[aria-label="Sort by ${label}: sort ascending"]`)
      expect(button.text()).toBe('')
      expect(button.element.nextSibling?.textContent).toBe(label)
      await button.trigger('click')
      expect(wrapper.emitted('update:sort')?.slice(-1)[0]).toEqual([{ field, direction: 'asc' }])
      expect(button.element.closest('th')?.getAttribute('aria-sort')).toBe('ascending')
      expect(button.attributes('aria-label')).toContain('sort descending')
      await button.trigger('click')
      expect(wrapper.emitted('update:sort')?.slice(-1)[0]).toEqual([{ field, direction: 'desc' }])
      expect(button.element.closest('th')?.getAttribute('aria-sort')).toBe('descending')
      expect(button.attributes('aria-label')).toContain('clear sorting')
      await button.trigger('click')
      expect(wrapper.emitted('update:sort')?.slice(-1)[0]).toEqual([undefined])
      expect(wrapper.find('th[aria-sort]').exists()).toBe(false)
    }
  })
  it('retains configurable annotation breakdowns, unknown/zero values and header associations', async () => {
    const { wrapper } = await render()
    await wrapper.setProps({
      visibility: {
        ...defaultDocumentColumns(),
        faces_manual: true,
        mentions_unassigned: true,
        ndk: true,
      },
      documents: [
        { ...documents[0]!, entity_link_stats: undefined },
        {
          ...documents[0]!,
          source_id: 'empty',
          entity_link_stats: { faces: { total: 0 }, mentions: { total: 0 } },
        },
      ],
    })
    for (const id of ['total', 'faces_total', 'mentions_total'])
      expect(wrapper.findAll(`td[data-column="${id}"]`).map((c) => c.text())).toEqual([
        'Unknown',
        '0',
      ])
    for (const cell of wrapper.findAll('td'))
      expect(document.getElementById(cell.attributes('headers')!)).not.toBeNull()
    expect(wrapper.get('[data-slot="document-source-link"]').attributes('rel')).toBe(
      'noopener noreferrer',
    )
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(document.querySelectorAll('legend')).toHaveLength(3)
    const restore = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Restore defaults',
    )!
    restore.click()
    await flushPromises()
    expect(wrapper.emitted('update:visibility')?.slice(-1)[0]).toEqual([defaultDocumentColumns()])
  })
  it('reuses first-page thumbnails across toggles and handles no pages and missing media', async () => {
    const { wrapper } = await render()
    await flushPromises()
    expect(media.image).toHaveBeenCalledTimes(1)
    expect(wrapper.find('img').exists()).toBe(true)
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), first_page: false } })
    expect(wrapper.find('img').exists()).toBe(false)
    await wrapper.setProps({ visibility: defaultDocumentColumns() })
    await flushPromises()
    expect(media.image).toHaveBeenCalledTimes(1)
    await wrapper.setProps({
      documents: [{ ...documents[0]!, first_page_source_id: null, registered_page_count: 0 }],
    })
    expect(wrapper.text()).toContain('No pages')
    media.image.mockRejectedValue({ isAxiosError: true, response: { status: 404 } })
    await wrapper.setProps({ documents: [{ ...documents[0]!, first_page_source_id: 'missing' }] })
    await flushPromises()
    expect(wrapper.text()).toContain('No preview')
    expect(wrapper.get('td[data-column="first_page"] a').attributes('href')).toBe(
      '/scans?page=missing',
    )
  })
})
