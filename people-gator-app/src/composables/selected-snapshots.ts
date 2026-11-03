import { computed, shallowRef, watch, type Ref } from 'vue'

/** Keep the exact selected data through background refetches. */
export function useSelectedSnapshots<T extends { id: string }>(
  ids: Ref<Set<string>>,
  records: () => T[],
) {
  const saved = shallowRef(new Map<string, T>())
  watch(
    ids,
    (selected) => {
      const next = new Map(saved.value)
      for (const id of next.keys()) if (!selected.has(id)) next.delete(id)
      for (const record of records()) {
        if (selected.has(record.id) && !next.has(record.id)) next.set(record.id, { ...record })
      }
      saved.value = next
    },
    { flush: 'sync' },
  )
  return computed(() => [...saved.value.values()])
}
