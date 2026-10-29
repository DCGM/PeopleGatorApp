import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@vueuse/core', async (original) => {
  const { ref } = await import('vue')
  return {
    ...(await original<typeof import('@vueuse/core')>()),
    useElementSize: () => ({ width: ref(1104), height: ref(0) }),
  }
})

import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import type { PersonDiscoveryFace } from '@/viewmodels/person-detail.types'
import { personDiscoverySignals } from '@/viewmodels/person-discovery'

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
    pageUrl: `https://archive.example/other-library/${id}`,
    pageLabel: `page-${id}`,
  }
}

describe('PersonDiscoveryPanel', () => {
  it('builds compact entity queries with canonical annotation choices', () => {
    expect(
      personDiscoverySignals('person-1', 'face-model', '  Extra text  ', ['name', 'faces']),
    ).toEqual({
      'query.entity_id': 'person-1',
      'query.entity_annotations': ['faces', 'name'],
      'query.text': ['Extra text'],
      'query.face_embedding_model': 'face-model',
      limit: 40,
    })
    expect(personDiscoverySignals('person-1', null, '')).toEqual({
      'query.entity_id': 'person-1',
      'query.entity_annotations': ['faces', 'aliases', 'name'],
      limit: 40,
    })
  })

  it('selects with the dedicated control and emits a batch assignment', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-match')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 2,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    const archive = wrapper.get('a[target="_blank"]')
    expect(archive.text()).toBe('NDK')
    expect(archive.attributes('title')).toBe('Digitální knihovna')
    expect(archive.classes()).toEqual(expect.arrayContaining(['absolute', 'left-3', 'top-3']))
    expect(archive.attributes('href')).toBe('https://archive.example/other-library/face-match')
    expect(wrapper.find('a a').exists()).toBe(false)
    await archive.trigger('click')
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
    expect(wrapper.emitted('assignFaces')).toBeUndefined()
    expect(wrapper.text()).toContain('93%')
    expect(wrapper.text()).toContain('Unassigned')
    expect(wrapper.findAll('[data-face-selection-target="control"]')).toHaveLength(1)
    await wrapper.get('[aria-label="Select face face-match for assignment"]').trigger('click')

    await archive.trigger('click')
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
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    await wrapper.get('[aria-label="Select face face-1 for assignment"]').trigger('click')
    await wrapper
      .get('[aria-label="Select face face-3 for assignment"]')
      .trigger('click', { shiftKey: true })

    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
    expect(
      wrapper.findAll('[data-face-selection-target="control"][aria-pressed="true"]'),
    ).toHaveLength(3)
  })

  it('shift-selects a range when clicking the face cards in selection mode', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-1'), face('face-2'), face('face-3')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    await wrapper.get('[aria-label="Select face face-1 for assignment"]').trigger('click')
    await wrapper
      .get('[aria-label="Add face face-3 to selection"]')
      .trigger('click', { shiftKey: true })

    expect(wrapper.get('[role="toolbar"]').text()).toContain('3 faces selected')
    expect(
      wrapper.findAll('[data-face-selection-target="control"][aria-pressed="true"]'),
    ).toHaveLength(3)
  })

  it('makes face clicks additive once assignment selection is enabled', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-1'), face('face-2'), face('face-3')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(
      wrapper.get('[aria-label="Open face face-1 on its source document"]').attributes('href'),
    ).toBeUndefined()

    await wrapper.get('[aria-label="Select face face-1 for assignment"]').trigger('click')
    expect(wrapper.find('[aria-label="Open face face-2 on its source document"]').exists()).toBe(
      false,
    )

    await wrapper.get('[aria-label="Add face face-2 to selection"]').trigger('click')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('2 faces selected')

    await wrapper.get('[aria-label="Face face-1 is selected"]').trigger('click')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('2 faces selected')

    await wrapper.get('[aria-label="Remove face face-1 from assignment"]').trigger('click')
    expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
  })

  it('uses a chevron link to open the matched face on its source page', () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [face('face-match')],
        people: [],
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
      name: 'document-page',
      params: { libraryId: 'nlp', documentId: 'document-1', pageId: 'page-face-match' },
      query: { person: 'face-match', origin_matched_face: 'face-match' },
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
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
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
            textMatch: true,
            matchedFaceIds: ['matched-face'],
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
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    expect(wrapper.findAllComponents(RouterLinkStub)[0]!.props('to')).toEqual({
      name: 'person-detail',
      params: { personId: 'ada-king' },
      query: { origin_matched_face: ['matched-face'] },
    })
    expect(wrapper.text()).toContain('Face')
    expect(wrapper.findAll('[data-slot=badge]').map((badge) => badge.text())).toContain('Text')
  })

  it('selects people and emits their IDs for a batch merge', async () => {
    const wrapper = mount(PersonDiscoveryPanel, {
      props: {
        faces: [],
        people: ['Ada King', 'Grace Hopper', 'Joan Clarke'].map((name, index) => ({
          id: `person-${index + 1}`,
          name,
          shortDescription: '',
          aliases: [],
          portrait: '',
          portraitLoading: false,
        })),
        currentName: 'Ada Lovelace',
        referenceFaceCount: 1,
      },
      global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
    })

    await wrapper.get('[aria-label="Select Ada King for merge"]').trigger('click')
    await wrapper
      .get('[aria-label="Select Joan Clarke for merge"]')
      .trigger('click', { shiftKey: true })

    expect(wrapper.get('[aria-label="Selected person actions"]').text()).toContain(
      '3 people selected',
    )
    expect(wrapper.findAll('[aria-label$="from merge"][aria-pressed="true"]')).toHaveLength(3)
    await wrapper.get('[aria-label="Selected person actions"] button:last-child').trigger('click')
    expect(wrapper.emitted('mergePeople')).toEqual([[['person-1', 'person-2', 'person-3']]])

    await wrapper.setProps({ mergeSucceeded: true })
    expect(wrapper.find('[aria-label="Selected person actions"]').exists()).toBe(false)
  })
})

it('keeps reference tags in Similar people and retries discovery errors', async () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [],
      people: [],
      currentName: 'Zora',
      referenceFaceCount: 15,
      peopleAnnotations: ['faces', 'name'],
      searchTerm: 'extra signal',
      searchError: new Error('invalid search'),
    },
    global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
  })
  expect(
    wrapper.get('[aria-label="Active discovery people filters"]').findAll('small'),
  ).toHaveLength(2)
  await wrapper.get('[aria-label="Remove modality faces"]').trigger('click')
  expect(wrapper.emitted('update:peopleAnnotations')?.[0]).toEqual([['name']])
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Clear filters')!
    .trigger('click')
  expect(wrapper.emitted('clearPeopleFilters')).toHaveLength(1)
  expect(wrapper.emitted('update:searchTerm')).toBeUndefined()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Retry')!
    .trigger('click')
  expect(wrapper.emitted('retry')).toHaveLength(1)
  await wrapper.setProps({ peopleAnnotations: [], searchTerm: '', searchError: undefined })
  expect(wrapper.text()).toContain('Choose a modality or enter search text.')
  expect(wrapper.find('[aria-label="Active discovery faces filters"]').exists()).toBe(false)
})

it('labels text-only matches without inventing cosine percentages', () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [{ ...face('text-face'), score: null }],
      people: [],
      currentName: 'Zora',
      referenceFaceCount: 15,
    },
    global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
  })
  expect(wrapper.text()).toContain('Text match')
  expect(wrapper.text()).not.toContain('sim ')
})

it('shows and removes a model override with default sources, and clears both choices together', async () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [],
      people: [],
      currentName: 'Zora',
      referenceFaceCount: 15,
      annotations: ['faces', 'aliases', 'name'],
      faceModel: 'alternate',
      defaultFaceModel: 'default',
      modelOptions: [{ value: 'alternate', label: 'Alternate model' }],
      searchTerm: 'keep me',
    },
    global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
  })
  expect(wrapper.get('[aria-label="Active discovery faces filters"]').text()).toContain(
    'Face model: Alternate model',
  )
  expect(wrapper.findAll('small[data-slot="badge"]')).toHaveLength(1)
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Clear filters')!
    .trigger('click')
  expect(wrapper.emitted('clearFilters')).toHaveLength(1)
  expect(wrapper.emitted('update:searchTerm')).toBeUndefined()
  await wrapper.get('[aria-label="Remove face model"]').trigger('click')
  expect(wrapper.emitted('update:faceModel')).toEqual([['']])
  await wrapper.setProps({ faceModel: 'default' })
  expect(wrapper.find('[aria-label="Active discovery faces filters"]').exists()).toBe(false)
})

it('keeps failed action selections available for retry without offering a search retry', async () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [face('retry-face')],
      people: [{ id: 'retry-person', name: 'Orion', aliases: [], shortDescription: '' }],
      currentName: 'Zora',
      referenceFaceCount: 15,
    },
    global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
  })
  await wrapper.get('[aria-label="Select face retry-face for assignment"]').trigger('click')
  const assign = () =>
    wrapper.findAll('button').find((button) => button.text() === 'Assign to Zora')!
  await assign().trigger('click')
  await wrapper.setProps({ assignmentFailed: true })
  expect(wrapper.get('[role="alert"]').text()).toContain('Assignment failed.')
  expect(wrapper.text()).not.toContain('Search failed.')
  expect(wrapper.findAll('button').some((button) => button.text() === 'Retry')).toBe(false)
  await assign().trigger('click')
  expect(wrapper.emitted('assignFaces')).toEqual([[['retry-face']], [['retry-face']]])
  await wrapper.setProps({ assignmentFailed: false })
  await wrapper.get('[aria-label="Select Orion for merge"]').trigger('click')
  const merge = () =>
    wrapper.findAll('button').find((button) => button.text() === 'Merge into Zora')!
  await merge().trigger('click')
  await wrapper.setProps({ mergeFailed: true })
  expect(wrapper.get('[role="alert"]').text()).toContain('Merge failed.')
  expect(wrapper.text()).not.toContain('Search failed.')
  await merge().trigger('click')
  expect(wrapper.emitted('mergePeople')).toEqual([[['retry-person']], [['retry-person']]])
})

it('keeps face modalities/model before assignment and gives people their own matching controls', () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [],
      people: [],
      currentName: 'Lina',
      referenceFaceCount: 42,
      modelOptions: [{ value: 'model', label: 'Model' }],
      faceModel: 'model',
      peopleFaceModel: 'model',
      faceSort: { field: 'confidence', direction: 'asc' },
      peopleSort: { field: 'name', direction: 'asc' },
      faceSortOptions: [{ value: 'confidence', label: 'Confidence', kind: 'number' }],
      peopleSortOptions: [{ value: 'name', label: 'Name', kind: 'text' }],
    },
    global: {
      stubs: {
        RouterLink: RouterLinkStub,
        PersonPortrait: true,
        SearchFilterPanel: {
          props: ['label', 'filtersOnly'],
          template: '<div :aria-label="label"><input v-if="!filtersOnly" /><slot /></div>',
        },
      },
    },
  })
  const faces = wrapper.get('[aria-label="Discovery faces"]')
  const people = wrapper.get('[aria-label="Discovery people"]')
  expect(faces.find('input').exists()).toBe(false)
  expect(people.find('input').exists()).toBe(true)
  expect(
    faces.findAll('button[aria-label]').map((control) => control.attributes('aria-label')),
  ).toEqual(['Face model', 'Assignment', 'Sort similar faces'])
  expect(
    people.findAll('button[aria-label]').map((control) => control.attributes('aria-label')),
  ).toEqual(['Modalities', 'Face model', 'Sort similar people'])
})

it('omits legacy text and modality controls from the face-only panel', () => {
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: [],
      people: [],
      currentName: 'Lina',
      referenceFaceCount: 42,
      annotations: ['name'],
      faceSearchTerm: 'legacy identifier',
      searchTerm: 'keep people text',
    },
    global: {
      stubs: {
        RouterLink: RouterLinkStub,
        PersonPortrait: true,
        SearchFilterPanel: {
          props: ['label', 'filtersOnly'],
          template:
            '<div :aria-label="label + ` panel`"><input v-if="!filtersOnly" /><slot /></div>',
        },
      },
    },
  })
  const faces = wrapper.get('[aria-label="Discovery faces panel"]')
  expect(faces.find('input').exists()).toBe(false)
  expect(faces.find('[aria-label="Modalities"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="Active discovery faces filters"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="Remove face text"]').exists()).toBe(false)
  expect(
    wrapper.get('[aria-label="Discovery people panel"]').find('[aria-label="Modalities"]').exists(),
  ).toBe(true)
})

it('bounds found faces to two rows, uses cached results first and keeps retry in the plus tile', async () => {
  const records = Array.from({ length: 30 }, (_, i) => face(`paged-${i}`))
  const wrapper = mount(PersonDiscoveryPanel, {
    props: {
      faces: records.slice(0, 14),
      people: [],
      currentName: 'Lina',
      referenceFaceCount: 42,
      faceCount: 30,
      hasMoreFaces: true,
    },
    global: { stubs: { RouterLink: RouterLinkStub, PersonPortrait: true } },
  })
  expect(wrapper.findAll('[data-found-face-card]')).toHaveLength(13)
  await wrapper.get('[aria-label="Select face paged-0 for assignment"]').trigger('click')
  await wrapper.get('[data-found-faces-more]').trigger('click')
  expect(wrapper.emitted('loadMoreFaces')).toHaveLength(1)
  await wrapper.setProps({ loadingMoreFaces: true })
  expect(wrapper.get('[data-found-faces-more]').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ loadingMoreFaces: false, moreFacesFailed: true })
  expect(wrapper.get('[data-found-faces-more]').attributes('aria-label')).toBe('Retry')
  await wrapper.get('[data-found-faces-more]').trigger('click')
  expect(wrapper.emitted('loadMoreFaces')).toHaveLength(2)
  await wrapper.setProps({ faces: records, hasMoreFaces: false, moreFacesFailed: false })
  expect(wrapper.findAll('[data-found-face-card]')).toHaveLength(27)
  expect(wrapper.get('[role="toolbar"]').text()).toContain('1 face selected')
  await wrapper.get('[data-found-faces-more]').trigger('click')
  expect(wrapper.findAll('[data-found-face-card]')).toHaveLength(30)
  expect(wrapper.find('[data-found-faces-more]').exists()).toBe(false)
  expect(wrapper.emitted('loadMoreFaces')).toHaveLength(2)
  await wrapper.setProps({ faceModel: 'other' })
  expect(wrapper.findAll('[data-found-face-card]')).toHaveLength(13)
  expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
  wrapper.unmount()
})
