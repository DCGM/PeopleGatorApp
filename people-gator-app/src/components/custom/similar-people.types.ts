export type SimilarPersonSource = 'page' | 'database'

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
  faceId?: string
  entityKey?: string
  entityLineIndex?: number
}
