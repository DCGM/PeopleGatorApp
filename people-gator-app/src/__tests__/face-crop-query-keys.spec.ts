import { QueryClient } from '@tanstack/vue-query'
import { describe, expect, it } from 'vitest'

import { queryKeys } from '@/query/keys'

describe('face crop query keys', () => {
  it('keeps immutable crops when face evidence is invalidated', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.faceCrops.aligned('face', 256), new Blob())
    queryClient.setQueryData(queryKeys.faces.list({ limit: 1 }), { items: [] })
    await queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
    expect(queryClient.getQueryState(queryKeys.faces.list({ limit: 1 }))?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(queryKeys.faceCrops.aligned('face', 256))?.isInvalidated).toBe(
      false,
    )
    queryClient.clear()
  })
})
