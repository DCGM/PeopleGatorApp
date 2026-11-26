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
import { restartPeoplePages } from './people-count-invalidation'

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
      restartPeoplePages(queryClient)
      queryClient.setQueryData(queryKeys.entities.person(person.entity_id), person)
      // The shared entity record is a subset of the person record.
      queryClient.setQueryData(queryKeys.entities.detail(person.entity_id), person)
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.images.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
    },
  })
}

/** Cache updates after a person record is created or replaced. */
function storePerson(queryClient: ReturnType<typeof useQueryClient>, person: PersonResponse) {
  restartPeoplePages(queryClient)
  queryClient.setQueryData(queryKeys.entities.person(person.entity_id), person)
  queryClient.setQueryData(queryKeys.entities.detail(person.entity_id), person)
  for (const queryKey of [
    queryKeys.entities.lists(),
    queryKeys.search.all,
    queryKeys.documents.all,
    queryKeys.sources.all,
    queryKeys.images.all,
    queryKeys.pages.all,
    queryKeys.faces.all,
    queryKeys.textMentions.all,
  ])
    void queryClient.invalidateQueries({ queryKey })
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
