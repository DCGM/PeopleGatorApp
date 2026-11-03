import { describe, expect, it, vi, afterEach } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import {
  defaultDocumentColumns,
  DOCUMENT_COLUMNS_STORAGE_KEY,
  readDocumentColumns,
  useDocumentColumns,
} from '@/viewmodels/document-table'

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})
describe('document column session preferences', () => {
  it.each([null, '', 'null', '[]', '42', '{', '{"obsolete":true}', '{"name":"false"}'])(
    'falls back for invalid or obsolete saved selections (%s)',
    (raw) => {
      expect(readDocumentColumns({ getItem: () => raw })).toEqual(defaultDocumentColumns())
    },
  )
  it('retains valid choices and ignores obsolete IDs and invalid values', () => {
    const getItem = () =>
      '{"name":false,"ndk":true,"faces_total":false,"obsolete":true,"library":"bad"}'
    expect(readDocumentColumns({ getItem })).toEqual({
      ...defaultDocumentColumns(),
      name: false,
      ndk: true,
      faces_total: false,
    })
    expect(
      readDocumentColumns({
        getItem: () => {
          throw new Error('denied')
        },
      }),
    ).toEqual(defaultDocumentColumns())
  })
  it('saves changes and restores them on remount, including restore defaults', async () => {
    let columns!: ReturnType<typeof useDocumentColumns>
    const Component = defineComponent({
      setup() {
        columns = useDocumentColumns()
        return () => null
      },
    })
    let wrapper = mount(Component)
    columns.value = { ...columns.value, name: false, ndk: true }
    await nextTick()
    expect(JSON.parse(window.sessionStorage.getItem(DOCUMENT_COLUMNS_STORAGE_KEY)!)).toEqual(
      columns.value,
    )
    wrapper.unmount()
    wrapper = mount(Component)
    expect(columns.value).toEqual({ ...defaultDocumentColumns(), name: false, ndk: true })
    columns.value = defaultDocumentColumns()
    await nextTick()
    wrapper.unmount()
    wrapper = mount(Component)
    expect(columns.value).toEqual(defaultDocumentColumns())
    wrapper.unmount()
  })
  it('keeps controls usable when accessing or writing sessionStorage throws', async () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
    })
    let columns!: ReturnType<typeof useDocumentColumns>
    const wrapper = mount(
      defineComponent({
        setup() {
          columns = useDocumentColumns()
          return () => null
        },
      }),
    )
    columns.value.ndk = true
    await nextTick()
    expect(columns.value.ndk).toBe(true)
    wrapper.unmount()
  })
})
