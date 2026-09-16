import type { EntityType } from '@/client/types.gen'

export type TranscriptionLineId =
  | 'line-intro'
  | 'line-anna'
  | 'line-program'
  | 'line-attendees'
  | 'line-next-meeting'
  | 'line-details'
  | 'line-library'
  | 'line-exhibition'
  | 'line-school'
  | 'line-restoration'
  | 'line-market'
  | 'line-choir'
  | 'line-sports'
  | 'line-weather'

export type TranslationLanguage = 'en' | 'cs' | 'de'

export type FaceStatus = 'auto' | 'valid' | 'change' | 'empty' | 'fail'

export type Face = {
  id: string
  personId: string | null
  name: string
  confidence: number
  status: FaceStatus
  position: { left: number; top: number; width: number; height: number }
  portrait: string
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
  id: TranscriptionLineId
  text: string
  position: { left: number; top: number; width: number; height: number }
  entities?: TranscriptionEntitySpan[]
}
