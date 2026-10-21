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

  it('shows distinct spellings with full counts and loads exact occurrences on demand', async () => {
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
    expect(wrapper.text()).toContain('“Ada Novak”')
    expect(wrapper.text()).toContain('3 occurrences')
    expect(wrapper.text()).toContain('“ADA NOVAK”')
    expect(wrapper.text()).toContain('Showing 2 of 2 groups')
    expect(mocks.mentions).not.toHaveBeenCalled()

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('“Ada Novak”'))!
      .trigger('click')
    await flushPromises()
    expect(mocks.mentions.mock.calls[0]![0]).toMatchObject({
      query: {
        'filter.entity_id': ['person-ada'],
        'filter.name': ['Ada Novak'],
        sort: 'source',
        sort_direction: 'asc',
      },
    })
    expect(wrapper.text()).toContain('Letters')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toMatchObject({
      name: 'document-page',
      params: { libraryId: 'lib', documentId: 'doc', pageId: 'p1' },
    })
  })
})
