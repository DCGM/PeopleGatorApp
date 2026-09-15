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

  it('shows disabled pagination when all candidates fit on one page', () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    const paginationButtons = wrapper.findAll('[data-slot="pagination"] button')
    expect(paginationButtons).toHaveLength(3)
    expect(paginationButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(
      true,
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
      .get('input[placeholder="Search by name, WikiData ID, NACR ID"]')
      .setValue('  Max von Gallwitz  ')
    await wrapper.get('button[aria-label="Add person"]').trigger('click')

    expect(wrapper.get('form input').element.value).toBe('Max von Gallwitz')

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('create')?.[0]?.[0]).toMatchObject({
      id: 'max-von-gallwitz',
      name: 'Max von Gallwitz',
      detections: 1,
      source: 'page',
    })
  })

  it('paginates long candidate lists', async () => {
    const paginatedPeople = [
      ...people,
      { ...people[1]!, id: 'josef-svoboda', name: 'Josef Svoboda' },
      { ...people[1]!, id: 'alena-horakova', name: 'Alena Horáková' },
      { ...people[1]!, id: 'jan-novak', name: 'Jan Novák' },
      { ...people[1]!, id: 'eva-vesela', name: 'Eva Veselá' },
      { ...people[1]!, id: 'petr-cerny', name: 'Petr Černý' },
    ]
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people: paginatedPeople, assignedPersonId: null, viewedPersonId: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.find('[data-slot="scroll-area-viewport"]').exists()).toBe(false)
    expect(wrapper.findAll('[aria-label^="Preview "]')).toHaveLength(3)
    expect(wrapper.findAll('[data-slot="pagination"] button')).toHaveLength(3)
    await wrapper.get('[aria-label="Next people page"]').trigger('click')
    expect(wrapper.get('[aria-label="Preview Alena Horáková on this page"]')).toBeDefined()

    await wrapper.get('[aria-label="Next people page"]').trigger('click')
    expect(wrapper.get('[aria-label="Preview Petr Černý on this page"]')).toBeDefined()

    await wrapper.get('[aria-label="Previous people page"]').trigger('click')
    expect(wrapper.get('[aria-label="Preview Alena Horáková on this page"]')).toBeDefined()

    await wrapper.get('[aria-label="First people page"]').trigger('click')
    expect(wrapper.get('[aria-label="Preview Anna Nováková on this page"]')).toBeDefined()
  })
})
