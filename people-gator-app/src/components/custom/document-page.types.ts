import type { EntityType } from '@/client/types.gen'

export type TranscriptionLineId =
  | 'line-intro'
  | 'line-anna'
  | 'line-program'
  | 'line-attendees'
  | 'line-next-meeting'
  | 'line-details'

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
  label: EntityType
  text: string
  line_id: string
  start_index: number
  end_index: number
}

export type TranscriptionLine = {
  id: TranscriptionLineId
  text: string
  position: { left: number; top: number; width: number; height: number }
  entities?: TranscriptionEntitySpan[]
}

export type VisibleTranscriptionLine = {
  index: number
  line: TranscriptionLine
}
