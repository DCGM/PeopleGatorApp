import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { computed, defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import PersonMentionEntry from '@/components/custom/PersonMentionEntry.vue'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
import { useRouteQueryPatch } from '@/composables/route-query'
import { SCAN_SELECTED_MENTION } from '@/viewmodels/scan-sidebar'
import type { PersonMention } from '@/viewmodels/person-detail.types'
import type { Face } from '@/viewmodels/document-workspace.types'

const page = { template: '<div />' }
function scanRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: page },
      {
        name: 'document-page',
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        component: page,
      },
    ],
  })
}

describe('scan sidebar navigation (#103)', () => {
  it('keeps changes still in flight when a later tick patches the query', async () => {
    const router = scanRouter()
    await router.push('/?keep=1')
    let patch!: ReturnType<typeof useRouteQueryPatch>
    mount(
      defineComponent({
        setup() {
          patch = useRouteQueryPatch()
          return () => h('div')
        },
      }),
      { global: { plugins: [router] } },
    )
    patch({ panel: 'faces' }, 'push')
    await Promise.resolve()
    // The first navigation has not committed when the next change arrives.
    patch({ person: 'face-a' })
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      keep: '1',
      panel: 'faces',
      person: 'face-a',
    })
  })

  it('opens another page from a scan mention with the same sidebar settings', async () => {
    const router = scanRouter()
    await router.push({
      name: 'document-page',
      params: { libraryId: 'lib', documentId: 'doc', pageId: 'one' },
      query: {
        panel: 'mentions',
        mention_scope: 'document',
        page_link_state: 'manual',
        person: 'f',
        line: 'l1',
      },
    })
    const wrapper = mount(PersonMentionEntry, {
      props: {
        linkStates: ['manual'],
        mention: {
          id: 'm1',
          excerpt: 'Ada wrote.',
          matchedText: 'Ada',
          library: 'lib',
          documentId: 'doc',
          pageId: 'two',
          pageLabel: 'two',
          metadata: { entity_id: 'ada' },
        } as unknown as PersonMention,
      },
      global: {
        plugins: [router],
        stubs: { RouterLink: RouterLinkStub },
        provide: { [SCAN_SELECTED_MENTION as symbol]: computed(() => 'm1') },
      },
    })
    // Only the mention text (context and name) selects; the page is plain text.
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links).toHaveLength(1)
    expect(links[0]!.attributes('aria-label')).toBe('Select mention: Ada wrote.')
    expect(links[0]!.attributes('aria-current')).toBe('true')
    expect(wrapper.text()).toContain('two')
    expect(wrapper.find('[data-mention-selected]').exists()).toBe(true)
    // The transcription's look: a muted line and the name selected in blue.
    expect(links[0]!.classes()).toContain('bg-muted')
    expect(links[0]!.get('mark').classes()).toEqual(
      expect.arrayContaining(['bg-accent/20', 'outline-1', 'outline-accent']),
    )
    const linkQuery = () =>
      (wrapper.getComponent(RouterLinkStub).props('to') as { query: Record<string, unknown> }).query
    // Another page keeps the sidebar's settings; the evidence filter stays behind (#109).
    expect(wrapper.getComponent(RouterLinkStub).props('to')).toMatchObject({
      params: { pageId: 'two' },
      query: {
        panel: 'mentions',
        mention_scope: 'document',
        person: undefined,
        line: undefined,
        mention: 'm1',
        selectedPerson: 'ada',
      },
    })
    expect(linkQuery()).not.toHaveProperty('page_link_state')
    // A mention on the current page keeps every setting of this view.
    await wrapper.setProps({ mention: { ...wrapper.props('mention'), pageId: 'one' } })
    expect(linkQuery()).toMatchObject({
      page_link_state: 'manual',
      panel: 'mentions',
      mention: 'm1',
    })
  })

  it('cancels a new-person draft on Escape without closing the card', async () => {
    const face = {
      id: 'f',
      personId: null,
      name: 'x',
      position: {},
      linkState: null,
    } as unknown as Face
    const outer = vi.fn()
    const wrapper = mount(
      defineComponent({
        setup: () => () =>
          h('div', { onKeydown: outer }, [h(SelectedFaceItem, { face, canDelete: false })]),
      }),
      {
        global: {
          stubs: { RouterLink: RouterLinkStub, IdentityFacePreview: true, LoadableImage: true },
        },
      },
    )
    await wrapper.get('[aria-label="Create and assign a new profile"]').trigger('click')
    await nextTick()
    await wrapper.get('form').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(outer).not.toHaveBeenCalled()
    // Without a draft, Escape still reaches the card to dismiss it.
    await wrapper.getComponent(SelectedFaceItem).trigger('keydown', { key: 'Escape' })
    expect(outer).toHaveBeenCalledTimes(1)
  })
})
