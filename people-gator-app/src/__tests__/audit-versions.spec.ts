import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useSelectedSnapshots } from '@/composables/selected-snapshots'
import { usePatchEntityMutation } from '@/query/entities'

const api = vi.hoisted(() => ({ patch: vi.fn() }))
vi.mock('@/client', () => ({ patchEntityRouteApiV1EntitiesEntityIdPatch: api.patch }))

describe('versions read by mutation callers', () => {
  it('preserves the selected representation after a background refresh', () => {
    const ids = ref(new Set<string>())
    const records = ref([{ id: 'face', version: 7, name: 'Reviewed' }])
    const selection = useSelectedSnapshots(ids, () => records.value)
    ids.value = new Set(['face'])
    records.value = [{ id: 'face', version: 8, name: 'Another edit' }]
    expect(selection.value).toEqual([{ id: 'face', version: 7, name: 'Reviewed' }])
    ids.value = new Set()
    ids.value = new Set(['face'])
    expect(selection.value[0]?.version).toBe(8)
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
      mutation.mutateAsync({ entityId: 'person', body: { name: 'Draft', version: 3 } }),
    ).rejects.toThrow('Version conflict')
    expect(api.patch).toHaveBeenCalledTimes(1)
    expect(api.patch.mock.calls[0]![0].body.version).toBe(3)
    expect(client.getQueryData(['entities', 'detail', 'person'])).toEqual({
      entity_id: 'person',
      version: 4,
    })
    wrapper.unmount()
    client.clear()
  })
})
