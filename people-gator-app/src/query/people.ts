import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getPersonRouteApiV1PeopleEntityIdGet,
  listPeopleRouteApiV1PeopleGet,
  patchPersonRouteApiV1PeopleEntityIdPatch,
  searchPeopleGetApiV1SearchPeopleGet,
  type ListPeopleRouteApiV1PeopleGetData,
  type PersonPatchRequest,
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
