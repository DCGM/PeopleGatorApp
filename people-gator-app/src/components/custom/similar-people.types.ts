export type SimilarPersonSource = 'page' | 'database'

export type SimilarPersonCandidate = {
  id: string
  name: string
  portrait?: string
  score: number
  nerMentions: number
  detections: number
  source: SimilarPersonSource
  faceId?: string
  entityKey?: string
  entityLineIndex?: number
}
