import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import type { Face } from '@/viewmodels/document-workspace.types'

const mocks = vi.hoisted(() => ({
  groups: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  mentions: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  page: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  document: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listTextMentionGroupsRouteApiV1TextMentionGroupsGet: mocks.groups,
  listTextMentionsRouteApiV1TextMentionsGet: mocks.mentions,
  getPageRouteApiV1PagesPageSourceIdGet: mocks.page,
  lookupDocumentRouteApiV1DocumentsLookupGet: mocks.document,
}))
// A reviewer who may annotate still gets no selection in the scan sidebar.
vi.mock('@/composables/can-annotate', async () => {
  const { ref } = await import('vue')
  return { useCanAnnotate: () => ref(true) }
})

import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'

describe('scan Mentions and face card (#103)', () => {
  it('omits mention selection only where it is turned off', async () => {
    mocks.groups.mockResolvedValue({
      data: {
        items: [{ name: 'Hana Sidebar', occurrence_count: 1, last_touched_at: null }],
        total_count: 1,
        cursor: null,
      },
    })
    mocks.mentions.mockResolvedValue({
      data: {
        items: [
          {
            mention_id: 'm1',
            name: 'Hana Sidebar',
            context: 'Hana Sidebar opened the ledger.',
            entity_id: null,
            entity_link_state: null,
            source_id: 'page-source',
          },
        ],
        total_count: 1,
        cursor: null,
      },
    })
    mocks.page.mockResolvedValue({
      data: { source_id: 'page-source', library: 'lib', document_id: 'doc', page_id: 'p1' },
    })
    mocks.document.mockResolvedValue({ data: { library: 'lib', document_id: 'doc' } })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    const mountGroups = (selectable?: boolean) =>
      mount(PersonMentionGroups, {
        props: {
          filters: { 'filter.page_source_id': ['page-source'] },
          groupSort: { field: 'text', direction: 'asc' },
          occurrenceSort: { field: 'text', direction: 'asc' },
          linkStates: [],
          compactOccurrences: true,
          ...(selectable !== undefined && { selectable }),
        },
        global: {
          plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
          stubs: { RouterLink: RouterLinkStub },
        },
      })
    const person = mountGroups()
    const scan = mountGroups(false)
    await flushPromises()
    // Person detail keeps group and occurrence selection.
    expect(person.findAll('[role="checkbox"]')).toHaveLength(2)
    expect(scan.text()).toContain('Hana Sidebar opened the ledger.')
    expect(scan.findAll('[role="checkbox"]')).toHaveLength(0)
  })

  it('shows the selected face card without a Current badge', () => {
    const face = {
      id: 'face',
      personId: 'person',
      name: 'Hana Sidebar',
      position: { left: 0, top: 0, width: 1, height: 1 },
      linkState: 'automatic',
    } as unknown as Face
    const wrapper = mount(SelectedFaceItem, {
      props: { face },
      slots: { actions: () => h('span') },
      global: {
        stubs: { RouterLink: RouterLinkStub, IdentityFacePreview: true, LoadableImage: true },
      },
    })
    expect(wrapper.text()).toContain('Hana Sidebar')
    expect(wrapper.text()).not.toMatch(/current/i)
  })
})
