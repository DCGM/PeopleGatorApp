import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getMeRouteApiV1MeGet,
  getUserRouteApiV1UsersUserIdGet,
  listUsersRouteApiV1UsersGet,
  patchUserRouteApiV1UsersUserIdPatch,
  type ListUsersRouteApiV1UsersGetData,
  type UserPatchRequest,
} from '@/client'
import { responseData } from '@/query/api'
import { initialCursor, nextCursor, withCursor } from '@/query/cursor'
import { queryKeys } from '@/query/keys'

export type UserListParams = NonNullable<ListUsersRouteApiV1UsersGetData['query']>

export function useMeQuery() {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: ({ signal }) => responseData(getMeRouteApiV1MeGet({ signal, throwOnError: true })),
  })
}

export function useUserListQuery(
  params?: MaybeRefOrGetter<UserListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.users.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) =>
      responseData(
        listUsersRouteApiV1UsersGet({
          query: withCursor(toValue(params), pageParam),
          signal,
          throwOnError: true,
        }),
      ),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useUserQuery(userId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.users.detail(toValue(userId))),
    queryFn: ({ signal }) =>
      responseData(
        getUserRouteApiV1UsersUserIdGet({
          path: { user_id: toValue(userId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(userId))),
  })
}

export function usePatchUserMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, body }: { userId: string; body: UserPatchRequest }) =>
      responseData(
        patchUserRouteApiV1UsersUserIdPatch({
          path: { user_id: userId },
          body,
          throwOnError: true,
        }),
      ),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.users.detail(user.user_id), user)
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.all })
    },
  })
}
