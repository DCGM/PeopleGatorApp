import { COUNT_OPTIONS } from './annotation-counts'
import type {
  DocumentSortField,
  EntitySortField,
  FaceSortField,
  PageSortField,
  TextMentionGroupSortField,
  TextMentionSortField,
} from '@/client'
import type { SortOption, SortState, SortUrlKeys } from '@/lib/sorting'

/**
 * Sort fields per browsable list (#33). Every option is an API sort applied to
 * the complete result set before pagination; none reorders only loaded cards.
 */
export const RELEVANCE: SortState<'relevance'> = { field: 'relevance', direction: 'desc' }

export const PEOPLE_SORTS: SortOption<EntitySortField>[] = [
  { value: 'faces_total_count', label: 'Faces', kind: 'number' },
  { value: 'mentions_total_count', label: 'Text mentions', kind: 'number' },
  { value: 'annotations_total_count', label: 'All annotations', kind: 'number' },
  { value: 'relevance', label: 'Relevance', kind: 'relevance' },
  { value: 'name', label: 'Name', kind: 'text' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
  { value: 'created_at', label: 'Created / imported', kind: 'time' },
  { value: 'entity_id', label: 'Person ID', kind: 'id' },
]
export const PEOPLE_BROWSE_DEFAULT: SortState<EntitySortField> = { field: 'name', direction: 'asc' }

export const DOCUMENT_SORTS: SortOption<DocumentSortField>[] = [
  { value: 'relevance', label: 'Relevance', kind: 'relevance' },
  { value: 'name', label: 'Name', kind: 'text' },
  { value: 'library', label: 'Library', kind: 'text' },
  { value: 'document_id', label: 'Document ID', kind: 'id' },
  { value: 'page_count', label: 'Pages', kind: 'number' },
  { value: 'last_touched_at', label: 'Last processing', kind: 'time' },
  ...COUNT_OPTIONS,
]
export const DOCUMENT_BROWSE_DEFAULT: SortState<DocumentSortField> = {
  field: 'name',
  direction: 'asc',
}

export const PAGE_SORTS: SortOption<PageSortField>[] = [
  { value: 'page_number', label: 'Page number', kind: 'number' },
  { value: 'relevance', label: 'Relevance', kind: 'relevance' },
  { value: 'library', label: 'Library', kind: 'text' },
  { value: 'document_id', label: 'Document ID', kind: 'id' },
  { value: 'page_id', label: 'Page ID', kind: 'id' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
  ...COUNT_OPTIONS,
]
export const PAGE_BROWSE_DEFAULT: SortState<PageSortField> = { field: 'library', direction: 'asc' }

/** The gallery holds one document, so library/document order adds nothing. */
export const GALLERY_SORTS: SortOption<PageSortField>[] = [
  { value: 'page_number', label: 'Page number', kind: 'number' },
  { value: 'page_id', label: 'Page ID', kind: 'id' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
  ...COUNT_OPTIONS,
]
export const GALLERY_DEFAULT: SortState<PageSortField> = { field: 'page_number', direction: 'asc' }
export const GALLERY_SORT_KEYS: SortUrlKeys = { field: 'gallery_sort', direction: 'gallery_dir' }

export const FACE_SORTS: SortOption<FaceSortField>[] = [
  { value: 'relevance', label: 'Similarity', kind: 'relevance' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
  { value: 'link_state', label: 'Assignment', kind: 'state' },
  { value: 'confidence', label: 'Confidence', kind: 'number' },
  { value: 'source', label: 'Source', kind: 'text' },
  { value: 'detection_id', label: 'Face ID', kind: 'id' },
]
/** A page workspace lists one source, so source order adds nothing. */
export const WORKSPACE_FACE_SORTS: SortOption<FaceSortField>[] = FACE_SORTS.filter(
  (option) => option.value !== 'relevance' && option.value !== 'source',
)
export const FACE_DEFAULT: SortState<FaceSortField> = { field: 'detection_id', direction: 'asc' }
export const FACE_SORT_KEYS: SortUrlKeys = { field: 'face_sort', direction: 'face_dir' }
export const DISCOVERY_FACE_SORT_KEYS: SortUrlKeys = {
  field: 'similar_sort',
  direction: 'similar_dir',
}

export const MENTION_SORTS: SortOption<TextMentionSortField>[] = [
  { value: 'text', label: 'Text', kind: 'text' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
  { value: 'link_state', label: 'Assignment', kind: 'state' },
  { value: 'source', label: 'Source', kind: 'text' },
  { value: 'mention_id', label: 'Mention ID', kind: 'id' },
]
export const MENTION_DEFAULT: SortState<TextMentionSortField> = { field: 'text', direction: 'asc' }
export const MENTION_SORT_KEYS: SortUrlKeys = { field: 'mention_sort', direction: 'mention_dir' }

export const MENTION_GROUP_SORTS: SortOption<TextMentionGroupSortField>[] = [
  { value: 'text', label: 'Text', kind: 'text' },
  { value: 'count', label: 'Occurrences', kind: 'number' },
  { value: 'last_touched_at', label: 'Last change', kind: 'time' },
]
export const MENTION_GROUP_DEFAULT: SortState<TextMentionGroupSortField> = {
  field: 'text',
  direction: 'asc',
}
export const MENTION_GROUP_SORT_KEYS: SortUrlKeys = { field: 'group_sort', direction: 'group_dir' }

export const SIMILAR_PEOPLE_SORT_KEYS: SortUrlKeys = {
  field: 'people_sort',
  direction: 'people_dir',
}
export const CANDIDATE_SORT_KEYS: SortUrlKeys = {
  field: 'candidate_sort',
  direction: 'candidate_dir',
}

/** Relevance needs a score; browse lists offer every other field. */
export function scoredOptions<Field extends string>(
  options: readonly SortOption<Field>[],
  scored: boolean,
): SortOption<Field>[] {
  return scored ? [...options] : options.filter((option) => option.value !== 'relevance')
}
