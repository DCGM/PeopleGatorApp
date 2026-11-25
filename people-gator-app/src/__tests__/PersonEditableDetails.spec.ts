import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'

describe('PersonEditableDetails', () => {
  it('edits identity authority IDs in the person header', async () => {
    const wrapper = mount(PersonEditableDetails, {
      global: { stubs: { PersonPortrait: true } },
      props: {
        modelValue: {
          name: 'Ada Lovelace',
          shortDescription: 'Mathematician',
          article: '',
          aliases: [],
        },
        personId: 'ada-lovelace',
        faceCount: 1,
        mentionCount: 2,
        libraryCount: 1,
        wikidataId: 'https://www.wikidata.org/wiki/Q7259',
        nationalLibraryAuthorityId: 'xx0000000',
      },
    })

    expect(wrapper.get('header').text()).toContain('https://www.wikidata.org/wiki/Q7259')
    expect(wrapper.get('a').attributes('href')).toBe('https://www.wikidata.org/wiki/Q7259')
    expect(wrapper.get('header').text()).toContain('xx0000000')
    expect(wrapper.find('section').text()).not.toContain('Wikidata')

    await wrapper.get('[aria-label="Edit Wikidata ID"]').trigger('click')
    const editable = wrapper.get('[role="textbox"]')
    editable.element.textContent = ' https://www.wikidata.org/wiki/Q123 '
    await editable.trigger('input')
    await wrapper.get('[aria-label="Save Wikidata ID"]').trigger('click')

    expect(wrapper.emitted('update:identifiers')?.[0]?.[0]).toEqual({
      wikidataId: 'https://www.wikidata.org/wiki/Q123',
      nationalLibraryAuthorityId: 'xx0000000',
    })
  })

  const base = {
    modelValue: { name: 'Karel Vrba', shortDescription: '', article: '', aliases: [] },
    personId: 'karel',
    faceCount: 0,
    mentionCount: 0,
    libraryCount: 0,
    wikidataId: '',
    nationalLibraryAuthorityId: '',
  }
  const nameDates = {
    firstName: 'Karel',
    middleNames: '',
    surname: 'Vrba',
    birthDate: '1890-03-14',
    deathDate: '',
  }

  it('shows and edits structured names and life dates', async () => {
    const wrapper = mount(PersonEditableDetails, {
      global: { stubs: { PersonPortrait: true } },
      props: { ...base, nameDates },
    })
    const section = () => wrapper.get('[aria-label="Name and life dates"]')
    expect(section().text()).toContain('Karel')
    expect(section().text()).toContain('Vrba')
    expect(section().text()).toContain('1890')
    expect(section().text()).toContain('Died—')

    await wrapper.get('[aria-label="Edit name and life dates"]').trigger('click')
    await wrapper.get('input[aria-label="Middle names"]').setValue('  Jan   Maria ')
    await wrapper.get('input[aria-label="Died"]').setValue('1962-11-02')
    await wrapper.get('input[aria-label="First name"]').setValue('')
    await wrapper.get('[aria-label="Save name and life dates"]').trigger('click')

    expect(wrapper.emitted('update:nameDates')?.[0]?.[0]).toEqual({
      firstName: '',
      middleNames: 'Jan Maria',
      surname: 'Vrba',
      birthDate: '1890-03-14',
      deathDate: '1962-11-02',
    })
    expect(wrapper.find('input[aria-label="Died"]').exists()).toBe(false)
  })

  it('keeps editing and explains a death date before the birth date', async () => {
    const wrapper = mount(PersonEditableDetails, {
      global: { stubs: { PersonPortrait: true } },
      props: { ...base, nameDates },
    })
    await wrapper.get('[aria-label="Edit name and life dates"]').trigger('click')
    await wrapper.get('input[aria-label="Died"]').setValue('1880-01-01')
    await wrapper.get('[aria-label="Save name and life dates"]').trigger('click')

    expect(wrapper.emitted('update:nameDates')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').text()).toBe('Death date must not be before birth date.')
    expect(wrapper.get('input[aria-label="Died"]').attributes('aria-invalid')).toBe('true')

    await wrapper.get('[aria-label="Cancel name and life dates editing"]').trigger('click')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('1880')
  })
})
