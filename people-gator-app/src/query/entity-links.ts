import { readVersion } from './versions'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  patchFaceRouteApiV1FacesDetectionIdPatch,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch,
} from '@/client'
import { responseData } from './api'
import { queryKeys } from './keys'
import { restartPeoplePages } from './people-count-invalidation'
export function useVerifyLinkMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({
      kind,
      id,
      expectedVersion,
    }: {
      kind: 'face' | 'mention'
      id: string
      expectedVersion?: number
    }) =>
      kind === 'face'
        ? responseData(
            patchFaceRouteApiV1FacesDetectionIdPatch({
              path: { detection_id: id },
              body: {
                expected_version: expectedVersion ?? readVersion(client, kind, id),
                entity_link_state: 'verified',
              },
              throwOnError: true,
            }),
          )
        : responseData(
            patchTextMentionRouteApiV1TextMentionsMentionIdPatch({
              path: { mention_id: id },
              body: {
                expected_version: expectedVersion ?? readVersion(client, kind, id),
                entity_link_state: 'verified',
              },
              throwOnError: true,
            }),
          ),
    onSuccess: async () => {
      restartPeoplePages(client)
      await Promise.all(
        [
          queryKeys.faces.all,
          queryKeys.textMentions.all,
          queryKeys.entities.all,
          queryKeys.pages.all,
          queryKeys.documents.all,
          queryKeys.sources.all,
          queryKeys.images.all,
          queryKeys.search.all,
        ].map((queryKey) => client.invalidateQueries({ queryKey })),
      )
    },
  })
}
