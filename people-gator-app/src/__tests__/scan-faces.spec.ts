import { describe, expect, it } from 'vitest'
import type { FaceResponse } from '@/client'
import { groupFacesByPerson, scanFaceParams, type ScanFaceItem } from '@/viewmodels/scan-faces'

const item = (id: string, entity: string | null): ScanFaceItem => ({
  face: { detection_id: id, entity_id: entity, source_id: 'page' } as FaceResponse,
  onPage: true,
})
const sources = { page: 'page-source', document: 'document-source' }

describe('scan faces (#103)', () => {
  it('pages one scope and keeps people contiguous when grouped', () => {
    expect(
      scanFaceParams('page', 'flat', { field: 'confidence', direction: 'desc' }, sources, []),
    ).toEqual({
      'filter.page_source_id': ['page-source'],
      sort: 'confidence',
      sort_direction: 'desc',
      limit: 30,
      return_total_count: true,
    })
    expect(
      scanFaceParams('document', 'person', { field: 'confidence', direction: 'desc' }, sources, [
        'manual',
      ]),
    ).toMatchObject({
      'filter.document_source_id': ['document-source'],
      'filter.entity_link_state': ['manual'],
      sort: 'person',
      sort_direction: 'asc',
    })
  })

  it('groups by person with Unassigned last and never repeats a group across batches', () => {
    const groups = groupFacesByPerson([
      item('1', null),
      item('2', 'ada'),
      item('3', 'ada'),
      item('4', 'bea'),
      // A later batch can still bring a face of an earlier group.
      item('5', 'ada'),
      item('6', null),
    ])
    expect(
      groups.map((group) => [group.key, group.items.map((entry) => entry.face.detection_id)]),
    ).toEqual([
      ['ada', ['2', '3', '5']],
      ['bea', ['4']],
      ['unassigned', ['1', '6']],
    ])
  })
})
