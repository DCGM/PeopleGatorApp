import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { EntityListParams } from '@/query/entities'

export type PeopleProcessingFilters = {
  touchedFrom: string
  touchedTo: string
  documentIds: string[]
  userIds: string[]
  apiKeyIds: string[]
}

export type ProcessingQueryParams = Pick<
  EntityListParams,
  | 'filter.last_touched_from'
  | 'filter.last_touched_to'
  | 'filter.document_source_id'
  | 'filter.last_touched_by_user_id'
  | 'filter.last_touched_by_api_key_id'
>

export function emptyPeopleFilters(): PeopleProcessingFilters {
  return { touchedFrom: '', touchedTo: '', documentIds: [], userIds: [], apiKeyIds: [] }
}

export function localTimeToUtc(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

export function utcToLocalTime(value: unknown): string {
  if (typeof value !== 'string' || !/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  const seconds = `${pad(date.getSeconds())}.${String(date.getMilliseconds()).padStart(3, '0')}`
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${seconds}`
}

function ids(value: LocationQuery[string] | undefined): string[] {
  const values = Array.isArray(value) ? value : [value]
  return [
    ...new Set(values.filter((v): v is string => typeof v === 'string' && v.length > 0)),
  ].sort()
}

export function readPeopleFilters(query: LocationQuery): PeopleProcessingFilters {
  return {
    touchedFrom: utcToLocalTime(query.touched_from),
    touchedTo: utcToLocalTime(query.touched_to),
    documentIds: ids(query.document),
    userIds: ids(query.touched_by),
    apiKeyIds: ids(query.api_key),
  }
}

export function processingFilterError(filters: PeopleProcessingFilters): string | undefined {
  const from = localTimeToUtc(filters.touchedFrom)
  const to = localTimeToUtc(filters.touchedTo)
  if ((filters.touchedFrom && !from) || (filters.touchedTo && !to))
    return 'Enter a valid date and time.'
  if (from && to && from > to) return 'The start time must be before or equal to the end time.'
  return undefined
}

export function peopleFiltersQuery(filters: PeopleProcessingFilters): ProcessingQueryParams {
  return {
    ...(filters.touchedFrom && { 'filter.last_touched_from': localTimeToUtc(filters.touchedFrom) }),
    ...(filters.touchedTo && { 'filter.last_touched_to': localTimeToUtc(filters.touchedTo) }),
    ...(filters.documentIds.length && {
      'filter.document_source_id': [...filters.documentIds].sort(),
    }),
    ...(filters.userIds.length && {
      'filter.last_touched_by_user_id': [...filters.userIds].sort(),
    }),
    ...(filters.apiKeyIds.length && {
      'filter.last_touched_by_api_key_id': [...filters.apiKeyIds].sort(),
    }),
  }
}

export function peopleFiltersUrl(filters: PeopleProcessingFilters): LocationQueryRaw {
  return {
    ...(filters.touchedFrom && { touched_from: localTimeToUtc(filters.touchedFrom) }),
    ...(filters.touchedTo && { touched_to: localTimeToUtc(filters.touchedTo) }),
    ...(filters.documentIds.length && { document: [...filters.documentIds].sort() }),
    ...(filters.userIds.length && { touched_by: [...filters.userIds].sort() }),
    ...(filters.apiKeyIds.length && { api_key: [...filters.apiKeyIds].sort() }),
  }
}
