import { mount } from '@vue/test-utils'
import { h } from 'vue'
import { describe, expect, it } from 'vitest'

import EditableActions from '@/components/custom/EditableActions.vue'
import { Button } from '@/components/ui/button'

describe('EditableActions', () => {
  it('renders a single edit action in a button group', async () => {
    const wrapper = mount(EditableActions, {
      props: { editing: false, label: 'name' },
    })

    expect(wrapper.find('[role="group"] [aria-label="Edit name"]').exists()).toBe(true)

    await wrapper.get('[aria-label="Edit name"]').trigger('click')
    expect(wrapper.emitted('edit')).toHaveLength(1)
  })

  it('groups field actions with save and cancel', async () => {
    const wrapper = mount(EditableActions, {
      props: { editing: true, label: 'aliases' },
      slots: {
        default: () => h(Button, {}, () => 'Add alias'),
      },
    })
    const group = wrapper.get('[role="group"]')

    expect(group.text()).toContain('Add alias')
    expect(group.find('[aria-label="Save aliases"]').exists()).toBe(true)
    expect(group.find('[aria-label="Cancel aliases editing"]').exists()).toBe(true)

    await group.get('[aria-label="Save aliases"]').trigger('click')
    await group.get('[aria-label="Cancel aliases editing"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})
