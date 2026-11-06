import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import DocumentTable from '@/components/custom/DocumentTable.vue'
import {
  defaultDocumentColumnOrder,
  defaultDocumentColumns,
  documentColumnSizing,
} from '@/viewmodels/document-table'
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
      { path: '/pages/:pageSourceId', name: 'page-source', component: { template: '<div />' } },
      { path: '/documents', name: 'document-list', component: { template: '<div />' } },
      { path: '/scans', name: 'document-search', component: { template: '<div />' } },
    ],
  })
  await router.push('/documents?view=table&library=Archive&link_state=verified')
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 60_000 } },
  })
  const visibility = ref(defaultDocumentColumns())
  const order = ref(defaultDocumentColumnOrder())
  const wrapper = mount(DocumentTable, {
    props: {
      documents,
      visibility: visibility.value,
      'onUpdate:visibility': (value) => {
        visibility.value = value
        void wrapper.setProps({ visibility: value })
      },
      order: order.value,
      'onUpdate:order': (value) => {
        order.value = value
        void wrapper.setProps({ order: value })
      },
    },
    attachTo: document.body,
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  })
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  return { wrapper, router, visibility, order }
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
      'Add column',
    ])
    expect(
      wrapper
        .findAll('tbody td')
        .slice(1)
        .map((c) => c.text()),
    ).toEqual(['Document archive-id', 'Archive', '2', '1', '6', '4', '2', ''])
    expect(wrapper.get('td[data-column="first_page"] a').attributes('href')).toBe(
      '/pages/first-page-source',
    )
    expect(wrapper.get('td[data-column="name"] a').attributes('href')).toBe(
      '/pages/first-page-source',
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
          .findAll('col[data-column]')
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
    for (const cell of wrapper.findAll('tbody td[data-column]'))
      expect((cell.element as HTMLElement).style.width).toBe(
        original[cell.attributes('data-column')!],
      )
    // The add column takes the rest of a wider region (min-w-full), or at least 160px.
    expect((wrapper.get('table').element as HTMLElement).style.width).toBe(
      `${Object.keys(original).reduce((n, id) => n + documentColumnSizing(id).size, 160)}px`,
    )
    expect(wrapper.get('col[data-add-column]').attributes('style')).toBeUndefined()
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
  })
  it('adds one hidden column from the grouped header menu, also opened from any column cell', async () => {
    const { wrapper, visibility, order } = await render()
    const trigger = wrapper.get('th[data-add-column] button')
    expect(trigger.text()).toBe('Add column')
    await wrapper.get('tbody td[data-add-column]').trigger('click')
    await flushPromises()
    const menu = document.querySelector('[role="menu"]')!
    expect(
      [...menu.querySelectorAll('[data-slot="dropdown-menu-label"]')].map((l) => l.textContent),
    ).toEqual(['Document fields', 'All annotations', 'Faces', 'Text mentions'])
    const items = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')]
    const names = items.map((item) => item.getAttribute('aria-label') ?? item.textContent)
    // Shown fields are not offered again.
    expect(names).not.toContain('Document name')
    expect(names).not.toContain('Faces: Total')
    expect(names).toContain('NDK')
    expect(names).toContain('Faces: Manual')
    items.find((item) => item.getAttribute('aria-label') === 'Faces: Manual')!.click()
    await flushPromises()
    expect(visibility.value.faces_manual).toBe(true)
    expect(document.querySelector('[role="menu"]')).toBeNull()
    expect(document.activeElement).toBe(trigger.element)
    expect(order.value.indexOf('faces_manual')).toBe(order.value.indexOf('mentions_total') + 1)
    expect(
      wrapper
        .findAll('thead th')
        .map((h) => h.text())
        .slice(-2),
    ).toEqual(['Faces: Manual', 'Add column'])
    await wrapper.get('tbody td[data-add-column]').trigger('click')
    await flushPromises()
    ;[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')]
      .find((item) => item.textContent === 'Restore default columns')!
      .click()
    await flushPromises()
    expect(visibility.value).toEqual(defaultDocumentColumns())
    expect(order.value).toEqual(defaultDocumentColumnOrder())
  })
  it('removes a column only after a confirming second activation', async () => {
    const { wrapper, visibility } = await render()
    const remove = () => wrapper.find('[data-remove-column="library"]')
    expect(remove().attributes('aria-label')).toBe('Remove Library column')
    await remove().trigger('click')
    expect(visibility.value.library).toBe(true)
    expect(remove().attributes('aria-label')).toBe('Confirm removing Library column')
    expect(remove().text()).toBe('Remove')
    await remove().trigger('blur')
    expect(remove().attributes('aria-label')).toBe('Remove Library column')
    await remove().trigger('click')
    await remove().trigger('click')
    expect(visibility.value.library).toBe(false)
    expect(wrapper.find('th[data-column="library"]').exists()).toBe(false)
    // The fallback link column replaces the name and cannot be removed.
    await wrapper.setProps({ visibility: { ...visibility.value, name: false } })
    expect(wrapper.find('[data-remove-column="identity"]').exists()).toBe(false)
  })
  it('reorders visible columns from the header handle by keyboard and pointer', async () => {
    const { wrapper, order } = await render()
    const headers = () =>
      wrapper.findAll('thead th[data-column]').map((h) => h.attributes('data-column'))
    const handle = (id: string) => wrapper.get(`[data-move-column="${id}"]`)
    expect(handle('name').attributes('aria-label')).toBe('Move Document name column')
    await handle('name').trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(headers().slice(0, 3)).toEqual(['first_page', 'library', 'name'])
    expect(document.activeElement).toBe(handle('name').element)
    expect(wrapper.get('p.sr-only[role="status"]').text()).toBe(
      'Document name moved to position 3 of 8',
    )
    await handle('first_page').trigger('keydown', { key: 'ArrowLeft' })
    expect(headers()[0]).toBe('first_page')
    // Hidden fields between visible neighbours do not absorb a move.
    await handle('linked_entity_count').trigger('keydown', { key: 'ArrowRight' })
    expect(headers().slice(4, 6)).toEqual(['total', 'linked_entity_count'])

    // Pointer: drop Mentions on the left half of First page.
    const box = (left: number) =>
      ({ left, right: left + 100, width: 100, top: 0, bottom: 40, height: 40 }) as DOMRect
    const cells = wrapper.findAll('thead th[data-column]')
    cells.forEach((cell, index) => {
      cell.element.getBoundingClientRect = () => box(index * 100)
    })
    const mentions = handle('mentions_total').element
    mentions.dispatchEvent(new PointerEvent('pointerdown', { button: 0, pointerId: 1 }))
    mentions.dispatchEvent(new PointerEvent('pointermove', { clientX: 20, pointerId: 1 }))
    await flushPromises()
    expect(wrapper.get('th[data-column="first_page"]').classes()).toContain('before:bg-primary')
    mentions.dispatchEvent(new PointerEvent('pointerup', { clientX: 20, pointerId: 1 }))
    await flushPromises()
    expect(headers()[0]).toBe('mentions_total')
    expect(order.value.indexOf('mentions_total')).toBeLessThan(order.value.indexOf('first_page'))
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
    expect(wrapper.get('td[data-column="first_page"] a').attributes('href')).toBe('/pages/missing')
  })
})
