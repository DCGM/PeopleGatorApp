import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { galleryExpanded, useGalleryView } from '@/viewmodels/gallery-view'

describe('document-page gallery view URL', () => {
  it('uses compact mode for absent, invalid or repeated values', () => {
    expect(galleryExpanded({})).toBe(false)
    expect(galleryExpanded({ pages_view: 'other' })).toBe(false)
    expect(galleryExpanded({ pages_view: ['expanded', 'compact'] })).toBe(false)
    expect(galleryExpanded({ pages_view: 'expanded' })).toBe(true)
  })

  it('preserves document settings and restores expansion with history', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: {} }],
    })
    await router.push('/page?selectedPerson=nora&gallery_person_only=on&gallery_sort=name')
    let state!: ReturnType<typeof useGalleryView>
    const wrapper = mount(
      defineComponent({
        setup() {
          state = useGalleryView()
          return () => null
        },
      }),
      { global: { plugins: [router] } },
    )
    state.value = true
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      pages_view: 'expanded',
      selectedPerson: 'nora',
      gallery_person_only: 'on',
      gallery_sort: 'name',
    })
    state.value = false
    await flushPromises()
    expect(state.value).toBe(false)
    expect(router.currentRoute.value.query.pages_view).toBeUndefined()
    router.back()
    await flushPromises()
    expect(state.value).toBe(true)
    router.back()
    await flushPromises()
    expect(state.value).toBe(false)
    wrapper.unmount()
  })
})
