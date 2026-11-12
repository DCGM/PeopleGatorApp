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
      // Panel toggles at either edge are divided from the bar's own controls.
      const children = [...wrapper.element.children]
      expect(children.map((child) => child.getAttribute('data-slot') ?? child.tagName)).toEqual([
        'BUTTON',
        'separator',
        'scroll-area',
        'separator',
        'BUTTON',
      ])
      expect(wrapper.findAll('button').map((button) => button.text())).toEqual([
        'Open',
        'Zoom',
        'Close',
      ])
    } finally {
      wrapper.unmount()
    }
  })

  it('adds no toolbar role or panel dividers without a label or edge actions', () => {
    const wrapper = mount(PanelBar, { slots: { default: '<div role="tablist" />' } })
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false)
    expect(wrapper.find('[data-slot="separator"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
