import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SimilarPeoplePanel from '@/components/custom/SimilarPeoplePanel.vue'
import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'

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
  },
]

describe('SimilarPeoplePanel', () => {
  it('emits page face and entity targets when a candidate is previewed', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: 'anna-novakova' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.findAll('[data-slot="item"]')[0]!.classes()).toContain('border-accent')
    await wrapper.get('[aria-label="Preview Anna Nováková on this page"]').trigger('click')

    expect(wrapper.emitted('preview')).toEqual([[people[0]]])
  })

  it('links candidate names to person details', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.findAllComponents(RouterLinkStub)[0]!.props('to')).toEqual({
      name: 'person-detail',
      params: { personId: 'anna-novakova' },
    })
    expect(wrapper.get('p[title="Local lecturer and town historian."]').classes()).toContain(
      'text-xs',
    )
    expect(wrapper.get('[data-slot="item-footer"]').text()).toContain('sim 94% · dist 14 px')
  })

  it('constrains and truncates long candidate names', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: {
        people: [{ ...people[0]!, name: 'A very long person name that must stay inside the card' }],
        assignedPersonId: null,
        viewedPersonId: null,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    const name = wrapper.get('h4 > span')
    expect(name.classes()).toContain('truncate')
    expect(name.element.parentElement?.classList).toContain('min-w-0')
    expect(wrapper.get('[data-slot="item-content"]').classes()).toContain('overflow-hidden')
  })

  it('keeps server alias matches visible and filters by actual page/database source', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper.get('[aria-label="Search people"]').setValue('an alias')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(2)

    await wrapper.get('[aria-label="Database"]').trigger('click')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(1)
    expect(wrapper.get('[aria-label="Preview Marie Dvořáková on this page"]')).toBeDefined()

    await wrapper.get('[aria-label="On this page"]').trigger('click')
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(1)
    expect(wrapper.get('[aria-label="Preview Anna Nováková on this page"]')).toBeDefined()
  })

  it('does not show load more when all candidates fit', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.findAll('button').some((button) => button.text() === 'Load more people')).toBe(
      false,
    )
  })

  it('assigns a candidate without previewing it', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Assign')!
      .trigger('click')

    expect(wrapper.emitted('assign')).toEqual([[people[0]]])
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('creates a person using the active search text', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper
      .get('input[placeholder="Search by name or alias"]')
      .setValue('  Max von Gallwitz  ')
    await wrapper.get('button[aria-label="Add person"]').trigger('click')

    expect((wrapper.get('form input').element as HTMLInputElement).value).toBe('Max von Gallwitz')

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('create')?.[0]?.[0]).toMatchObject({
      id: 'max-von-gallwitz',
      name: 'Max von Gallwitz',
      detections: 1,
      source: 'page',
    })
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
      props: { people: extendedPeople, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.find('[data-slot="scroll-area-viewport"]').exists()).toBe(false)
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(3)
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
})
