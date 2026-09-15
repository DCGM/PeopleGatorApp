import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SimilarPeoplePanel from '@/components/custom/SimilarPeoplePanel.vue'
import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'

const people: SimilarPersonCandidate[] = [
  {
    id: 'anna-novakova',
    name: 'Anna Nováková',
    score: 94,
    nerMentions: 1,
    detections: 1,
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
    })

    expect(wrapper.findAll('[data-slot="item"]')[0]!.classes()).toContain('border-accent')
    await wrapper.get('[aria-label="Preview Anna Nováková on this page"]').trigger('click')

    expect(wrapper.emitted('preview')).toEqual([[people[0]]])
  })

  it('opens a person only from the candidate name', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
    })

    await wrapper.get('[aria-label="Open Anna Nováková"]').trigger('click')

    expect(wrapper.emitted('open-person')).toEqual([['anna-novakova']])
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('creates a person using the active search text', async () => {
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people, assignedPersonId: null, viewedPersonId: null },
    })

    await wrapper.get('input[placeholder="Search people"]').setValue('Max von Gallwitz')
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Add'))!
      .trigger('click')
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
    ]
    const wrapper = mount(SimilarPeoplePanel, {
      props: { people: paginatedPeople, assignedPersonId: null, viewedPersonId: null },
    })

    expect(wrapper.find('[aria-label="Preview Alena Horáková on this page"]').exists()).toBe(false)
    await wrapper.get('[aria-label="Next people page"]').trigger('click')

    expect(wrapper.get('[aria-label="Preview Alena Horáková on this page"]')).toBeDefined()
    expect(wrapper.find('[aria-label="Preview Anna Nováková on this page"]').exists()).toBe(false)
  })
})
