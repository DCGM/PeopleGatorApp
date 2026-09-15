import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import ContentEditable from '@/components/custom/ContentEditable.vue'

describe('ContentEditable', () => {
  it('does not rewrite the active element while updating v-model', async () => {
    const Host = defineComponent({
      components: { ContentEditable },
      setup() {
        return { value: ref('Anna') }
      },
      template: '<ContentEditable v-model="value" editable />',
    })
    const wrapper = mount(Host, { attachTo: document.body })
    const editable = wrapper.get('[contenteditable="plaintext-only"]')
    const element = editable.element as HTMLElement

    element.focus()
    element.textContent = 'AnXna'
    await editable.trigger('input')
    await nextTick()

    expect(wrapper.vm.value).toBe('AnXna')
    expect(editable.element).toBe(element)
    expect(element.textContent).toBe('AnXna')

    wrapper.unmount()
  })
})
