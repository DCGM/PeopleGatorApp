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
  it('keeps one applied width model through data, sorting, media and visibility changes', async () => {
    const { wrapper } = await render()
    const widths = () =>
      Object.fromEntries(
        wrapper
          .findAll('col')
          .map((col) => [col.attributes('data-column')!, (col.element as HTMLElement).style.width]),
      )
    const original = widths()
    const checkModel = () => {
      const current = widths()
      const total = Object.keys(current).reduce((sum, id) => sum + documentColumnSizing(id).size, 0)
      expect((wrapper.get('table').element as HTMLElement).style.width).toBe(`${total}px`)
      expect(wrapper.get('table').classes()).toContain('table-fixed')
      for (const cell of wrapper.findAll('tbody td')) {
        expect((cell.element as HTMLElement).style.width).toBe(
          current[cell.attributes('data-column')!],
        )
        expect(cell.classes()).toContain('[overflow-wrap:anywhere]')
      }
    }
    checkModel()
    await wrapper.get('button[aria-label="Sort by Document name"]').trigger('click')
    await wrapper.setProps({ documents: [] })
    expect(widths()).toEqual(original)
    checkModel()
    await wrapper.setProps({
      documents: [
        {
          ...documents[0]!,
          name: 'ArchiveReference'.repeat(50),
          library: 'Long archive'.repeat(20),
        },
      ],
    })
    expect(widths()).toEqual(original)
    expect(wrapper.get('tbody td').text()).toBe('ArchiveReference'.repeat(50))
    checkModel()
    await wrapper.setProps({
      visibility: {
        ...defaultDocumentColumns(),
        first_page: true,
        faces_total: true,
        faces_manual: true,
      },
    })
    await flushPromises()
    checkModel()
    expect(widths().first_page).toBe('144px')
    expect(
      (wrapper.get('th[scope="colgroup"][colspan="2"]').element as HTMLElement).style.width,
    ).toBe('320px')
    for (const [id, width] of Object.entries(original)) expect(widths()[id]).toBe(width)
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), library: false } })
    checkModel()
    expect(widths().library).toBeUndefined()
    await wrapper.setProps({
      visibility: defaultDocumentColumns(),
      documents: [...documents, { ...documents[0]!, source_id: 'appended' }],
    })
    expect(widths()).toEqual(original)
    checkModel()
    for (const button of wrapper.findAll('thead button[aria-label^="Sort by"]')) {
      expect(button.get('span[aria-hidden="true"]').classes()).toContain('size-4')
    }
  })
  it('resizes only through leaf headers, respects bounds and keeps sorting and visibility independent', async () => {
    const { wrapper } = await render()
    const handle = () => wrapper.get('[role="separator"][aria-label="Resize Document name column"]')
    const width = () => (wrapper.get('col[data-column="name"]').element as HTMLElement).style.width
    expect(wrapper.findAll('tbody [role="separator"]')).toHaveLength(0)
    expect(wrapper.findAll('th[scope="colgroup"] [role="separator"]')).toHaveLength(0)
    await handle().trigger('keydown', { key: 'ArrowRight' })
    expect(width()).toBe('330px')
    await handle().trigger('keydown', { key: 'ArrowLeft', shiftKey: true })
    expect(width()).toBe('290px')
    await handle().trigger('keydown', { key: 'Home' })
    await handle().trigger('keydown', { key: 'ArrowLeft' })
    expect(width()).toBe('200px')
    await handle().trigger('keydown', { key: 'End' })
    await handle().trigger('keydown', { key: 'ArrowRight' })
    expect(width()).toBe('720px')
    expect(handle().attributes('aria-valuenow')).toBe('720')
    await handle().trigger('click')
    expect(wrapper.emitted('update:sort')).toBeUndefined()
    await wrapper.setProps({
      documents: [],
      visibility: { ...defaultDocumentColumns(), name: false },
    })
    await wrapper.setProps({ documents, visibility: defaultDocumentColumns() })
    expect(width()).toBe('720px')
    await handle().trigger('keydown', { key: 'Enter' })
    expect(width()).toBe('320px')
    await handle().trigger('keydown', { key: 'ArrowRight' })
    await wrapper.get('button[aria-label="Sort by Document name"]').trigger('click')
    expect(width()).toBe('330px')
    const sortChanges = wrapper.emitted('update:sort')?.length
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), first_page: true } })
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Restore column widths')!
      .trigger('click')
    expect(width()).toBe('320px')
    expect(wrapper.find('col[data-column="first_page"]').exists()).toBe(true)
    expect(wrapper.emitted('update:sort')).toHaveLength(sortChanges!)
  })
  it('renders one row per document, full summaries, unknowns and navigation', async () => {
    const { wrapper } = await render()
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.findAll('tbody td').map((cell) => cell.text())).toEqual([
      'Document archive-id',
      'NDK',
      'Archive',
      '2',
      'Unknown',
      '1',
      '6',
      '2',
      '1',
      '1',
      '2',
    ])
    expect(wrapper.findAll('th')[0]!.text()).toBe('Document name')
    expect(wrapper.findAll('tbody a[href^="/scans"]')).toHaveLength(1)
    const link = wrapper.get('tbody a[href^="/scans"]')
    expect(link.attributes('href')).toBe(
      '/scans?library=Archive&link_state=verified&document=source-a',
    )
    expect(link.attributes('aria-label')).toContain('archive-id')
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0')
    const description = wrapper.get('table').attributes('aria-describedby')
    expect(wrapper.get(`[id="${description}"]`).text()).toContain('Counts cover')
    expect(wrapper.get('[role="region"]').attributes('aria-describedby')).toBeUndefined()
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
    expect(wrapper.get('tbody a[href^="/scans"]').text()).toBe('Archive · archive-id')
    for (const label of labels()) {
      const checkbox = label.querySelector('[role="checkbox"]') as HTMLElement
      if (checkbox.getAttribute('data-state') === 'checked') {
        checkbox.click()
        await flushPromises()
      }
    }
    await flushPromises()
    expect(wrapper.findAll('th').map((cell) => cell.text())).toEqual(['Document'])
    expect(wrapper.get('tbody a[href^="/scans"]').attributes('aria-label')).toContain('Archive')
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
    expect(wrapper.findAll('tbody a[href^="/scans"]')).toHaveLength(1)
    expect(wrapper.get('tbody a[href^="/scans"]').text()).toBe('archive-id')
    await wrapper.get('tbody a[href^="/scans"]').trigger('click')
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
  it('shows a simple external NDK link immediately after the name without enabling thumbnails', async () => {
    const { wrapper, router } = await render()
    expect(
      wrapper
        .findAll('th')
        .slice(0, 2)
        .map((cell) => cell.text()),
    ).toEqual(['Document name', 'NDK'])
    const link = wrapper.get('tbody td:nth-child(2) [data-slot="document-source-link"]')
    expect(link.find('svg[aria-hidden="true"]').exists()).toBe(true)
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
    expect(media.image).not.toHaveBeenCalled()
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
  it('groups annotation choices and shows independent face/mention counts', async () => {
    const { wrapper, visibility } = await render()
    expect(wrapper.findAll('th[scope="colgroup"]').map((h) => h.text())).toEqual([
      'All annotations',
    ])
    await wrapper.setProps({
      documents: [
        {
          ...documents[0]!,
          entity_link_stats: {
            faces: { total: 18, automatic: 2, manual: 3, verified: 5, unassigned: 8 },
            mentions: { total: 25, automatic: 11, manual: 7, verified: 4, unassigned: 3 },
          },
        },
      ],
    })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect([...document.querySelectorAll('legend')].map((node) => node.textContent)).toEqual([
      'All annotations',
      'Faces',
      'Text mentions',
    ])
    for (const scope of ['Faces', 'Text mentions']) {
      for (const state of ['Total', 'Automatic', 'Manual', 'Verified', 'Unassigned']) {
        ;(
          document.querySelector(
            `[role="checkbox"][aria-label="${scope}: ${state}"]`,
          ) as HTMLElement
        ).click()
        await flushPromises()
      }
    }
    expect(
      wrapper.findAll('th[scope="colgroup"]').map((h) => [h.text(), h.attributes('colspan')]),
    ).toEqual([
      ['All annotations', '5'],
      ['Faces', '5'],
      ['Text mentions', '5'],
    ])
    for (const [prefix, expected] of [
      ['', ['43', '13', '10', '9', '11']],
      ['faces_', ['18', '2', '3', '5', '8']],
      ['mentions_', ['25', '11', '7', '4', '3']],
    ] as const) {
      expect(
        ['total', 'automatic', 'manual', 'verified', 'unassigned'].map((state) =>
          wrapper.get(`td[data-column="${prefix}${state}"]`).text(),
        ),
      ).toEqual(expected)
    }
    const cell = wrapper.get('td[data-column="faces_total"]')
    for (const id of cell.attributes('headers')!.split(' '))
      expect(document.getElementById(id)).not.toBeNull()
    expect(wrapper.get('th').attributes('rowspan')).toBe('2')
    const selected = { ...visibility.value }
    await wrapper.setProps({ documents: [...documents, { ...documents[0]!, source_id: 'second' }] })
    expect(visibility.value).toEqual(selected)
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(media.image).not.toHaveBeenCalled()
    const restore = [...document.querySelectorAll('button')].find(
      (button) => button.textContent === 'Restore defaults',
    )!
    restore.click()
    await flushPromises()
    expect(visibility.value).toEqual(defaultDocumentColumns())
    expect(wrapper.findAll('th[scope="colgroup"]').map((h) => h.text())).toEqual([
      'All annotations',
    ])
  })
  it('distinguishes zero counts from missing summaries for each annotation group', async () => {
    const { wrapper } = await render()
    await wrapper.setProps({
      documents: [
        { ...documents[0]!, entity_link_stats: undefined },
        {
          ...documents[0]!,
          source_id: 'empty',
          entity_link_stats: { faces: { total: 0 }, mentions: { total: 0 } },
        },
      ],
      visibility: { ...defaultDocumentColumns(), faces_total: true, mentions_total: true },
    })
    for (const column of ['total', 'faces_total', 'mentions_total']) {
      expect(wrapper.findAll(`td[data-column="${column}"]`).map((cell) => cell.text())).toEqual([
        'Unknown',
        '0',
      ])
    }
  })
  it('offers only supported server sort fields and flips their indicated direction', async () => {
    const { wrapper } = await render()
    await wrapper.setProps({ visibility: { ...defaultDocumentColumns(), document_id: true } })
    expect(
      wrapper
        .findAll('thead button[aria-label^="Sort by"]')
        .map((button) => button.attributes('aria-label')),
    ).toEqual([
      'Sort by Document name',
      'Sort by Library',
      'Sort by Document ID',
      'Sort by Pages',
      'Sort by Last modified',
      ...['Total', 'Automatic', 'Manual', 'Verified', 'Unassigned'].map(
        (state) => `Sort by All annotations: ${state}`,
      ),
    ])
    expect(wrapper.get('th[aria-sort="ascending"]').text()).toBe('Document name')
    for (const [label, field, natural] of [
      ['Pages', 'page_count', 'desc'],
      ['Library', 'library', 'asc'],
      ['Document ID', 'document_id', 'asc'],
      ['Last modified', 'last_touched_at', 'desc'],
      ['Document name', 'name', 'asc'],
      ...['Total', 'Automatic', 'Manual', 'Verified', 'Unassigned'].map((state) => [
        `All annotations: ${state}`,
        `annotations_${state.toLowerCase()}_count`,
        'desc',
      ]),
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
