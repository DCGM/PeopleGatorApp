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
    // Typed person resources (#123) stay under `entities`, so every entity
    // invalidation and page restart also refreshes them.
    people: (params?: QueryParams) =>
      ['entities', 'list', 'infinite', 'people', params ?? {}] as const,
    person: (entityId: string) => ['entities', 'detail', entityId, 'person'] as const,
  },
  faces: {
    all: ['faces'] as const,
    lists: () => ['faces', 'list'] as const,
    list: (params?: QueryParams) => ['faces', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['faces', 'list', 'infinite', params ?? {}] as const,
    detail: (detectionId: string) => ['faces', 'detail', detectionId] as const,
  },
  // Crops are immutable per detection. Keep them outside `faces` so evidence
  // edits that invalidate faces do not re-download every displayed portrait.
  faceCrops: {
    all: ['face-crops'] as const,
    aligned: (detectionId: string, maxWidth?: number) =>
      ['face-crops', 'aligned', detectionId, maxWidth] as const,
  },
  // Page and image bytes are immutable too, and stay outside `pages`/`images`.
  pageImages: {
    all: ['page-images'] as const,
    source: (sourceId: string) => ['page-images', sourceId] as const,
    image: (sourceId: string, width?: number) => ['page-images', sourceId, width] as const,
  },
  imageContents: {
    all: ['image-contents'] as const,
    content: (imageId: string) => ['image-contents', imageId] as const,
  },
  textMentions: {
    all: ['text-mentions'] as const,
    lists: () => ['text-mentions', 'list'] as const,
    list: (params?: QueryParams) => ['text-mentions', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) =>
      ['text-mentions', 'list', 'infinite', params ?? {}] as const,
    // Groups live under text-mentions so every mention mutation refreshes them.
    groups: (params?: QueryParams) => ['text-mentions', 'groups', params ?? {}] as const,
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
    results: (params?: QueryParams) => ['pages', 'results', 'infinite', params ?? {}] as const,
    detail: (sourceId: string) => ['pages', 'detail', sourceId] as const,
    lookup: (library: string, documentId: string, pageId: string) =>
      ['pages', 'lookup', library, documentId, pageId] as const,
    layout: (sourceId: string) => ['pages', 'layout', sourceId] as const,
    mentionSpans: (sourceId: string, states: string[] = []) => ['pages', 'mention-spans', sourceId, states] as const,
  },
  images: {
    all: ['images'] as const,
    list: (params?: QueryParams) => ['images', 'list', params ?? {}] as const,
    infinite: (params?: QueryParams) => ['images', 'list', 'infinite', params ?? {}] as const,
    detail: (imageId: string) => ['images', 'detail', imageId] as const,
    lookup: (url: string) => ['images', 'lookup', url] as const,
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
    infinitePeople: (params?: QueryParams) =>
      ['search', 'entities', 'infinite', 'people', params ?? {}] as const,
    faces: (params?: QueryParams) => ['search', 'faces', params ?? {}] as const,
    infiniteFaces: (params?: QueryParams) => ['search', 'faces', 'infinite', params ?? {}] as const,
    pages: (params?: QueryParams) => ['search', 'pages', params ?? {}] as const,
    infinitePages: (params?: QueryParams) => ['search', 'pages', 'infinite', params ?? {}] as const,
    documents: (params?: QueryParams) => ['search', 'documents', params ?? {}] as const,
    infiniteDocuments: (params?: QueryParams) =>
      ['search', 'documents', 'infinite', params ?? {}] as const,
  },
  // Filter choices and the labels of selections that arrived through a link.
  filterOptions: {
    all: ['people-filter-options'] as const,
    kind: (kind: string) => ['people-filter-options', kind] as const,
  },
  sourceLabels: {
    all: ['filter-source-labels'] as const,
    selection: (kind: string, ids: string[]) => ['filter-source-labels', kind, ids] as const,
  },
  actorLabels: {
    all: ['filter-actor-labels'] as const,
    kind: (kind: string) => ['filter-actor-labels', kind] as const,
    actor: (kind: string, id: string) => ['filter-actor-labels', kind, id] as const,
  },
  translations: {
    all: ['translations'] as const,
    detail: (text: string, language: string) => ['translations', text, language] as const,
  },
} as const
