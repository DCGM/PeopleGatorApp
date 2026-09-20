export type SimilarPersonSource = 'page' | 'database'

export type SimilarPersonMatchSource =
  | { type: 'text-search'; score: number }
  | { type: 'face-match'; distance: number }
  | { type: 'scan-text' }
  | { type: 'scan-face' }

export type SimilarPersonCandidate = {
  id: string
  name: string
  shortDescription?: string
  portrait?: string
  score?: number
  nerMentions: number
  detections: number
  closestMentionDistancePx?: number
  source: SimilarPersonSource
  matchSources?: SimilarPersonMatchSource[]
  wikidataId?: string
  nlcrAuthorityId?: string
  faceId?: string
  entityKey?: string
  entityLineIndex?: number
}
