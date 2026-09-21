import { effectScope, ref, type Ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useObjectUrl } from '@/composables/object-url'

describe('object URL cache', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('reuses a cached blob URL when a view is left and mounted again', () => {
    vi.useFakeTimers()
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:face-crop')
    const revokeObjectURL = vi.fn<(url: string) => void>()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

    const blob = new Blob(['face'])
    const blobRef = ref(blob)
    let firstUrl: Ref<string> | undefined
    const firstScope = effectScope()
    firstScope.run(() => {
      firstUrl = useObjectUrl(blobRef)
    })

    expect(firstUrl?.value).toBe('blob:face-crop')
    firstScope.stop()

    let secondUrl: Ref<string> | undefined
    const secondScope = effectScope()
    secondScope.run(() => {
      secondUrl = useObjectUrl(blobRef)
    })

    expect(secondUrl?.value).toBe('blob:face-crop')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).not.toHaveBeenCalled()

    secondScope.stop()
    vi.advanceTimersByTime(5 * 60_000)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:face-crop')
  })
})
