import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PanelBar from '@/components/custom/PanelBar.vue'

describe('PanelBar', () => {
  it('centers one line of controls in a horizontal ScrollArea between edge actions', () => {
    const wrapper = mount(PanelBar, {
      props: { as: 'header', label: 'Scan tools' },
      slots: {
        start: '<button>Open</button>',
        default: '<button>Zoom</button>',
        end: '<button>Close</button>',
      },
    })
    try {
      expect(wrapper.element.tagName).toBe('HEADER')
      expect(wrapper.classes()).toContain('h-14')
      const toolbar = wrapper.get('[role="toolbar"]')
      expect(toolbar.attributes('aria-label')).toBe('Scan tools')
      expect(toolbar.classes()).toEqual(expect.arrayContaining(['mx-auto', 'w-max']))
      expect(toolbar.classes()).not.toContain('flex-wrap')
      expect(wrapper.get('[data-slot="scroll-area"]').find('[role="toolbar"]').exists()).toBe(true)
      expect(wrapper.findAll('button').map((button) => button.text())).toEqual([
        'Open',
        'Zoom',
        'Close',
      ])
    } finally {
      wrapper.unmount()
    }
  })

  it('adds no toolbar role without a label', () => {
    const wrapper = mount(PanelBar, { slots: { default: '<div role="tablist" />' } })
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
