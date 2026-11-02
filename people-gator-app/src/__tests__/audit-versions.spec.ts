import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { readVersion } from '@/query/versions'
import { usePatchEntityMutation } from '@/query/entities'

const api = vi.hoisted(() => ({ patch: vi.fn() }))
vi.mock('@/client', () => ({ patchEntityRouteApiV1EntitiesEntityIdPatch: api.patch }))

describe('versions read by mutation callers', () => {
  it('reads versions from paginated results and avoids related-object versions', () => {
    const client = new QueryClient()
    client.setQueryData(['faces'], {
      pages: [
        { items: [{ detection_id: 'face', entity_id: 'person', source_id: 'page', version: 7 }] },
      ],
    })
    client.setQueryData(['people'], {
      pages: [{ items: [{ entity_id: 'person', entity_type: 'person', version: 3 }] }],
    })
    client.setQueryData(['pages'], { source_id: 'page', source_type: 'page', version: 2 })
    expect(readVersion(client, 'face', 'face')).toBe(7)
    expect(readVersion(client, 'entity', 'person')).toBe(3)
    expect(readVersion(client, 'source', 'page')).toBe(2)
    expect(() => readVersion(client, 'mention', 'missing')).toThrow('Reload')
    client.clear()
  })

  it('refuses to invent a version for an unread object', () => {
    const client = new QueryClient()
    client.setQueryData(['legacy'], { entity_id: 'person' })
    expect(() => readVersion(client, 'entity', 'person')).toThrow('Reload')
    client.clear()
  })

  it('surfaces a conflict without rereading or retrying an overwrite', async () => {
    const client = new QueryClient()
    client.setQueryData(['entities', 'detail', 'person'], { entity_id: 'person', version: 4 })
    const conflict = new Error('Version conflict; reload before editing')
    api.patch.mockRejectedValueOnce(conflict)
    let mutation!: ReturnType<typeof usePatchEntityMutation>
    const wrapper = mount(
      defineComponent({
        setup() {
          mutation = usePatchEntityMutation()
          return () => h('div')
        },
      }),
      {
        global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
      },
    )
    await expect(
      mutation.mutateAsync({ entityId: 'person', body: { name: 'Draft', expected_version: 3 } }),
    ).rejects.toThrow('Version conflict')
    expect(api.patch).toHaveBeenCalledTimes(1)
    expect(api.patch.mock.calls[0]![0].body.expected_version).toBe(3)
    expect(client.getQueryData(['entities', 'detail', 'person'])).toEqual({
      entity_id: 'person',
      version: 4,
    })
    wrapper.unmount()
    client.clear()
  })
})
