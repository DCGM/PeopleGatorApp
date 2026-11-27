import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getPersonRouteApiV1PeopleEntityIdGet,
  listPeopleRouteApiV1PeopleGet,
  patchPersonRouteApiV1PeopleEntityIdPatch,
  putPersonRouteApiV1PeopleEntityIdPut,
  searchPeopleGetApiV1SearchPeopleGet,
  type ListPeopleRouteApiV1PeopleGetData,
  type PersonCreateRequest,
  type PersonPatchRequest,
  type PersonResponse,
  type SearchPeopleGetApiV1SearchPeopleGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { invalidateEntityRecords } from './invalidation'

/** Typed person API (#123): names, life dates and their filters/sorts live only here. */
export type PeopleListParams = NonNullable<ListPeopleRouteApiV1PeopleGetData['query']>
export type PeopleSearchParams = NonNullable<SearchPeopleGetApiV1SearchPeopleGetData['query']>

export function fetchPeople(params?: PeopleListParams, signal?: AbortSignal) {
  return responseData(listPeopleRouteApiV1PeopleGet({ query: params, signal, throwOnError: true }))
}

export function searchPeople(params: PeopleSearchParams, signal?: AbortSignal) {
  return responseData(
    searchPeopleGetApiV1SearchPeopleGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchPerson(entityId: string, signal?: AbortSignal) {
  return responseData(
    getPersonRouteApiV1PeopleEntityIdGet({
      path: { entity_id: entityId },
      signal,
      throwOnError: true,
    }),
  )
}

export function usePersonQuery(entityId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.entities.person(toValue(entityId))),
    queryFn: ({ signal }) => fetchPerson(toValue(entityId), signal),
    enabled: computed(() => Boolean(toValue(entityId))),
  })
}

export function usePatchPersonMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entityId, body }: { entityId: string; body: PersonPatchRequest }) =>
      responseData(
        patchPersonRouteApiV1PeopleEntityIdPatch({
          path: { entity_id: entityId },
          body,
          throwOnError: true,
        }),
      ),
    onSuccess: (person) => {
      queryClient.setQueryData(queryKeys.entities.person(person.entity_id), person)
      // The shared entity record is a subset of the person record.
      queryClient.setQueryData(queryKeys.entities.detail(person.entity_id), person)
      void invalidateEntityRecords(queryClient)
    },
  })
}

/** Cache updates after a person record is created or replaced. */
function storePerson(queryClient: ReturnType<typeof useQueryClient>, person: PersonResponse) {
  queryClient.setQueryData(queryKeys.entities.person(person.entity_id), person)
  queryClient.setQueryData(queryKeys.entities.detail(person.entity_id), person)
  void invalidateEntityRecords(queryClient)
}

/**
 * Create or replace the person with a client-chosen UUID (#173). Repeating the
 * same request is idempotent, so a retry never creates a second person.
 */
export function usePutPersonMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entityId, body }: { entityId: string; body: PersonCreateRequest }) =>
      responseData(
        putPersonRouteApiV1PeopleEntityIdPut({
          path: { entity_id: entityId },
          body,
          throwOnError: true,
        }),
      ),
    onSuccess: (person) => storePerson(queryClient, person),
  })
}
