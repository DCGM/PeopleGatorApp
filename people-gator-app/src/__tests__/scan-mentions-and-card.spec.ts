import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import type { Face, MentionCardTarget } from '@/viewmodels/document-workspace.types'

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

  it('shows the selected face card without a Current badge', async () => {
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
    // The floating card can be dismissed with its own X button.
    await wrapper.get('button[aria-label="Close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  describe('selected mention card (#176)', () => {
    const target = (fields: Partial<MentionCardTarget> = {}): MentionCardTarget => ({
      ids: ['m1'],
      texts: ['Jan Bulk'],
      personId: 'jan',
      name: 'Jan Bulk',
      thumbnailFaceId: null,
      mixed: false,
      anyLinked: true,
      anyUnverified: true,
      linkState: 'automatic',
      verifiedBy: null,
      verifiedAt: null,
      ...fields,
    })
    const mountCard = (mentions: MentionCardTarget, props: Record<string, unknown> = {}) =>
      mount(SelectedFaceItem, {
        props: { mentions, canDelete: true, ...props },
        slots: { actions: () => h('button', { 'aria-label': 'Verify this link' }) },
        global: {
          stubs: { RouterLink: RouterLinkStub, IdentityFacePreview: true, PersonPortrait: true },
        },
      })
    const labels = (wrapper: ReturnType<typeof mountCard>) =>
      wrapper.findAll('button[aria-label]').map((button) => button.attributes('aria-label'))

    it('uses the face card layout and actions for one linked mention', async () => {
      const wrapper = mountCard(target())
      expect(labels(wrapper)).toEqual([
        'Search people by this name',
        'Reassign to another profile',
        'Create and assign a new profile',
        'Unassign current profile',
        'Verify this link',
        'Delete mention',
        'Close',
      ])
      expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
        name: 'person-detail',
        params: { personId: 'jan' },
        query: {},
      })
      expect(wrapper.text()).toContain('“Jan Bulk”')
      expect(wrapper.findComponent({ name: 'EntityLinkStateBadge' }).exists()).toBe(true)
      for (const [label, event] of [
        ['Search people by this name', 'searchFace'],
        ['Reassign to another profile', 'findProfile'],
        ['Unassign current profile', 'unassign'],
        ['Delete mention', 'delete'],
      ] as const) {
        await wrapper.get(`[aria-label="${label}"]`).trigger('click')
        expect(wrapper.emitted(event)).toHaveLength(1)
      }
    })

    it('counts a mixed selection and names its texts', () => {
      const wrapper = mountCard(
        target({
          ids: ['m1', 'm2', 'm3'],
          texts: ['Jan Bulk', 'J. Bulk'],
          personId: null,
          mixed: true,
        }),
      )
      expect(wrapper.text()).toContain('Several people')
      expect(wrapper.text()).toContain('3 mentions · “Jan Bulk”, “J. Bulk”')
      expect(wrapper.findComponent({ name: 'EntityLinkStateBadge' }).exists()).toBe(false)
      expect(labels(wrapper)).toContain('Search people by these names')
      expect(labels(wrapper)).toContain('Delete mentions')
    })

    it('links unlinked mentions and creates a person pre-filled with the text', async () => {
      const wrapper = mountCard(
        target({
          ids: ['m1', 'm2'],
          personId: null,
          anyLinked: false,
          anyUnverified: false,
          linkState: null,
        }),
      )
      expect(wrapper.text()).toContain('Unlinked mentions')
      expect(labels(wrapper)).not.toContain('Unassign current profile')
      expect(labels(wrapper)).toContain('Link to an existing profile')
      await wrapper.get('[aria-label="Create and assign a new profile"]').trigger('click')
      expect(wrapper.get('[aria-label="New person name"]').text()).toBe('Jan Bulk')
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('createProfile')).toEqual([
        [{ name: 'Jan Bulk', shortDescription: undefined }],
      ])
    })

    it('hides annotation and delete actions without permission', () => {
      const wrapper = mountCard(target(), { canAnnotate: false, canDelete: false })
      expect(labels(wrapper)).toEqual(['Search people by this name', 'Close'])
    })
  })
})
