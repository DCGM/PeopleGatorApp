import { partialMatchKey, type QueryClient, type QueryKey } from '@tanstack/vue-query'

import { queryKeys } from './keys'
import { restartPeoplePages } from './people-count-invalidation'

/**
 * Cache relationships maintained by mutations (#74).
 *
 * - Evidence (faces, mentions, their links) feeds people, page/document/source
 *   counts and every search result.
 * - Entity records feed the same views through names and portraits.
 * - Media deletion cascades to evidence and touches the affected people, and
 *   media changes alter the document/page filter choices and selected labels.
 * - A user's name appears in user choices and selected actor labels.
 *
 * Image bytes (`pageImages`, `imageContents`, `faceCrops`) are immutable and
 * live outside these groups, so no edit downloads them again.
 */
const EVIDENCE_VIEWS = [
  queryKeys.faces.all,
  queryKeys.textMentions.all,
  queryKeys.pages.all,
  queryKeys.documents.all,
  queryKeys.sources.all,
  queryKeys.images.all,
  queryKeys.search.all,
] as const

/**
 * Refresh every query under the given key prefixes exactly once. A key already
 * covered by another prefix is dropped: invalidating both would cancel and
 * restart the same refetch.
 */
export function invalidateOnce(client: QueryClient, groups: readonly QueryKey[]) {
  const disjoint = groups.filter(
    (key, index) =>
      !groups.some(
        (other, otherIndex) =>
          otherIndex !== index &&
          partialMatchKey(key, other) &&
          (other.length < key.length || otherIndex < index),
      ),
  )
  return Promise.all(disjoint.map((queryKey) => client.invalidateQueries({ queryKey })))
}

/** Faces, mentions or their links changed, or people were merged or removed. */
export function invalidateEvidence(client: QueryClient) {
  restartPeoplePages(client)
  return invalidateOnce(client, [queryKeys.entities.all, ...EVIDENCE_VIEWS])
}

/**
 * An entity record changed and the caller already stored its detail: refresh
 * entity lists, the views naming the entity and any `extra` keys.
 */
export function invalidateEntityRecords(client: QueryClient, extra: readonly QueryKey[] = []) {
  restartPeoplePages(client)
  return invalidateOnce(client, [queryKeys.entities.lists(), ...EVIDENCE_VIEWS, ...extra])
}

/** Documents, pages, images or sources were created or deleted. */
export function invalidateMedia(client: QueryClient) {
  restartPeoplePages(client)
  return invalidateOnce(client, [
    queryKeys.entities.all,
    ...EVIDENCE_VIEWS,
    queryKeys.filterOptions.kind('library'),
    queryKeys.filterOptions.kind('document'),
    queryKeys.filterOptions.kind('page'),
    queryKeys.sourceLabels.all,
  ])
}

/** A user record changed, including its display name. */
export function invalidateUsers(client: QueryClient) {
  return invalidateOnce(client, [
    queryKeys.users.all,
    queryKeys.auth.all,
    queryKeys.filterOptions.kind('user'),
    queryKeys.actorLabels.kind('user'),
  ])
}
