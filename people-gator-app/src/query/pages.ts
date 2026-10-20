import type { EvidenceQuery } from '@/viewmodels/evidence-filters'
import { useQuery } from '@tanstack/vue-query'
import { isAxiosError } from 'axios'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet,
  getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet,
} from '@/client'
import type { EntityLinkState } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export async function fetchPageLayout(sourceId: string, signal?: AbortSignal) {
  try {
    return await responseData(
      getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet({
        path: { page_source_id: sourceId },
        signal,
        throwOnError: true,
      }),
    )
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export function usePageLayoutQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.layout(toValue(sourceId))),
    queryFn: ({ signal }) => fetchPageLayout(toValue(sourceId), signal),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export async function fetchPageMentionSpans(
  sourceId: string,
  signal?: AbortSignal,
  states: EntityLinkState[] = [],
  evidence: EvidenceQuery = {},
) {
  try {
    return await responseData(
      getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet({
        query: { ...evidence, 'filter.entity_link_state': states.length ? states : undefined },
        path: { page_source_id: sourceId },
        signal,
        throwOnError: true,
      }),
    )
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 404) return []
    throw error
  }
}

export function usePageMentionSpansQuery(
  sourceId: MaybeRefOrGetter<string>,
  states: MaybeRefOrGetter<EntityLinkState[]> = [],
  evidence: MaybeRefOrGetter<EvidenceQuery> = {},
) {
  return useQuery({
    queryKey: computed(() => [
      ...queryKeys.pages.mentionSpans(toValue(sourceId), toValue(states)),
      toValue(evidence),
    ]),
    queryFn: ({ signal }) =>
      fetchPageMentionSpans(toValue(sourceId), signal, toValue(states), toValue(evidence)),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}
