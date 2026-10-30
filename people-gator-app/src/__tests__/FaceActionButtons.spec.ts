import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FaceActionButtons from '@/components/custom/FaceActionButtons.vue'
import type { Face } from '@/viewmodels/document-workspace.types'

const face: Face = {
  id: 'face',
  personId: 'person',
  name: 'Lina',
  confidence: 99,
  status: 'assigned',
  position: { left: 10, top: 10, width: 20, height: 20 },
  portrait: '',
  portraitLoading: false,
  linkState: 'manual',
}
it('uses one icon group, emits actions, and respects link state and permissions', async () => {
  const wrapper = mount(FaceActionButtons, {
    props: { face, canAnnotate: true, canDelete: true },
  })
  expect(wrapper.get('[role="group"]').attributes('data-slot')).toBe('button-group')
  for (const [label, event] of [
    ['Reassign', 'findProfile'],
    ['Unlink', 'unassign'],
    ['Verify', 'verify'],
    ['Delete detection', 'delete'],
  ]) {
    const button = wrapper.get(`button[aria-label="${label}"]`)
    expect(button.text()).toBe('')
    expect(button.find('svg').exists()).toBe(true)
    await button.trigger('click')
    expect(wrapper.emitted(event!)).toHaveLength(1)
  }
  await wrapper.setProps({ busy: true })
  expect(
    wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined),
  ).toBe(true)
  await wrapper.setProps({ face: { ...face, linkState: 'verified' }, canDelete: false })
  expect(wrapper.find('[aria-label="Verify"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="Delete detection"]').exists()).toBe(false)
  await wrapper.setProps({ face: { ...face, personId: null } })
  expect(wrapper.find('[aria-label="Link"]').exists()).toBe(true)
  expect(wrapper.find('[aria-label="Unlink"]').exists()).toBe(false)
  await wrapper.setProps({ canAnnotate: false })
  expect(wrapper.findAll('button')).toHaveLength(0)
})
