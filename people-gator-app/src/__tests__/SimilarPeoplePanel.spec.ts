import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import SimilarPeoplePanel from '@/components/custom/SimilarPeoplePanel.vue'
import type { Face } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'

const people: SimilarPersonCandidate[] = [
  {
    id: 'anna-novakova',
    name: 'Anna Nováková',
    shortDescription: 'Local lecturer and town historian.',
    score: 94,
    nerMentions: 1,
    detections: 1,
    closestMentionDistancePx: 14,
    source: 'page',
    matchSources: [
      { type: 'face-match', distance: 0.06 },
      { type: 'scan-text' },
      { type: 'scan-face' },
    ],
    wikidataId: 'Q42',
    nlcrAuthorityId: 'xx0000000',
    faceId: 'face-01',
    entityKey: 'line-anna:35:48',
    entityLineIndex: 1,
  },
  {
    id: 'marie-dvorakova',
    name: 'Marie Dvořáková',
    score: 81,
    nerMentions: 0,
    detections: 0,
    source: 'database',
    matchSources: [{ type: 'text-search', score: 81 }],
  },
]

const unassignedFace: Face = {
  id: 'face-current',
  embeddingModel: 'face-model',
  personId: null,
  name: 'Unknown person',
  confidence: 91,
  status: 'unassigned',
  position: { left: 0, top: 0, width: 10, height: 10 },
  portrait: '/face-current.jpg',
  portraitLoading: false,
}

const assignedFace: Face = {
  ...unassignedFace,
  personId: 'anna-novakova',
  name: 'Anna Nováková',
  shortDescription: 'Local lecturer and town historian.',
  wikidataId: 'Q42',
  status: 'assigned',
}

describe('SimilarPeoplePanel', () => {
  it('emits page face and entity targets when a candidate is previewed', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: 'anna-novakova',
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAll('[data-slot="item"]')[1]!.classes()).toContain('border-accent')
    await wrapper.get('[aria-label="Preview Anna Nováková on this page"]').trigger('click')

    expect(wrapper.emitted('preview')).toEqual([[people[0]]])
  })

  it('links candidate names to person details', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAllComponents(RouterLinkStub)[0]!.props('to')).toEqual({
      name: 'person-detail',
      params: { personId: 'anna-novakova' },
      query: { origin_matched_face: 'face-01' },
    })
    expect(wrapper.get('p[title="Local lecturer and town historian."]').text()).toBe(
      'Local lecturer and town historian.',
    )
    expect(wrapper.get('p[title="Local lecturer and town historian."]').classes()).toContain(
      'text-xs',
    )
    expect(wrapper.get('[aria-label="Face match cosine distance 0.06"]').text()).toBe('0.06')
    expect(wrapper.get('[aria-label="Found in scanned text"]')).toBeDefined()
    expect(wrapper.get('[aria-label="Found in scanned faces"]')).toBeDefined()
    const textScore = wrapper.get('[aria-label="Text search score 81"] span')
    expect(textScore.text()).toBe('81')
    expect(textScore.classes()).toContain('w-[3ch]')
    expect(wrapper.get('a[href="https://www.wikidata.org/wiki/Q42"]').text()).toContain('Wikidata')
    expect(wrapper.get('a[href*="local_base=aut"]').text()).toContain('NLCR AUT')
  })

  it('constrains and truncates long candidate names', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: [{ ...people[0]!, name: 'A very long person name that must stay inside the card' }],
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    const name = wrapper.get('h4 > span')
    expect(name.classes()).toContain('truncate')
    expect(name.element.parentElement?.classList).toContain('min-w-0')
    expect(wrapper.get('[data-slot="item-content"]').classes()).toContain('overflow-hidden')
  })

  it('switches empty searches between page and face candidates, while text overrides the source', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    if (wrapper.find('button[aria-label="Show filters"]').exists())
      await wrapper.findAll('button[aria-label="Show filters"]').slice(-1)[0]!.trigger('click')
    expect(wrapper.get('[aria-label="Show people on this page"]').attributes('data-state')).toBe(
      'on',
    )
    await wrapper.get('[aria-label="Show people with similar faces"]').trigger('click')
    expect(
      wrapper.get('[aria-label="Show people with similar faces"]').attributes('data-state'),
    ).toBe('on')

    await wrapper.get('[aria-label="Search people"]').setValue('an alias')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(2)
    expect(wrapper.find('[aria-label="Choose candidate source"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="Show filters"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Showing database name and alias matches.')
  })

  it('does not append a loading row while refreshing existing candidates', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
        loading: true,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    const results = wrapper.get('[aria-live="polite"][aria-busy="true"]')
    expect(results.find('[aria-label="Loading similar person"]').exists()).toBe(false)
    expect(results.findAll('[aria-label^="Preview "]')).toHaveLength(2)
  })

  it('shows the selected face as an actionable item above reassignment search', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: assignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAllComponents(RouterLinkStub)[0]!.props('to')).toEqual({
      name: 'person-detail',
      params: { personId: 'anna-novakova' },
      query: { origin_matched_face: 'face-current' },
    })
    const wikidataLink = wrapper.get('a[href="https://www.wikidata.org/wiki/Q42"]')
    expect(wikidataLink.text()).toBe('Wikidata')
    expect(wrapper.findAll('[data-slot="item-footer"]')[0]!.text()).not.toContain('confidence')
    expect(wrapper.get('[data-slot="item-actions"]').text()).toContain('Current')
    expect(wrapper.findAll('[data-slot="item"]')[0]!.classes()).toContain('items-start')
    expect(wrapper.findAll('[data-slot="item-media"]')[0]!.classes()).toContain('self-start')
    const reassignButton = wrapper.get('[aria-label="Reassign to another profile"]')
    // Card actions are icon-only; their names are shown as hover tooltips.
    expect(reassignButton.attributes('data-size')).toBe('icon-xs')
    expect(reassignButton.text()).toBe('')
    expect(reassignButton.element.closest('[data-slot="item-footer"]')).not.toBeNull()
    // View faces stays on the left; the actions are grouped on the right.
    const actions = reassignButton.element.parentElement!
    expect(actions.classList).toContain('ml-auto')
    expect(actions.classList).toContain('justify-end')
    const viewFaces = wrapper.get('button[aria-label*="faces" i]').element
    expect(actions.contains(viewFaces)).toBe(false)
    expect(
      viewFaces.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(wrapper.text()).toContain('Reassign to similar')
    expect(
      wrapper.get('[aria-label="Assigned to Anna Nováková"]').attributes('disabled'),
    ).toBeDefined()
    expect(wrapper.get('[aria-label="Reassign to Marie Dvořáková"]').text()).toBe('Reassign')
    expect(wrapper.get('[aria-label="Reassign to another profile"]')).toBeDefined()
    expect(wrapper.get('[aria-label="Create and assign a new profile"]')).toBeDefined()

    await wrapper.get('[aria-label="Unassign current profile"]').trigger('click')
    expect(wrapper.emitted('unassign')).toHaveLength(1)
  })

  it('does not show load more when all candidates fit', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAll('button').some((button) => button.text() === 'Load more people')).toBe(
      false,
    )
  })

  it('assigns a candidate without previewing it', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Assign')!
      .trigger('click')

    expect(wrapper.emitted('assign')).toEqual([[people[0]]])
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('hides assignment buttons while browsing without a selected face', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: null,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAll('button').some((button) => button.text() === 'Assign')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === 'Reassign')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === 'Assigned')).toBe(false)
  })

  it('creates and assigns a person from blank inline fields', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    await wrapper
      .get('input[placeholder="Search by name or alias"]')
      .setValue('  Max von Gallwitz  ')
    await wrapper.get('button[aria-label="Create and assign a new profile"]').trigger('click')

    const nameField = wrapper.get('[aria-label="New person name"]')
    const descriptionField = wrapper.get('[aria-label="New person short description"]')
    expect(nameField.element.tagName).toBe('H4')
    expect(nameField.text()).toBe('')
    expect(descriptionField.text()).toBe('')
    expect(
      wrapper.get('[aria-label="Create and assign profile"]').attributes('disabled'),
    ).toBeDefined()

    nameField.element.textContent = '  Max von Gallwitz  '
    await nameField.trigger('input')
    descriptionField.element.textContent = 'Prussian field marshal'
    await descriptionField.trigger('input')

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('create')?.[0]?.[0]).toMatchObject({
      id: 'max-von-gallwitz',
      name: 'Max von Gallwitz',
      shortDescription: 'Prussian field marshal',
      detections: 1,
      source: 'page',
    })
  })

  it('requests another result page after revealing the loaded candidates', async () => {
    const initialPeople = [...people, { ...people[1]!, id: 'josef-svoboda', name: 'Josef Svoboda' }]
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: initialPeople,
        selectedFace: unassignedFace,
        viewedPersonId: null,
        hasNextPage: true,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    const loadMore = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more people')!
    await loadMore.trigger('click')

    expect(wrapper.emitted('loadMore')).toEqual([[]])
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(3)

    await wrapper.setProps({ isFetchingNextPage: true })
    expect(loadMore.attributes('disabled')).toBeDefined()
    expect(loadMore.text()).toBe('Loading more')

    await wrapper.setProps({
      people: [...initialPeople, { ...people[1]!, id: 'alena-horakova', name: 'Alena Horakova' }],
      hasNextPage: false,
      isFetchingNextPage: false,
    })
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(4)
    expect(wrapper.findAll('button').some((button) => button.text() === 'Load more people')).toBe(
      false,
    )
  })

  it('progressively reveals long candidate lists', async () => {
    const extendedPeople = [
      ...people,
      { ...people[1]!, id: 'josef-svoboda', name: 'Josef Svoboda' },
      { ...people[1]!, id: 'alena-horakova', name: 'Alena Horáková' },
      { ...people[1]!, id: 'jan-novak', name: 'Jan Novák' },
      { ...people[1]!, id: 'eva-vesela', name: 'Eva Veselá' },
      { ...people[1]!, id: 'petr-cerny', name: 'Petr Černý' },
    ]
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: extendedPeople,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.find('[data-slot="scroll-area-viewport"]').exists()).toBe(true)
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(3)
    const loadMoreItem = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more people')!
    expect(loadMoreItem.attributes('data-slot')).toBe('button')
    expect(loadMoreItem.attributes('data-variant')).toBe('link')
    expect(loadMoreItem.findAll('svg.lucide-chevrons-down')).toHaveLength(1)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more people')!
      .trigger('click')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(6)
    expect(wrapper.get('[aria-label="Preview Alena Horáková on this page"]')).toBeDefined()

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more people')!
      .trigger('click')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(7)
    expect(wrapper.get('[aria-label="Preview Petr Černý on this page"]')).toBeDefined()
    expect(wrapper.findAll('button').some((button) => button.text() === 'Load more people')).toBe(
      false,
    )
  })

  it('loads the next page when the load-more link enters the scroll viewport', async () => {
    const extendedPeople = [
      ...people,
      { ...people[1]!, id: 'josef-svoboda', name: 'Josef Svoboda' },
      { ...people[1]!, id: 'alena-horakova', name: 'Alena Horáková' },
      { ...people[1]!, id: 'jan-novak', name: 'Jan Novák' },
    ]
    let intersect: IntersectionObserverCallback | undefined

    vi.useFakeTimers()
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn<() => void>(),
        removeEventListener: vi.fn<() => void>(),
      }),
    )
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: IntersectionObserverCallback) {
          intersect = callback
        }

        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )

    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: extendedPeople,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    try {
      await wrapper.vm.$nextTick()
      await Promise.resolve()
      intersect?.(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      )
      await wrapper.vm.$nextTick()

      expect(wrapper.get('button[disabled]').text()).toBe('Loading more')

      await vi.advanceTimersByTimeAsync(150)
      expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(5)
      expect(wrapper.findAll('button').some((button) => button.text() === 'Load more people')).toBe(
        false,
      )
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })

  it('reveals the selected person and scrolls only the candidate viewport', async () => {
    const extendedPeople = [
      ...people,
      { ...people[1]!, id: 'josef-svoboda', name: 'Josef Svoboda' },
      { ...people[1]!, id: 'alena-horakova', name: 'Alena Horáková' },
      { ...people[1]!, id: 'jan-novak', name: 'Jan Novák' },
    ]
    const scrollBy = vi.fn()
    const originalScrollIntoView = HTMLElement.prototype.scrollBy
    Object.defineProperty(HTMLElement.prototype, 'scrollBy', {
      configurable: true,
      value: scrollBy,
    })

    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: extendedPeople,
        selectedFace: unassignedFace,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    try {
      expect(wrapper.find('[aria-label="Preview Jan Novák on this page"]').exists()).toBe(false)

      await wrapper.setProps({ viewedPersonId: 'jan-novak' })
      await wrapper.vm.$nextTick()

      expect(wrapper.get('[aria-label="Preview Jan Novák on this page"]')).toBeDefined()
      expect(scrollBy).toHaveBeenCalledWith({ behavior: 'smooth', top: 0 })
    } finally {
      wrapper.unmount()
      if (originalScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, 'scrollBy', {
          configurable: true,
          value: originalScrollIntoView,
        })
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, 'scrollBy')
      }
    }
  })
})
