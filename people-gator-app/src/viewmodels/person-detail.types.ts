import type { BoundingBox } from '@/client'

export type PersonProfile = {
  name: string
  shortDescription: string
  article: string
  aliases: string[]
}

export type PersonProcessingInfo = {
  touchedAt: string | null
  userId: string | null
  userLabel: string | null
  apiKeyId: string | null
  apiKeyLabel: string | null
}

export type PersonIdentifiers = {
  wikidataId: string
  nationalLibraryAuthorityId: string
}

export type PersonFace = {
  id: string
  portrait: string
  portraitLoading: boolean
  confidence: number
  library: string
  documentId: string
  pageId: string
  pageLabel: string
  position: BoundingBox
}

export type PersonMention = {
  id: string
  excerpt: string
  matchedText: string
  library: string
  documentId: string
  documentTitle: string
  pageId: string
  pageLabel: string
}

export type PersonDiscoveryFace = {
  id: string
  portrait: string
  portraitLoading: boolean
  score: number
  assignedEntityId: string | null
  assignedEntityName?: string
  library?: string
  documentId?: string
  pageId?: string
  pageLabel?: string
}

export type PersonDiscoveryCandidate = {
  id: string
  name: string
  shortDescription: string
  aliases: string[]
  portrait: string
  portraitLoading: boolean
}
