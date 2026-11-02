import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useWorkspaceSplit } from '@/composables/workspace-split'

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
