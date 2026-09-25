import type { EntityType } from '@/client/types.gen'

export type FaceStatus = 'assigned' | 'unassigned'

export type Face = {
  id: string
  embeddingModel?: string
  personId: string | null
  name: string
  shortDescription?: string
  wikidataId?: string
  nlcrAuthorityId?: string
  confidence: number
  status: FaceStatus
  position: { left: number; top: number; width: number; height: number }
  portrait: string
  portraitLoading: boolean
}

export type PageViewportBounds = {
  left: number
  top: number
  width: number
  height: number
}

export type TranscriptionEntitySpan = {
  entity_id?: string
  label: EntityType
  text: string
  line_id: string
  start_index: number
  end_index: number
}

export function transcriptionEntityKey(entity: TranscriptionEntitySpan) {
  return entity.entity_id ?? `${entity.line_id}:${entity.start_index}:${entity.end_index}`
}

export type TranscriptionLine = {
  id: string
  text: string
  position: { left: number; top: number; width: number; height: number }
  entities?: TranscriptionEntitySpan[]
}
