import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SIDEBAR_WIDTH, useSidebarWidth, useWorkspaceSplit } from '@/composables/workspace-split'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('responsive workspace split', () => {
  it('restores independent sizes through repeated round trips and reloads', async () => {
    const direction = ref<'horizontal' | 'vertical'>('horizontal')
    let size = 40
    let split: ReturnType<typeof useWorkspaceSplit>
    const panel = ref({
      getSize: () => size,
      resize: vi.fn((value: number) => {
        size = value
        split.layoutChanged([value, 100 - value])
      }),
    })
    const scope = effectScope()
    split = scope.run(() => useWorkspaceSplit(direction, panel))!
    size = 46
    split.layoutChanged([46, 54])
    for (let pass = 0; pass < 3; pass++) {
      direction.value = 'vertical'
      await nextTick()
      await nextTick()
      expect(size).toBe(pass ? 35 : 30)
      size = 35
      split.layoutChanged([35, 65])
      direction.value = 'horizontal'
      await nextTick()
      await nextTick()
      expect(size).toBe(46)
    }
    scope.stop()
    const reload = effectScope()
    expect(reload.run(() => useWorkspaceSplit(ref('vertical'), panel))!.defaultSize).toBe(35)
    reload.stop()
  })

  it('keeps legacy split settings and ignores unavailable or malformed storage', () => {
    localStorage.setItem(
      'reka:document-workspace-horizontal',
      JSON.stringify({ prior: { layout: [51, 49] } }),
    )
    const scope = effectScope()
    expect(scope.run(() => useWorkspaceSplit(ref('horizontal'), ref(null)))!.defaultSize).toBe(51)
    scope.stop()
    localStorage.clear()
    localStorage.setItem('document-workspace-layouts-v1', '{invalid')
    const invalid = effectScope()
    expect(invalid.run(() => useWorkspaceSplit(ref('vertical'), ref(null)))!.defaultSize).toBe(30)
    invalid.stop()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const blocked = effectScope()
    const split = blocked.run(() => useWorkspaceSplit(ref('horizontal'), ref(null)))!
    expect(split.defaultSize).toBe(40)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => split.layoutChanged([50, 50])).not.toThrow()
    blocked.stop()
  })
})

// The sidebar restore waits for the splitter to measure the wide layout.
async function settled() {
  await nextTick()
  for (let frame = 0; frame < 3; frame++) await new Promise(requestAnimationFrame)
}

describe('scan sidebar width (#121)', () => {
  it('saves wide widths only and restores them when the screen widens again', async () => {
    const wide = ref(true)
    let size = SIDEBAR_WIDTH.default
    const panel = ref({ getSize: () => size, resize: vi.fn((value: number) => (size = value)) })
    const scope = effectScope()
    const sidebar = scope.run(() => useSidebarWidth(wide, panel))!
    expect(sidebar.defaultSize).toBe(400)
    sidebar.layoutChanged([60, 520])
    // Narrow layouts stack the sidebar; their splitter sizes are not kept.
    wide.value = false
    await nextTick()
    sidebar.layoutChanged([50, 0])
    sidebar.layoutChanged([50, 330])
    wide.value = true
    await settled()
    expect(panel.value.resize).toHaveBeenLastCalledWith(520)
    sidebar.layoutChanged([70, 319.99])
    wide.value = false
    await nextTick()
    wide.value = true
    await settled()
    expect(panel.value.resize).toHaveBeenLastCalledWith(320)
    sidebar.layoutChanged([60, 520])
    // Widths outside the limits are ignored.
    sidebar.layoutChanged([90, 100])
    sidebar.layoutChanged([10, 2000])
    scope.stop()
    const reload = effectScope()
    expect(reload.run(() => useSidebarWidth(ref(true), ref(null)))!.defaultSize).toBe(520)
    reload.stop()
  })

  it('ignores malformed or unavailable storage', () => {
    localStorage.setItem('document-sidebar-width-v1', '{invalid')
    const scope = effectScope()
    expect(scope.run(() => useSidebarWidth(ref(true), ref(null)))!.defaultSize).toBe(400)
    scope.stop()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const blocked = effectScope()
    const sidebar = blocked.run(() => useSidebarWidth(ref(true), ref(null)))!
    expect(() => sidebar.layoutChanged([60, 500])).not.toThrow()
    blocked.stop()
  })
})
