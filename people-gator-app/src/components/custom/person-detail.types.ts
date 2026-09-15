import type { FaceStatus } from '@/components/custom/document-page.types'

export type PersonProfile = {
  name: string
  shortDescription: string
  article: string
  aliases: string[]
}

export type PersonFace = {
  id: string
  portrait: string
  status: Extract<FaceStatus, 'auto' | 'valid' | 'change'>
  confidence: number
  library: string
  documentId: string
  pageId: string
  pageLabel: string
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
  lineId: string
  date: string
}
