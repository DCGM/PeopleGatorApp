import type { InfiniteData, QueryClient } from '@tanstack/vue-query'

/** Discard continuation keys after evidence edits before existing invalidation refetches. */
export function restartPeoplePages(client: QueryClient) {
  for (const queryKey of [
    ['entities', 'list', 'infinite'],
    ['search', 'entities', 'infinite'],
  ]) {
    client.setQueriesData<InfiniteData<unknown>>(
      { queryKey },
      (cached) =>
        cached && {
          ...cached,
          pages: cached.pages.slice(0, 1),
          pageParams: cached.pageParams.slice(0, 1),
        },
    )
  }
}
