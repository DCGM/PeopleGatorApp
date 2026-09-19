import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import type { PersonDiscoveryFace } from '@/components/custom/person-detail.types'
import { personDiscoverySignals } from '@/query/person-discovery'

function face(id: string, score = 93): PersonDiscoveryFace {
  return {
    id,
    portrait: '',
    portraitLoading: false,
    score,
    assignedEntityId: null,
    library: 'nlp',
    documentId: 'document-1',
    pageId: `page-${id}`,
    pageLabel: `page-${id}`,
  }
}

describe('PersonDiscoveryPanel', () => {
  it('builds a combined person search from face and name signals', () => {
    expect(personDiscoverySignals(['face-1', 'face-2'], '  Ada Lovelace  ')).toEqual({
      q: ['Ada Lovelace'],
      q_face_id: ['face-1', 'face-2'],
      entity_type: ['person'],
      limit: 40,
    })
  })

  it('selects an item and emits a batch assignment from the action toolbar', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-match')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 2,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.text()).toContain('93%')
    expect(wrapper.text()).toContain('Unassigned')
    expect(wrapper.findAll('[data-face-selection-target="control"]')).toHaveLength(0)
    await wrapper.get('[aria-label="Select only face face-match"]').trigger('click')

    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
    expect(wrapper.get('[role="toolbar"]').classes()).toContain('fixed')
    expect(wrapper.get('[data-slot="item"]').classes()).toContain('border-secondary')
    expect(wrapper.findAll('[data-face-selection-target="control"]')).toHaveLength(1)
    expect(wrapper.get('[data-face-selection-target="control"]').classes()).toContain('bg-accent')
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Assign to Ada Lovelace'))!
      .trigger('click')

    expect(wrapper.emitted('assignFaces')).toEqual([[['face-match']]])
  })

  it('shift-selects the inclusive range from the selection anchor', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-1'), face('face-2'), face('face-3')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper.get('[aria-label="Select only face face-1"]').trigger('click')
    await wrapper.get('[aria-label="Select only face face-3"]').trigger('click', { shiftKey: true })

    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
    expect(
      wrapper.findAll('[data-face-selection-target="card"][aria-pressed="true"]'),
    ).toHaveLength(3)
  })

  it('uses normal click for a single selection and modifier or circle clicks for additive selection', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-1'), face('face-2'), face('face-3')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper.get('[aria-label="Select only face face-1"]').trigger('click')
    await wrapper.get('[aria-label="Select only face face-2"]').trigger('click')
    expect(
      wrapper.findAll('[data-face-selection-target="card"][aria-pressed="true"]'),
    ).toHaveLength(1)

    await wrapper.get('[aria-label="Select only face face-3"]').trigger('click', { ctrlKey: true })
    expect(
      wrapper.findAll('[data-face-selection-target="card"][aria-pressed="true"]'),
    ).toHaveLength(2)

    await wrapper.get('[aria-label="Add face face-1 to selection"]').trigger('click')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
  })

  it('uses a chevron link to open the matched face on its source page', () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-match')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
      name: 'document-page',
      params: { libraryId: 'nlp', documentId: 'document-1', pageId: 'page-face-match' },
      query: { person: 'face-match' },
    })
  })

  it('shows the assigned person name with the page-view face status treatment', () => {
    const assignedFace = {
      ...face('face-match'),
      assignedEntityId: 'person-1',
      assignedEntityName: 'Grace Hopper',
    }
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [assignedFace],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    const status = wrapper.get('p.text-emerald-700')
    expect(status.text()).toContain('Grace Hopper')
    expect(status.text()).toContain('sim 93%')
    expect(status.find('.lucide-link').exists()).toBe(true)
    expect(status.get('b').classes()).toContain('truncate')
  })

  it('links similar people to their detail records', () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [],
        people: [
          {
            id: 'ada-king',
            name: 'Ada King',
            shortDescription: 'Mathematician and writer',
            aliases: ['Augusta Ada King'],
            portrait: '',
            portraitLoading: false,
          },
        ],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
        searchTerm: 'Ada Lovelace',
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.findAllComponents(RouterLinkStub)[0]!.props('to')).toEqual({
      name: 'person-detail',
      params: { personId: 'ada-king' },
    })
    expect(wrapper.text()).toContain('Face')
    expect(wrapper.text()).toContain('Name')
  })
})
