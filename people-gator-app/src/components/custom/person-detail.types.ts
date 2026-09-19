import type { BoundingBox } from '@/client'

export type PersonProfile = {
  name: string
  shortDescription: string
  article: string
  aliases: string[]
}

export type PersonFace = {
  id: string
  portrait: string
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
