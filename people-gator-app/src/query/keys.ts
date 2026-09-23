type QueryParams = Record<string, unknown> | undefined

export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    me: () => ['auth', 'me'] as const,
  },
  system: {
    all: ['system'] as const,
    root: () => ['system', 'root'] as const,
    health: () => ['system', 'health'] as const,
  },
  entities: {
    all: ['entities'] as const,
    lists: () => ['entities', 'list'] as const,
    list: (params?: QueryParams) => ['entities', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['entities', 'list', 'infinite', params ?? {}] as const,
    details: () => ['entities', 'detail'] as const,
    detail: (entityId: string) => ['entities', 'detail', entityId] as const,
  },
  faces: {
    all: ['faces'] as const,
    lists: () => ['faces', 'list'] as const,
    list: (params?: QueryParams) => ['faces', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['faces', 'list', 'infinite', params ?? {}] as const,
    detail: (detectionId: string) => ['faces', 'detail', detectionId] as const,
    alignedCrop: (detectionId: string, maxWidth?: number) =>
      ['faces', 'aligned-crop', detectionId, maxWidth] as const,
  },
  textMentions: {
    all: ['text-mentions'] as const,
    lists: () => ['text-mentions', 'list'] as const,
    list: (params?: QueryParams) => ['text-mentions', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) =>
      ['text-mentions', 'list', 'infinite', params ?? {}] as const,
    detail: (mentionId: string) => ['text-mentions', 'detail', mentionId] as const,
  },
  sources: {
    all: ['sources'] as const,
    list: (params?: QueryParams) => ['sources', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['sources', 'list', 'infinite', params ?? {}] as const,
    detail: (sourceId: string) => ['sources', 'detail', sourceId] as const,
    lookup: (url: string) => ['sources', 'lookup', url] as const,
  },
  documents: {
    all: ['documents'] as const,
    lists: () => ['documents', 'list'] as const,
    list: (params?: QueryParams) => ['documents', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['documents', 'list', 'infinite', params ?? {}] as const,
    detail: (sourceId: string) => ['documents', 'detail', sourceId] as const,
    lookup: (library: string, documentId: string) =>
      ['documents', 'lookup', library, documentId] as const,
  },
  pages: {
    all: ['pages'] as const,
    lists: () => ['pages', 'list'] as const,
    list: (params?: QueryParams) => ['pages', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['pages', 'list', 'infinite', params ?? {}] as const,
    detail: (sourceId: string) => ['pages', 'detail', sourceId] as const,
    lookup: (library: string, documentId: string, pageId: string) =>
      ['pages', 'lookup', library, documentId, pageId] as const,
    image: (sourceId: string, width?: number) => ['pages', 'image', sourceId, width] as const,
    layout: (sourceId: string) => ['pages', 'layout', sourceId] as const,
    mentionSpans: (sourceId: string) => ['pages', 'mention-spans', sourceId] as const,
  },
  images: {
    all: ['images'] as const,
    list: (params?: QueryParams) => ['images', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['images', 'list', 'infinite', params ?? {}] as const,
    detail: (imageId: string) => ['images', 'detail', imageId] as const,
    lookup: (url: string) => ['images', 'lookup', url] as const,
    content: (imageId: string) => ['images', 'content', imageId] as const,
  },
  users: {
    all: ['users'] as const,
    list: (params?: QueryParams) => ['users', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['users', 'list', 'infinite', params ?? {}] as const,
    detail: (userId: string) => ['users', 'detail', userId] as const,
  },
  search: {
    all: ['search'] as const,
    entities: (params?: QueryParams) => ['search', 'entities', params ?? {}] as const,
    infiniteEntities: (params?: QueryParams) =>
      ['search', 'entities', 'infinite', params ?? {}] as const,
    faces: (params?: QueryParams) => ['search', 'faces', params ?? {}] as const,
    infiniteFaces: (params?: QueryParams) => ['search', 'faces', 'infinite', params ?? {}] as const,
    pages: (params?: QueryParams) => ['search', 'pages', params ?? {}] as const,
    infinitePages: (params?: QueryParams) => ['search', 'pages', 'infinite', params ?? {}] as const,
    documents: (params?: QueryParams) => ['search', 'documents', params ?? {}] as const,
    infiniteDocuments: (params?: QueryParams) =>
      ['search', 'documents', 'infinite', params ?? {}] as const,
  },
  translations: {
    all: ['translations'] as const,
    detail: (text: string, language: string) => ['translations', text, language] as const,
  },
} as const
