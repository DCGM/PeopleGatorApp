import type { LinkMetadata } from '@/lib/entity-links'
import type { FaceResponse, TextMentionResponse } from '@/client'
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

export type PersonFace = LinkMetadata & {
  /** A witness from the originating search, pinned first and labelled. */
  matched?: boolean
  metadata?: FaceResponse
  sourceId?: string
  sourceLoading?: boolean
  pageUrl?: string
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

export type PersonMention = LinkMetadata & {
  metadata?: TextMentionResponse
  sourceId?: string
  sourceLoading?: boolean
  pageUrl?: string
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
  score: number | null
  assignedEntityId: string | null
  assignedEntityName?: string
  library?: string
  documentId?: string
  pageId?: string
  pageUrl?: string
  pageLabel?: string
}

export type PersonDiscoveryCandidate = {
  textMatch?: boolean
  matchedFaceIds?: string[]
  id: string
  name: string
  shortDescription: string
  aliases: string[]
  thumbnailFaceId?: string | null
}
