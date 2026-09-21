import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { translateRouteApiV1TranslatePost, type Language, type TranslationResponse } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export function fetchTranslation(text: string, language: Language, signal?: AbortSignal) {
  return responseData(
    translateRouteApiV1TranslatePost({
      body: { text, language },
      signal,
      throwOnError: true,
    }),
  ) as Promise<TranslationResponse>
}

export function useTranslationQuery(
  text: MaybeRefOrGetter<string>,
  language: MaybeRefOrGetter<Language>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.translations.detail(toValue(text), toValue(language))),
    queryFn: ({ signal }) => fetchTranslation(toValue(text), toValue(language), signal),
    enabled: computed(() => toValue(enabled) && Boolean(toValue(text).trim())),
    staleTime: 5 * 60_000,
  })
}
