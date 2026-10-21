import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { fetchDocuments } from '@/query/media'
import { queryValues, type SharedQuery } from './shared-filters'

/**
 * Older scan links scoped `document` by archive document UUID within `library`.
 * The shared `document` value is an internal registered document UUID, so archive
 * IDs of registered documents are replaced in the URL. Archive IDs without a
 * registered document stay unresolved and cannot broaden a canonical selection.
 * Breadcrumbs use an explicit scans-only archive_document scope for pages
 * registered before their parent document.
 */
export function useDocumentScopeResolution() {
  const route = useRoute(),
    router = useRouter()
  const values = computed(() => queryValues(route.query.document))
  const archives = computed(() => queryValues(route.query.archive_document))
  const libraries = computed(() => queryValues(route.query.library))
  const query = useQuery({
    queryKey: computed(() => ['document-scope', values.value, archives.value, libraries.value]),
    queryFn: async ({ signal }) => {
      const registered = values.value.length
        ? await fetchDocuments(
            { 'filter.source_id': values.value, limit: values.value.length },
            signal,
          )
        : { items: [] }
      const known = new Set(registered.items.map((item) => item.source_id))
      const unknown = [
        ...new Set([...values.value.filter((value) => !known.has(value)), ...archives.value]),
      ]
      const archive =
        unknown.length && libraries.value.length
          ? await fetchDocuments(
              {
                'filter.library': libraries.value,
                'filter.document_id': unknown,
                limit: 100,
              },
              signal,
            )
          : { items: [] }
      const replacements = new Map<string, string[]>()
      for (const item of archive.items)
        replacements.set(item.document_id, [
          ...(replacements.get(item.document_id) ?? []),
          item.source_id,
        ])
      return { replacements, unregistered: unknown.filter((value) => !replacements.has(value)) }
    },
    enabled: computed(() => values.value.length + archives.value.length > 0),
    staleTime: 60_000,
  })
  watch(
    () => query.data.value,
    (data) => {
      if (!data?.replacements.size) return
      const document = [
        ...values.value.flatMap((value) => data.replacements.get(value) ?? [value]),
        ...archives.value.flatMap((value) => data.replacements.get(value) ?? []),
      ]
      const remaining = archives.value.filter((value) => !data.replacements.has(value))
      void router.replace({
        query: {
          ...route.query,
          document: [...new Set(document)].sort(),
          archive_document: remaining.length ? remaining : undefined,
        },
      })
    },
  )
  const unregistered = computed(() =>
    archives.value.filter((value) => query.data.value?.unregistered.includes(value)),
  )
  return {
    unregistered,
    error: query.error,
    retry: () => query.refetch(),
    resolving: computed(
      () => values.value.length + archives.value.length > 0 && query.isPending.value,
    ),
    /** Shared criteria with unregistered archive IDs moved to their archive scope. */
    apply(shared: MaybeRefOrGetter<SharedQuery>) {
      return computed(() => {
        const params: SharedQuery & { 'filter.document_id'?: string[] } = { ...toValue(shared) }
        if (!unregistered.value.length) return params
        params['filter.document_id'] = unregistered.value
        return params
      })
    },
  }
}
