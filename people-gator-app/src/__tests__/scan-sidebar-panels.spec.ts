import { mount, RouterLinkStub } from '@vue/test-utils'
import { h } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ScanPeoplePanel from '@/components/custom/ScanPeoplePanel.vue'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
import type { Face } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'

vi.mock('@/composables/object-url', () => ({ useObjectUrl: () => ({ value: '' }) }))
vi.mock('@/query/faces', () => ({
  useFaceAlignedCropQuery: () => ({ data: { value: undefined }, isPending: { value: false } }),
}))

const face: Face = {
  id: 'face',
  personId: 'person',
  name: 'Lina',
  embeddingModel: 'model',
  confidence: 99,
  status: 'assigned',
  position: { left: 10, top: 10, width: 20, height: 20 },
  portrait: '',
  portraitLoading: false,
  linkState: 'manual',
}
const stubs = { RouterLink: RouterLinkStub, IdentityFacePreview: true, LoadableImage: true }
const labels = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findAll('button[aria-label]').map((button) => button.attributes('aria-label')!)

describe('selected face card (#103)', () => {
  it('orders actions and keeps Search apart from Link/Reassign', async () => {
    const wrapper = mount(SelectedFaceItem, {
      props: { face, canDelete: true },
      // The page passes the inline Verify control through this slot.
      slots: { actions: () => h('button', { 'aria-label': 'Verify this link' }) },
      global: { stubs },
    })
    expect(labels(wrapper)).toEqual([
      'Search people by this face',
      'Reassign to another profile',
      'Create and assign a new profile',
      'Unassign current profile',
      'Verify this link',
      'Delete detection',
    ])
    await wrapper.get('[aria-label="Search people by this face"]').trigger('click')
    await wrapper.get('[aria-label="Reassign to another profile"]').trigger('click')
    expect(wrapper.emitted('searchFace')).toHaveLength(1)
    expect(wrapper.emitted('findProfile')).toHaveLength(1)
  })

  it('is compact: face with a gallery button, state, and left-aligned actions', () => {
    const wrapper = mount(SelectedFaceItem, {
      props: {
        face: { ...face, shortDescription: 'Synthetic archivist', wikidataId: 'Q1' },
        canDelete: true,
      },
      global: { stubs },
    })
    const preview = wrapper.getComponent({ name: 'IdentityFacePreview' })
    expect(preview.props()).toEqual({ personId: 'person', name: 'Lina' })
    // The gallery button sits over the thumbnail, beside the name and state.
    expect(wrapper.get('[data-slot="item-media"]').element.contains(preview.element)).toBe(true)
    expect(wrapper.text()).toContain('Lina')
    expect(wrapper.text()).not.toContain('Synthetic archivist')
    expect(wrapper.text()).not.toContain('Wikidata')
    const actions = wrapper.get('[aria-label="Search people by this face"]').element.closest('div')!
    expect(actions.className).toContain('justify-start')
    expect(actions.className).not.toContain('ml-auto')
  })

  it('states an unassigned face truthfully and respects permissions', async () => {
    const wrapper = mount(SelectedFaceItem, {
      props: {
        face: { ...face, personId: null, linkState: null, embeddingModel: undefined },
        canAnnotate: false,
      },
      slots: { actions: () => h('button', { 'aria-label': 'Verify this link' }) },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('Unassigned face')
    // The assignment-state badge states it; no person info is repeated.
    expect(wrapper.get('[data-face-status-badge]').text()).toBe('Unassigned')
    // Browsing keeps Search; it needs a face embedding.
    expect(labels(wrapper)).toEqual(['Search people by this face'])
    expect(
      wrapper.get('[aria-label="Search people by this face"]').attributes('disabled'),
    ).toBeDefined()
    await wrapper.setProps({ canAnnotate: true })
    expect(labels(wrapper)).toContain('Link to an existing profile')
  })
})

describe('People panel (#103)', () => {
  const candidate: SimilarPersonCandidate = {
    id: 'ada',
    name: 'Ada',
    nerMentions: 0,
    detections: 0,
    source: 'database',
  }
  function panel(props: Record<string, unknown> = {}) {
    return mount(ScanPeoplePanel, {
      props: {
        people: [candidate],
        scored: false,
        loading: false,
        totalCount: 1,
        hasNextPage: false,
        isFetching: false,
        searchFaceId: null,
        selectedFace: null,
        viewedPersonId: null,
        text: '',
        scope: 'all',
        order: 'context',
        loadMore: vi.fn(() => Promise.resolve()),
        retry: vi.fn(),
        ...props,
      },
      global: { stubs: { ...stubs, SimilarPersonItem: false } },
    })
  }

  it('keeps face, scope, result count and Search in one input group', async () => {
    const wrapper = panel({ searchFaceId: 'face-a', scored: true, order: 'relevance' })
    const group = wrapper.get('[data-slot="input-group"]')
    // Attachments sit on their own row below the text, above the controls.
    const rows = group.findAll('[data-align="block-end"]')
    expect(rows).toHaveLength(2)
    const [context, addon] = rows as [(typeof rows)[0], (typeof rows)[0]]
    expect(context.attributes('aria-label')).toBe('Search context')
    expect(context.find('[data-search-face][data-face-id="face-a"]').exists()).toBe(true)
    expect(addon.find('[data-search-face]').exists()).toBe(false)
    expect(addon.get('button').attributes('aria-label')).toBe('Add search context')
    expect(addon.get('[aria-label="Scope: All people"]').text()).toBe('All people')
    expect(addon.get('[role="status"]').text()).toBe('1 result')
    await context.get('[aria-label="Remove search face"]').trigger('click')
    expect(wrapper.emitted('removeFace')).toHaveLength(1)
    // Sorting sits beside the Results heading, not in the search group.
    expect(group.findComponent({ name: 'SortSelect' }).exists()).toBe(false)
    expect(wrapper.get('#people-results-title').text()).toBe('Results')
    const sort = wrapper.findComponent({ name: 'SortSelect' })
    expect(sort.props('strategies')).toContainEqual(
      expect.objectContaining({ value: 'relevance', label: 'Similarity' }),
    )
    await wrapper.setProps({ scored: false, order: 'context' })
    expect(sort.props('strategies').map((option: { value: string }) => option.value)).toEqual([
      'context',
      'name',
      'last_touched_at',
    ])
  })

  it("offers the attached face's embedding models beside the scope", async () => {
    const wrapper = panel()
    expect(wrapper.find('[aria-label^="Face model:"]').exists()).toBe(false)
    await wrapper.setProps({
      searchFaceId: 'face-a',
      faceModels: ['model-a', 'model-b'],
      faceModel: 'model-b',
    })
    const [, controls] = wrapper.findAll('[data-align="block-end"]')
    const trigger = controls!.get('[aria-label="Face model: model-b"]')
    expect(trigger.text()).toBe('model-b')
    // It sits in the controls row after the scope, like the scope menu.
    const labels = controls!.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))
    expect(labels.indexOf('Face model: model-b')).toBe(labels.indexOf('Scope: All people') + 1)
  })

  it('keeps an empty, fixed-height attachment row without context', () => {
    const wrapper = panel()
    const [context] = wrapper.findAll('[data-align="block-end"]')
    expect(context!.attributes('aria-label')).toBe('Search context')
    expect(context!.classes()).toContain('h-9')
    expect(context!.find('[data-search-face]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Add search context"]').exists()).toBe(true)
  })

  it('applies name text after a typing pause, or at once on Enter or Search', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = panel({ text: 'Ada' })
      const field = wrapper.get('textarea[aria-label="Search people"]')
      const submit = wrapper.get('button[type="submit"]')
      expect(submit.text()).toBe('Search')
      expect(submit.attributes('disabled')).toBeDefined()
      await field.setValue('Nov')
      await field.setValue('Novak')
      vi.advanceTimersByTime(299)
      expect(wrapper.emitted('update:text')).toBeUndefined()
      // One search after the pause, with the latest text.
      vi.advanceTimersByTime(1)
      expect(wrapper.emitted('update:text')).toEqual([['Novak']])
      await wrapper.setProps({ text: 'Novak' })
      await field.setValue(' Lina ')
      await field.trigger('keydown', { key: 'Enter', shiftKey: true })
      expect(wrapper.emitted('update:text')).toHaveLength(1)
      await field.trigger('keydown', { key: 'Enter' })
      expect(wrapper.emitted('update:text')).toEqual([['Novak'], ['Lina']])
      await wrapper.setProps({ text: 'Lina' })
      await field.setValue('Ida')
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('update:text')).toEqual([['Novak'], ['Lina'], ['Ida']])
      // The pending pause finds nothing left to apply.
      await wrapper.setProps({ text: 'Ida' })
      vi.advanceTimersByTime(300)
      expect(wrapper.emitted('update:text')).toHaveLength(3)
      // A restored or cleared applied text replaces the draft.
      await wrapper.setProps({ text: '' })
      expect((field.element as HTMLTextAreaElement).value).toBe('')
    } finally {
      vi.useRealTimers()
    }
  })

  it('marks page text, page faces and document membership with one icon each', () => {
    const wrapper = panel({
      people: [
        {
          ...candidate,
          matchSources: [{ type: 'scan-text' }, { type: 'scan-face' }, { type: 'in-document' }],
        },
      ],
    })
    const badges = wrapper.get('[aria-label="Match sources"]')
    expect(badges.findAll('[aria-label]').map((badge) => badge.attributes('aria-label'))).toEqual([
      'Mentioned on this page',
      'Face on this page',
      'In this document',
    ])
    expect(badges.findAll('svg')).toHaveLength(3)
    expect(badges.find('.lucide-scan').exists()).toBe(false)
  })

  it('shows more faces from the same gallery button over the result portrait', () => {
    const wrapper = panel()
    const media = wrapper.get('[data-slot="item-media"]')
    expect(media.findComponent({ name: 'IdentityFacePreview' }).props()).toEqual({
      personId: 'ada',
      name: 'Ada',
    })
    // No separate labelled button remains in the card footer.
    expect(wrapper.findAllComponents({ name: 'IdentityFacePreview' })).toHaveLength(1)
    // With nothing to link or assign, the card has no empty footer.
    expect(wrapper.find('[data-slot="item-footer"]').exists()).toBe(false)
  })

  it('assigns only a selected face, separately from preview', async () => {
    const wrapper = panel()
    expect(wrapper.find('button[aria-label^="Assign to"]').exists()).toBe(false)
    await wrapper.setProps({ selectedFace: { ...face, personId: null } })
    await wrapper.get('button[aria-label="Preview Ada on this page"]').trigger('click')
    expect(wrapper.emitted('preview')).toHaveLength(1)
    expect(wrapper.emitted('assign')).toBeUndefined()
    await wrapper.get('button[aria-label="Assign to Ada"]').trigger('click')
    expect(wrapper.emitted('assign')).toHaveLength(1)
  })
})
