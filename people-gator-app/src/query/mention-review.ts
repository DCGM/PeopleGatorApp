import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch,
  type TextMentionResponse,
} from '@/client'
import { responseData } from './api'
import { fetchTextMentions, type TextMentionListParams } from './text-mentions'
import { queryKeys } from './keys'
import { restartPeoplePages } from './people-count-invalidation'

export type MentionReviewTargets =
  | { items: { id: string; version: number }[] }
  | {
      scopes: TextMentionListParams[]
      items?: { id: string; version: number }[]
      excludeIds?: string[]
      /** Loaded explicit selections already verified; skipped by Verify. */
      verifiedIds?: string[]
    }

/** Resolve every cursor before writes: review can change the active filter itself. */
export async function resolveMentionTargets(
  targets: MentionReviewTargets,
  action: 'verify' | 'unlink' = 'unlink',
  versions?: Map<string, number>,
  selectedRecords?: Map<string, TextMentionResponse>,
) {
  if (!('scopes' in targets)) {
    for (const item of targets.items) versions?.set(item.id, item.version)
    return [...new Set(targets.items.map((item) => item.id))]
  }
  const records = new Map<string, TextMentionResponse>()
  for (const scope of targets.scopes) {
    let cursor: string | null = null
    do {
      const page = await fetchTextMentions({ ...scope, limit: 100, cursor })
      for (const record of page.items) {
        records.set(record.mention_id, record)
        selectedRecords?.set(record.mention_id, record)
        versions?.set(record.mention_id, record.version)
      }
      cursor = page.cursor ?? null
    } while (cursor)
  }
  for (const item of targets.items ?? []) versions?.set(item.id, item.version)
  const excluded = new Set(targets.excludeIds)
  // Verify reports changed occurrences: already-verified records are no-ops.
  if (action === 'verify') {
    for (const [id, record] of records)
      if (record.entity_link_state === 'verified') excluded.add(id)
    for (const id of targets.verifiedIds ?? []) excluded.add(id)
  }
  return [...new Set([...records.keys(), ...(targets.items ?? []).map((item) => item.id)])].filter(
    (id) => !excluded.has(id),
  )
}

export function useReviewMentionsMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({
      targets,
      action,
    }: {
      targets: { items: { id: string; version: number }[] }
      action: 'verify' | 'unlink'
    }) => {
      const versions = new Map(targets.items.map(({ id, version }) => [id, version]))
      const ids = [...versions.keys()]
      let completed = 0
      try {
        // Stay below the API's default batch limit and report confirmed chunks on failure.
        for (let index = 0; index < ids.length; index += 50) {
          const records = await responseData(
            patchTextMentionBatchRouteApiV1TextMentionsBatchPatch({
              body: ids.slice(index, index + 50).map((mention_id) => ({
                mention_id,
                version: versions.get(mention_id)!,
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
      restartPeoplePages(client)
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
