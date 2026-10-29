import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'

const filters = { 'filter.entity_id': ['person-ada'] }

describe('exact appearance mention groups', () => {
  beforeEach(() => {
    mocks.groups.mockReset().mockResolvedValue({
      data: {
        items: [
          { name: 'Ada Novak', occurrence_count: 3, last_touched_at: null },
          { name: 'ADA NOVAK', occurrence_count: 1, last_touched_at: null },
        ],
        limit: 25,
        total_count: 2,
        cursor: null,
      },
    })
    mocks.mentions.mockReset().mockResolvedValue({
      data: {
        items: [
          {
            mention_id: 'm1',
            name: 'Ada Novak',
            context: 'Ada Novak signed the letter.',
            entity_id: 'person-ada',
            entity_link_state: 'manual',
            source_id: 'page-source',
          },
        ],
        limit: 20,
        total_count: 3,
        cursor: null,
      },
    })
    mocks.page.mockReset().mockResolvedValue({
      data: { source_id: 'page-source', library: 'lib', document_id: 'doc', page_id: 'p1' },
    })
    mocks.document.mockReset().mockResolvedValue({
      data: { source_id: 'doc-source', library: 'lib', document_id: 'doc', name: 'Letters' },
    })
  })

  it('expands groups by default, retains full counts and applies the compact option globally', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    const wrapper = mount(PersonMentionGroups, {
      props: {
        filters,
        groupSort: { field: 'count', direction: 'desc' },
        occurrenceSort: { field: 'source', direction: 'asc' },
        personId: 'person-ada',
        linkStates: [],
      },
      global: {
        plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: { RouterLink: RouterLinkStub, VerifyEntityLink: true, CreationDetails: true },
      },
    })
    await flushPromises()
    expect(mocks.groups.mock.calls[0]![0]).toMatchObject({
      query: { 'filter.entity_id': ['person-ada'], sort: 'count', sort_direction: 'desc' },
    })
    expect(wrapper.text()).toContain('Ada Novak')
    expect(wrapper.text()).toContain('3 occurrences')
    expect(wrapper.text()).toContain('ADA NOVAK')
    expect(wrapper.text()).toContain('Showing 2 of 2 groups')
    expect(mocks.mentions).toHaveBeenCalled()
    expect(wrapper.find('[data-slot=collapsible-trigger]').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'PersonMentionOccurrences' }).exists()).toBe(true)
    await wrapper.setProps({ compact: true })
    expect(wrapper.findComponent({ name: 'PersonMentionOccurrences' }).exists()).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text().includes('Ada Novak'))).toBe(
      false,
    )
    await wrapper.setProps({ compact: false })
    await flushPromises()
    expect(mocks.mentions.mock.calls[0]![0]).toMatchObject({
      query: {
        'filter.entity_id': ['person-ada'],
        'filter.name': ['Ada Novak'],
        sort: 'source',
        sort_direction: 'asc',
      },
    })
    expect(wrapper.text()).toContain('p1')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toMatchObject({
      name: 'document-page',
      params: { libraryId: 'lib', documentId: 'doc', pageId: 'p1' },
    })
  })
  it('keeps pending group skeletons in sync with density and replaces them with loaded records', async () => {
    let resolve!: (value: unknown) => void
    mocks.groups.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        }),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(PersonMentionGroups, {
      props: {
        mode: 'document',
        filters,
        groupSort: { field: 'text', direction: 'asc' },
        occurrenceSort: { field: 'source', direction: 'asc' },
        personId: 'person-ada',
        linkStates: [],
      },
      global: {
        plugins: [router, [VueQueryPlugin, { queryClient: client }]],
        stubs: { RouterLink: RouterLinkStub },
      },
    })
    await flushPromises()
    expect(wrapper.get('[role=status]').attributes('aria-label')).toBe('Loading mention groups')
    expect(wrapper.findAll('[data-mention-group-skeleton]')).toHaveLength(3)
    expect(wrapper.findAll('[data-mention-skeleton]')).toHaveLength(6)
    expect(wrapper.findAll('[data-mention-group-skeleton] button')).toHaveLength(0)
    await wrapper.setProps({ compact: true })
    expect(wrapper.findAll('[data-mention-group-skeleton]')).toHaveLength(3)
    expect(wrapper.findAll('[data-mention-skeleton]')).toHaveLength(0)
    await wrapper.setProps({ compact: false })
    expect(wrapper.findAll('[data-mention-skeleton]')).toHaveLength(6)
    resolve({
      data: {
        items: [
          {
            name: 'Letters',
            source_kind: 'document',
            source_id: 'doc-source',
            library: 'lib',
            document_id: 'doc',
            occurrence_count: 3,
          },
        ],
        cursor: null,
        limit: 25,
        total_count: 1,
      },
    })
    await flushPromises()
    expect(wrapper.find('[aria-label="Loading mention groups"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Letters')
    expect(wrapper.text()).toContain('Ada Novak signed the letter.')
    wrapper.unmount()
    client.clear()
  })
})
