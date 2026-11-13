import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import type { VerificationState } from '@/client'
import type { DocumentListParams } from '@/query/media'

// Documents-only filter; the shared configuration lives in shared-filters.ts.
export type UnassignedFilter = 'all' | 'yes' | 'no'

export function readUnassigned(query: LocationQuery): UnassignedFilter {
  return query.unassigned === 'yes' ? 'yes' : query.unassigned === 'no' ? 'no' : 'all'
}

export function unassignedQuery(value: UnassignedFilter): DocumentListParams {
  return value === 'all' ? {} : { 'filter.has_unassigned_faces': value === 'yes' }
}

// Derived document verification (#149): verified once every registered page is.
export type VerificationFilter = 'all' | 'verified' | 'not_verified'
export const VERIFICATION_LABELS = { verified: 'Verified', not_verified: 'Not verified' } as const

export function readVerification(query: LocationQuery): VerificationFilter {
  return query.verification === 'verified' || query.verification === 'not_verified'
    ? query.verification
    : 'all'
}

export function verificationQuery(value: VerificationFilter): {
  'filter.verification_state'?: VerificationState[]
} {
  return value === 'all' ? {} : { 'filter.verification_state': [value] }
}

export function useDocumentFilters() {
  const route = useRoute()
  const router = useRouter()
  const searchTerm = computed({
    get: () => (typeof route.query.q === 'string' ? route.query.q : ''),
    set: (q: string) => {
      void router.push({ query: { ...route.query, q: q || undefined } })
    },
  })
  const unassigned = computed({
    get: () => readUnassigned(route.query),
    set: (value: UnassignedFilter) => {
      void router.push({
        query: { ...route.query, unassigned: value === 'all' ? undefined : value },
      })
    },
  })
  const verification = computed({
    get: () => readVerification(route.query),
    set: (value: VerificationFilter) => {
      void router.push({
        query: { ...route.query, verification: value === 'all' ? undefined : value },
      })
    },
  })
  return { searchTerm, unassigned, verification }
}
