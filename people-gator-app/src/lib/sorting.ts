import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'

import type { SortDirection } from '@/client'

export type { SortDirection }

/** How a field reads to people; selects the direction wording. */
export type SortKind = 'text' | 'time' | 'number' | 'id' | 'state' | 'relevance'

export type SortOption<Field extends string = string> = {
  value: Field
  label: string
  kind: SortKind
}

export type SortState<Field extends string = string> = {
  field: Field
  direction: SortDirection
}

/** URL keys for one independently sortable list. */
export type SortUrlKeys = { field: string; direction: string }

export const DEFAULT_SORT_KEYS: SortUrlKeys = { field: 'sort', direction: 'dir' }

const DESCENDING_FIRST = new Set([
  'relevance',
  'last_touched_at',
  'created_at',
  'page_count',
  'count',
])

/** Mirrors the API: newest, largest and best first; otherwise ascending. */
export function defaultDirection(field: string): SortDirection {
  return DESCENDING_FIRST.has(field) ? 'desc' : 'asc'
}

const DIRECTION_LABELS: Record<SortKind, Record<SortDirection, string>> = {
  text: { asc: 'A–Z', desc: 'Z–A' },
  time: { asc: 'Oldest first', desc: 'Newest first' },
  number: { asc: 'Lowest first', desc: 'Highest first' },
  id: { asc: 'Ascending', desc: 'Descending' },
  state: { asc: 'Verified first', desc: 'Automatic first' },
  relevance: { asc: 'Weakest first', desc: 'Best first' },
}

export function directionLabel(kind: SortKind, direction: SortDirection) {
  return DIRECTION_LABELS[kind][direction]
}

export type SortStrategy<Field extends string = string> = SortState<Field> & {
  /** Stable select value, `field:direction`. */
  value: string
  label: string
}

/**
 * Every field in both directions as one selectable strategy, natural direction
 * first, e.g. "Name · A–Z", "Name · Z–A", "Last change · Newest first".
 */
export function sortStrategies<Field extends string>(
  options: readonly SortOption<Field>[],
): SortStrategy<Field>[] {
  return options.flatMap((option) => {
    const natural = defaultDirection(option.value)
    return ([natural, natural === 'asc' ? 'desc' : 'asc'] as const).map((direction) => ({
      field: option.value,
      direction,
      value: `${option.value}:${direction}`,
      label: `${option.label} · ${directionLabel(option.kind, direction)}`,
    }))
  })
}

/**
 * Read one list's sort from the URL. Unknown fields, including Relevance when
 * no score exists, recover to the list's default with truthful controls.
 */
export function readSort<Field extends string>(
  query: LocationQuery,
  keys: SortUrlKeys,
  options: readonly SortOption<Field>[],
  fallback: SortState<Field>,
): SortState<Field> {
  const raw = query[keys.field]
  const field = options.find((option) => option.value === raw)?.value
  if (!field) return fallback
  const direction = query[keys.direction]
  return {
    field,
    direction: direction === 'asc' || direction === 'desc' ? direction : defaultDirection(field),
  }
}

/** URL values for a sort; defaults are omitted so links stay short. */
export function sortUrl<Field extends string>(
  state: SortState<Field>,
  fallback: SortState<Field>,
  keys: SortUrlKeys = DEFAULT_SORT_KEYS,
): LocationQueryRaw {
  const isDefault = state.field === fallback.field && state.direction === fallback.direction
  return {
    [keys.field]: isDefault ? undefined : state.field,
    [keys.direction]:
      isDefault || state.direction === defaultDirection(state.field) ? undefined : state.direction,
  }
}

/** API parameters; part of every query key so a new order starts a new sequence. */
export function sortParams<Field extends string>(state: SortState<Field>) {
  return { sort: state.field, sort_direction: state.direction }
}

/** Ordinary-list parameters: Relevance needs a search score and is never sent. */
export function listSortParams<Field extends string>(
  state: SortState<Field>,
): { sort?: Exclude<Field, 'relevance'>; sort_direction?: SortDirection } {
  return state.field === 'relevance'
    ? {}
    : { sort: state.field as Exclude<Field, 'relevance'>, sort_direction: state.direction }
}

/** Keep only URL sort values that can travel to another list with the same meaning. */
export function compatibleSortUrl(
  query: LocationQuery,
  keys: SortUrlKeys,
  options: readonly SortOption[],
): LocationQueryRaw {
  const field = query[keys.field]
  if (!options.some((option) => option.value === field)) return {}
  return { [keys.field]: field, [keys.direction]: query[keys.direction] ?? undefined }
}

/**
 * Route-backed sort for one list. Options may change with context, such as
 * Relevance appearing only while a search query is active. An explicit choice
 * that remains applicable is kept; an inapplicable one resolves to `fallback`.
 */
export function useRouteSort<Field extends string>(
  keys: SortUrlKeys,
  options: MaybeRefOrGetter<readonly SortOption<Field>[]>,
  fallback: MaybeRefOrGetter<SortState<Field>>,
  navigation: 'push' | 'replace' = 'push',
) {
  const route = useRoute()
  const router = useRouter()
  return computed<SortState<Field>>({
    get: () => readSort(route.query, keys, toValue(options), toValue(fallback)),
    set: (state) => {
      void router[navigation]({
        query: { ...route.query, cursor: undefined, ...sortUrl(state, toValue(fallback), keys) },
      })
    },
  })
}
