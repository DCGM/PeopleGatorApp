import { mount } from '@vue/test-utils'
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
  pageUrl: 'https://archive.example/exact-api-page',
  pageLabel: 'Page 1',
  position: { x: 0, y: 0, width: 1, height: 1 },
  linkState: 'verified',
  metadata: {
    last_touched_at: '2026-10-20T10:00:00Z',
    last_touched_by_user_id: 'reviewer',
  } as PersonFace['metadata'],
}

describe('person evidence cards', () => {
  it('shows compact assignment, library and editor rows while retaining source navigation and verification attribution', async () => {
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
    await router.push('/people/person?api_key=00000000-0000-4000-8000-000000000001')
    const wrapper = mount(PersonFaceCard, {
      props: {
        face: { ...face, verifiedBy: 'verifier', verifiedAt: '2026-10-20T09:00:00Z' },
        personName: 'Irena',
      },
      global: { plugins: [router], stubs: { VerifyEntityLink: true } },
    })
    expect(wrapper.get('[data-face-source]').text()).toBe('preview-library · document-identifier')
    expect(wrapper.get('[data-face-assignment]').text()).toBe('Verifiedconf 99%')
    expect(wrapper.get('[data-face-assignment]').attributes('aria-label')).toContain(
      'Verified by verifier',
    )
    expect(wrapper.text()).not.toContain('Matching detection')
    expect(wrapper.text()).not.toContain('page-identifier')
    expect(wrapper.text()).not.toContain('Detection ID')
    expect(wrapper.find('[data-face-status-badge]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Last changed')
    expect(wrapper.text()).toContain('Preview reviewer')
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Detection origin')
    expect(wrapper.get('a').attributes('href')).toContain(
      'api_key=00000000-0000-4000-8000-000000000001',
    )
    expect(wrapper.get('a').attributes('href')).toContain('person=detection')
    expect(wrapper.find('a a').exists()).toBe(false)
    const editor = wrapper.get('[title="Evidence changed by Preview reviewer"]')
    expect(editor.element.tagName).toBe('SPAN')
    expect(editor.find('a').exists()).toBe(false)
    await editor.trigger('click')
    expect(router.currentRoute.value.name).toBe('person-detail')
    expect(router.currentRoute.value.query.touched_by).toBeUndefined()
    await wrapper.setProps({ face: { ...face, pageId: '', metadata: undefined } })
    expect(wrapper.text()).toContain('Last changed not recorded')
    expect(wrapper.text()).toContain('User not recorded')
    expect(wrapper.text()).toContain('Source page unavailable.')
    wrapper.unmount()
  })

  it('keeps archive links separate from routing and selection and replaces overlay badges', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/page', name: 'document-page', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    const wrapper = mount(PersonFaceCard, {
      props: {
        face: { ...face, matched: true },
        personName: 'Irena',
        portrait: true,
        selectable: true,
        selectionEnabled: true,
      },
      global: { plugins: [router] },
    })
    expect(wrapper.get('[data-person-portrait]').text()).toBe('Profile photo')
    expect(wrapper.get('[data-person-match]').text()).toBe('Search hit')
    expect(wrapper.findAll('[data-slot="badge"]')).toHaveLength(1)
    const link = wrapper.get('a[target="_blank"]')
    expect(link.attributes('href')).toBe(face.pageUrl)
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(link.attributes('aria-label')).toContain('page in Digitální knihovna (new tab)')
    expect(link.classes()).toContain('z-20')
    expect(wrapper.find('a a').exists()).toBe(false)
    await link.trigger('click')
    await link.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('add')).toBeUndefined()
    expect(wrapper.emitted('toggle')).toBeUndefined()
    expect(router.currentRoute.value.path).toBe('/')
    await wrapper.setProps({
      face: { ...face, pageUrl: undefined, sourceLoading: true, pageId: '' },
    })
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Loading source page')
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
