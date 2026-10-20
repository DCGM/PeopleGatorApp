import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import PersonFaceCard from '@/components/custom/PersonFaceCard.vue'
import type { PersonFace } from '@/viewmodels/person-detail.types'
import { annotationChangeTime } from '@/lib/annotation-change-time'

vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: computed(() => ({ reviewer: 'Preview reviewer' })) }),
}))
const face: PersonFace = {
  id: 'detection',
  portrait: '',
  portraitLoading: false,
  confidence: 99,
  library: 'preview-library',
  documentId: 'document-identifier',
  pageId: 'page-identifier',
  pageLabel: 'Page 1',
  position: { x: 0, y: 0, width: 1, height: 1 },
  linkState: 'verified',
  metadata: {
    last_touched_at: '2026-10-20T10:00:00Z',
    last_touched_by_user_id: 'reviewer',
  } as PersonFace['metadata'],
}

describe('person evidence cards', () => {
  it('keeps the complete source together, overlays status and separates editor/source links with retained scope', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/people/:personId', name: 'person-detail', component: { template: '<div />' } },
        { path: '/people', name: 'people-search', component: { template: '<div />' } },
        {
          path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
          name: 'document-page',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/people/person?evidence_origin=authority&origin_text=Irena')
    const wrapper = mount(PersonFaceCard, {
      props: { face, personName: 'Irena', matching: true },
      global: { plugins: [router], stubs: { VerifyEntityLink: true } },
    })
    expect(wrapper.get('[data-face-source]').text()).toBe(
      'preview-library · document-identifier · page-identifier',
    )
    expect(wrapper.get('[data-face-status-badge]').attributes('class')).toContain(
      'bottom-2 right-2',
    )
    expect(wrapper.text()).toContain('Matching detection')
    expect(wrapper.text()).toContain('Last changed')
    expect(wrapper.text()).toContain('Preview reviewer')
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Detection origin')
    expect(wrapper.get('a').attributes('href')).toContain('evidence_origin=authority')
    expect(wrapper.get('a').attributes('href')).toContain('person=detection')
    expect(wrapper.find('a a').exists()).toBe(false)
    await wrapper.get('a[title="Evidence changed by Preview reviewer"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('people-search')
    expect(router.currentRoute.value.query.evidence_user).toBe('reviewer')
    await wrapper.setProps({ face: { ...face, pageId: '', metadata: undefined } })
    expect(wrapper.text()).toContain('Last changed not recorded')
    expect(wrapper.text()).toContain('User not recorded')
    expect(wrapper.text()).toContain('Source page unavailable.')
    wrapper.unmount()
  })

  it('formats recent edits compactly and preserves unknown or future history honestly', () => {
    const now = new Date('2026-10-20T12:00:00Z')
    expect(annotationChangeTime('2026-10-20T11:59:45Z', now)).toBe('just now')
    expect(annotationChangeTime('2026-10-20T11:59:00Z', now)).toBe('1 min ago')
    expect(annotationChangeTime('2026-10-20T10:00:00Z', now)).toBe('2h ago')
    expect(annotationChangeTime('2026-10-18T12:00:00Z', now)).toBe('2d ago')
    for (const value of ['2026-01-01T12:00:00Z', '2026-10-21T12:00:00Z'])
      expect(annotationChangeTime(value, now)).toBe(new Date(value).toLocaleDateString())
    expect(annotationChangeTime(null, now)).toBeNull()
    expect(annotationChangeTime('invalid', now)).toBeNull()
  })
})
