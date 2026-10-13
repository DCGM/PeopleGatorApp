import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  patchFaceRouteApiV1FacesDetectionIdPatch,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch,
} from '@/client'
import { responseData } from './api'
import { queryKeys } from './keys'
export function useVerifyLinkMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({ kind, id }: { kind: 'face' | 'mention'; id: string }) =>
      kind === 'face'
        ? responseData(
            patchFaceRouteApiV1FacesDetectionIdPatch({
              path: { detection_id: id },
              body: { entity_link_state: 'verified' },
              throwOnError: true,
            }),
          )
        : responseData(
            patchTextMentionRouteApiV1TextMentionsMentionIdPatch({
              path: { mention_id: id },
              body: { entity_link_state: 'verified' },
              throwOnError: true,
            }),
          ),
    onSuccess: async () => {
      await Promise.all(
        [
          queryKeys.faces.all,
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
