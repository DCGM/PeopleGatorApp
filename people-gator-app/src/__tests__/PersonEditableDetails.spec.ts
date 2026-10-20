import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'

describe('PersonEditableDetails', () => {
  it('edits identity authority IDs in the person header', async () => {
    const wrapper = mount(PersonEditableDetails, {
      global: { stubs: { PersonPortrait: true, PersonThumbnailPicker: true } },
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
})
