import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch,
  type TextMentionResponse,
} from '@/client'
import { responseData } from './api'
import { fetchTextMentions, type TextMentionListParams } from './text-mentions'
import { queryKeys } from './keys'

export type MentionReviewTargets =
  { ids: string[] } | { scopes: TextMentionListParams[]; ids?: string[]; excludeIds?: string[] }

/** Resolve every cursor before writes: review can change the active filter itself. */
export async function resolveMentionTargets(targets: MentionReviewTargets) {
  if (!('scopes' in targets)) return [...new Set(targets.ids)]
  const records = new Map<string, TextMentionResponse>()
  for (const scope of targets.scopes) {
    let cursor: string | null = null
    do {
      const page = await fetchTextMentions({ ...scope, limit: 100, cursor })
      for (const record of page.items) records.set(record.mention_id, record)
      cursor = page.cursor ?? null
    } while (cursor)
  }
  const excluded = new Set(targets.excludeIds)
  return [...new Set([...records.keys(), ...(targets.ids ?? [])])].filter((id) => !excluded.has(id))
}

export function useReviewMentionsMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({
      targets,
      action,
    }: {
      targets: MentionReviewTargets
      action: 'verify' | 'unlink'
    }) => {
      const ids = await resolveMentionTargets(targets)
      let completed = 0
      try {
        // Stay below the API's default batch limit and report confirmed chunks on failure.
        for (let index = 0; index < ids.length; index += 50) {
          const records = await responseData(
            patchTextMentionBatchRouteApiV1TextMentionsBatchPatch({
              body: ids.slice(index, index + 50).map((mention_id) => ({
                mention_id,
                ...(action === 'verify'
                  ? { entity_link_state: 'verified' as const }
                  : { entity_id: null, entity_link_state: null }),
              })),
              throwOnError: true,
            }),
          )
          completed += records.filter(Boolean).length
          if (records.some((record) => !record)) throw new Error('Mention unavailable')
        }
      } catch {
        throw new Error(
          `${completed} of ${ids.length} updates confirmed. Review refreshed results before retrying.`,
        )
      }
      return completed
    },
    onSettled: async () => {
      await Promise.all(
        [
          queryKeys.textMentions.all,
          queryKeys.entities.all,
          queryKeys.pages.all,
          queryKeys.documents.all,
          queryKeys.sources.all,
          queryKeys.search.all,
        ].map((queryKey) => client.invalidateQueries({ queryKey })),
      )
    },
  })
}
