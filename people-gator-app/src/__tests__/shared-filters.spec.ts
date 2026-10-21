import { describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import {
  emptySharedFilters,
  localTimeToUtc,
  migrateLegacyFilters,
  readSharedFilters,
  relatedQuery,
  sharedFilterError,
  sharedFiltersQuery,
  sharedFiltersUrl,
  sharedUrlError,
  utcToLocalTime,
} from '@/viewmodels/shared-filters'

const doc = '00000000-0000-4000-8000-000000000001'
const page = '00000000-0000-4000-8000-000000000003'
const actor = '00000000-0000-4000-8000-000000000002'
const key = '00000000-0000-4000-8000-000000000004'
const shared: LocationQuery = {
  library: ['preview-nlk', 'preview-mzk', 'preview-mzk'],
  document: doc,
  page,
  link_state: ['verified', 'manual'],
  touched_by: actor,
  api_key: key,
  touched_from: '2026-01-01T12:00:00.123+02:00',
  touched_to: '2026-01-01T10:00:00.123Z',
}

describe('time conversion', () => {
  it('converts local wall-clock input to UTC without losing database microseconds', () => {
    const utc = '2026-03-29T21:59:59.999999Z'
    expect(localTimeToUtc(utcToLocalTime(utc))).toBe(utc)
    expect(utcToLocalTime('2026-01-02T13:30:15.123+01:00')).toBe(
      utcToLocalTime('2026-01-02T12:30:15.123Z'),
    )
    expect(localTimeToUtc('')).toBeUndefined()
    expect(utcToLocalTime('not-a-date')).toBe('')
    expect(utcToLocalTime('2026-02-30T00:00:00Z')).toBe('')
    expect(utcToLocalTime('2026-01-01T24:00:00Z')).toBe('')
    expect(utcToLocalTime('2026-01-02T12:00')).toBe('')
  })
})

describe('one shared filter configuration', () => {
  it('round-trips URL state and sends own-record modification criteria', () => {
    const filters = readSharedFilters(shared)
    expect(filters.libraries).toEqual(['preview-mzk', 'preview-nlk'])
    expect(readSharedFilters(sharedFiltersUrl(filters) as LocationQuery)).toEqual(filters)
    const query = sharedFiltersQuery(filters)
    expect(query).toEqual({
      'filter.library': ['preview-mzk', 'preview-nlk'],
      'filter.document_source_id': [doc],
      'filter.page_source_id': [page],
      'filter.entity_link_state': ['manual', 'verified'],
      'filter.last_touched_by_user_id': [actor],
      'filter.last_touched_by_api_key_id': [key],
      'filter.last_touched_from': '2026-01-01T10:00:00.123Z',
      'filter.last_touched_to': '2026-01-01T10:00:00.123Z',
    })
    // Equal bounds are inclusive; no legacy annotation criteria are produced.
    expect(sharedFilterError(filters)).toBeUndefined()
    expect(Object.keys(query).some((name) => name.includes('evidence'))).toBe(false)
    expect(sharedFiltersQuery(emptySharedFilters())).toEqual({})
  })

  it('transfers unchanged between views, without search, sort, cursors or view choices', () => {
    const fromDocuments = relatedQuery({
      name: 'document-list',
      query: { ...shared, q: 'Irena', sort: 'name', cursor: 'old', unassigned: 'yes' },
    }) as LocationQuery
    expect(readSharedFilters(fromDocuments)).toEqual(readSharedFilters(shared))
    for (const name of ['q', 'sort', 'cursor', 'unassigned'])
      expect(fromDocuments).not.toHaveProperty(name)
    // People → profile → People: the same predicates stay active and editable.
    const toProfile = relatedQuery({
      name: 'people-search',
      query: { ...fromDocuments, assignment: 'mentions' },
    }) as LocationQuery
    expect(toProfile.tab).toBe('mentions')
    expect(toProfile).not.toHaveProperty('assignment')
    const edited = relatedQuery({
      name: 'person-detail',
      query: { ...toProfile, touched_by: undefined } as unknown as LocationQuery,
    }) as LocationQuery
    expect(sharedFiltersQuery(readSharedFilters(edited))).not.toHaveProperty(
      'filter.last_touched_by_user_id',
    )
    expect(
      sharedFiltersQuery(readSharedFilters(edited))['filter.last_touched_by_api_key_id'],
    ).toEqual([key])
  })

  it('keeps invalid copied values visible and blocks their requests', () => {
    expect(sharedUrlError({ touched_from: 'not-a-date' })).toContain('invalid filter')
    expect(sharedUrlError({ touched_by: 'missing' })).toContain('invalid filter')
    expect(sharedUrlError({ ...shared, touched_from: '2027-01-01T00:00:00Z' })).toContain(
      'before or equal',
    )
    const next = relatedQuery({ name: 'people-search', query: { touched_by: [actor, 'missing'] } })
    expect(next.touched_by).toEqual([actor, 'missing'])
  })
})

describe('legacy #31 links', () => {
  it('renames same-meaning keys and drops resource-specific origin context', () => {
    const migrated = migrateLegacyFilters('people-search', {
      q: 'Irena',
      library: 'preview-nlk',
      evidence_library: 'preview-mzk',
      evidence_document: doc,
      evidence_source: page,
      origin_person_touched_by: actor,
      origin_text: 'Irena',
      origin_return: '/documents',
      origin_matched_face: page,
    })!
    expect(migrated.query).toEqual({
      q: 'Irena',
      library: ['preview-mzk', 'preview-nlk'],
      document: [doc],
      page: [page],
      origin_matched_face: page,
    })
    expect(migrated.dropped).toEqual([])
    expect(migrateLegacyFilters('people-search', shared)).toBeUndefined()
  })

  it('never turns annotation edits into another resource’s own modification', () => {
    const legacy = {
      evidence_user: actor,
      evidence_key: key,
      evidence_from: '2026-01-01T00:00:00Z',
    }
    const people = migrateLegacyFilters('people-search', legacy)!
    expect(readSharedFilters(people.query)).toEqual(emptySharedFilters())
    expect(people.dropped).toEqual(['annotation user', 'annotation API key', 'annotation from'])
    // Profiles and scans list the annotations themselves, so the meaning is kept.
    const profile = migrateLegacyFilters('person-detail', {
      ...legacy,
      touched_from: '2025-01-01T00:00:00Z',
    })!
    expect(profile.query).toEqual({
      touched_by: [actor],
      api_key: [key],
      touched_from: '2025-01-01T00:00:00Z',
    })
    expect(profile.dropped).toEqual([])
  })
})

// Router restoration and consecutive edits must preserve the effective predicates,
// including recoverable invalid values from copied URLs.
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useSharedFilters } from '@/viewmodels/shared-filters'

describe('shared configuration edits', () => {
  it('keeps invalid selections visible during other edits, then clears them explicitly', async () => {
    const Harness = defineComponent({
      setup() {
        const shared = useSharedFilters()
        return () =>
          h(
            'button',
            {
              onClick: () => {
                shared.filters.value = { ...shared.filters.value, libraries: ['preview-mzk'] }
              },
            },
            shared.error.value ?? 'valid',
          )
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: Harness }],
    })
    await router.push({
      path: '/',
      query: { q: 'Ada', touched_by: [actor, 'bad-id'], page, cursor: 'old' },
    })
    const wrapper = mount(Harness, { global: { plugins: [router] } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({
      library: ['preview-mzk'],
      touched_by: [actor, 'bad-id'],
      page: [page],
      q: 'Ada',
    })
    expect(router.currentRoute.value.query.cursor).toBeUndefined()
    expect(wrapper.text()).toContain('invalid filter')
    await router.push({ query: { ...router.currentRoute.value.query, touched_by: [actor] } })
    await flushPromises()
    expect(wrapper.text()).toBe('valid')
    router.back()
    await flushPromises()
    expect(wrapper.text()).toContain('invalid filter')
    router.forward()
    await flushPromises()
    expect(wrapper.text()).toBe('valid')
    wrapper.unmount()
  })

  it('blocks unknown link states and multiple date bounds instead of hiding them', () => {
    expect(sharedUrlError({ link_state: ['manual', 'bogus'] })).toContain('invalid filter')
    expect(
      sharedUrlError({ touched_from: ['2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z'] }),
    ).toContain('invalid filter')
    expect(readSharedFilters({ touched_from: ['2026-01-01T00:00:00Z'] }).touchedFrom).not.toBe('')
  })
})
