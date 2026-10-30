import { mount, RouterLinkStub } from '@vue/test-utils'
import { h } from 'vue'
import { describe, expect, it } from 'vitest'
import FaceActionButtons from '@/components/custom/FaceActionButtons.vue'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
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
    ['Reassign to another profile', 'findProfile'],
    ['Unassign current profile', 'unassign'],
    ['Verify this link', 'verify'],
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
  expect(wrapper.find('[aria-label="Verify this link"]').exists()).toBe(false)
  expect(wrapper.find('[aria-label="Delete detection"]').exists()).toBe(false)
  await wrapper.setProps({ face: { ...face, personId: null } })
  expect(wrapper.find('[aria-label="Link to an existing profile"]').exists()).toBe(true)
  expect(wrapper.find('[aria-label="Unassign current profile"]').exists()).toBe(false)
  await wrapper.setProps({ canAnnotate: false })
  expect(wrapper.findAll('button')).toHaveLength(0)
})

it('orders the card actions like the scan action bar', () => {
  const labels = (wrapper: ReturnType<typeof mount>) =>
    wrapper.findAll('button[aria-label]').map((button) => button.attributes('aria-label')!)
  const bar = labels(
    mount(FaceActionButtons, { props: { face, canAnnotate: true, canDelete: true } }),
  )
  const card = labels(
    mount(SelectedFaceItem, {
      props: { face, canDelete: true },
      // The page passes the inline Verify control through this slot.
      slots: { actions: () => h('button', { 'aria-label': 'Verify this link' }) },
      global: { stubs: { RouterLink: RouterLinkStub, IdentityFacePreview: true } },
    }),
  )
  expect(bar).toEqual([
    'Reassign to another profile',
    'Unassign current profile',
    'Verify this link',
    'Delete detection',
  ])
  // New is card-only and sits beside the other assignment action.
  expect(card).toEqual([
    'Reassign to another profile',
    'Create and assign a new profile',
    'Unassign current profile',
    'Verify this link',
    'Delete detection',
  ])
})
