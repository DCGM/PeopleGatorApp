import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { translateRouteApiV1TranslatePost, type Language, type TranslationResponse } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export type TranslationLine = {
  id: string
  text: string
}

export function fetchTranslation(text: string, language: Language, signal?: AbortSignal) {
  return responseData(
    translateRouteApiV1TranslatePost({
      body: { text, language },
      signal,
      throwOnError: true,
    }),
  ) as Promise<TranslationResponse>
}

export function useTranslationsQuery(
  lines: MaybeRefOrGetter<TranslationLine[]>,
  language: MaybeRefOrGetter<Language>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQueries({
    queries: computed(() => {
      const activeLines = toValue(lines)
      const targetLanguage = toValue(language)
      if (!toValue(enabled) || !activeLines.length) return []

      return activeLines.map((line) => ({
        queryKey: queryKeys.translations.detail(line.id, targetLanguage, line.text),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchTranslation(line.text, targetLanguage, signal),
        enabled: Boolean(line.text.trim()),
        staleTime: 5 * 60_000,
      }))
    }),
  })
}
