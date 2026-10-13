import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet,
  getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet,
} from '@/client'
import type { EntityLinkState } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export function fetchPageLayout(sourceId: string, signal?: AbortSignal) {
  return responseData(
    getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet({
      path: { page_source_id: sourceId },
      signal,
      throwOnError: true,
    }),
  )
}

export function usePageLayoutQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.layout(toValue(sourceId))),
    queryFn: ({ signal }) => fetchPageLayout(toValue(sourceId), signal),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function fetchPageMentionSpans(sourceId: string, signal?: AbortSignal, states: EntityLinkState[] = []) {
  return responseData(
    getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet({
      query: { 'filter.entity_link_state': states.length ? states : undefined },
      path: { page_source_id: sourceId },
      signal,
      throwOnError: true,
    }),
  )
}

export function usePageMentionSpansQuery(sourceId: MaybeRefOrGetter<string>, states: MaybeRefOrGetter<EntityLinkState[]> = []) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.mentionSpans(toValue(sourceId), toValue(states))),
    queryFn: ({ signal }) => fetchPageMentionSpans(toValue(sourceId), signal, toValue(states)),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}
