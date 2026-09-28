import type { EntityResponse, FoundEntity, TextMentionSpanModel } from '@/client'
import type { EntitySearchParams } from '@/query/search'

export type CandidateBrowseMode = 'page' | 'face'

/** Face similarity and text search are distinct modes, never a fused request. */
export function candidateSearchParams(
  selectedFaceId: string | null,
  searchTerm: string,
  faceEmbeddingModel?: string,
  browseMode: CandidateBrowseMode = 'face',
): EntitySearchParams | undefined {
  const text = searchTerm.trim()
  if (text) return { 'query.text': [text], limit: 50 }
  if (browseMode === 'face' && selectedFaceId && faceEmbeddingModel) {
    return {
      'query.face_id': [selectedFaceId],
      'query.face_embedding_model': faceEmbeddingModel,
      limit: 50,
    }
  }
  return undefined
}

/** The current page's own detections and mentions determine source membership. */
export function currentPagePersonIds(
  faces: Array<{ entity_id?: string | null }>,
  spans: Array<Pick<TextMentionSpanModel, 'entity_id' | 'entity_type'>>,
) {
  return [
    ...new Set([
      ...faces.flatMap((face) => (face.entity_id ? [face.entity_id] : [])),
      ...spans.filter((span) => span.entity_type === 'person').map((span) => span.entity_id),
    ]),
  ]
}

export function candidateEntities(
  onPage: EntityResponse[],
  matches: FoundEntity[],
  searchTerm: string,
): Array<EntityResponse | FoundEntity> {
  // Text search must show only server matches, including alias matches whose
  // primary name differs from the search term.
  if (searchTerm.trim()) return matches
  const unique = new Map<string, EntityResponse | FoundEntity>()
  for (const entity of [...matches, ...onPage]) {
    if (!unique.has(entity.entity_id)) unique.set(entity.entity_id, entity)
  }
  return [...unique.values()]
}
