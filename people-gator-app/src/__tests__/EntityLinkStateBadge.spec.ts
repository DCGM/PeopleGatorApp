import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EntityLinkStateBadge from '@/components/custom/EntityLinkStateBadge.vue'
import UiTooltip from '@/components/custom/UiTooltip.vue'
import { linkTooltip } from '@/lib/entity-links'

describe('EntityLinkStateBadge', () => {
  it.each(['automatic', 'manual', 'verified', null] as const)(
    'preserves %s state and accessible text when workspace tooltips are disabled',
    (linkState) => {
      const metadata = { linkState }
      const wrapper = mount(EntityLinkStateBadge, {
        props: { ...metadata, focusable: false, tooltip: false },
      })
      expect(wrapper.findComponent(UiTooltip).exists()).toBe(false)
      const badge = wrapper.get('[data-face-status-badge]')
      expect(badge.attributes('title')).toBeUndefined()
      expect(badge.attributes('tabindex')).toBeUndefined()
      expect(badge.attributes('aria-label')).toBe(linkTooltip(metadata))
      expect(badge.find('svg').exists()).toBe(true)
      expect(badge.text()).not.toBe('')
    },
  )

  it('retains tooltips and keyboard focus for callers outside the scan workspace', () => {
    const wrapper = mount(EntityLinkStateBadge, { props: { linkState: 'verified' } })
    expect(wrapper.findComponent(UiTooltip).exists()).toBe(true)
    const badge = wrapper.get('[data-face-status-badge]')
    expect(badge.attributes('title')).toBe('Verified link')
    expect(badge.attributes('aria-label')).toBe('Verified link')
    expect(badge.attributes('tabindex')).toBe('0')
  })
})
