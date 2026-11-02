import { computed, ref, watch, type Ref } from 'vue'
import { isAxiosError } from 'axios'
import { useHasScope } from '@/composables/can-annotate'
import { addSelectionRange } from '@/lib/range-selection'
import { fetchEntity, useMergeEntitiesMutation } from '@/query/entities'

type Person = { id: string; name: string }

export function usePeopleMerge(people: Ref<Person[]>, scope: Ref<string>, loading: Ref<boolean>) {
  const allowed = useHasScope('people-gator:admin')
  const mutation = useMergeEntitiesMutation()
  const selectedIds = ref(new Set<string>())
  const anchor = ref<string | null>(null)
  const busy = ref(false)
  const message = ref('')
  const selected = computed(() => {
    const available = new Map(people.value.map((person) => [person.id, person]))
    return [...selectedIds.value].flatMap((id) => (available.has(id) ? [available.get(id)!] : []))
  })
  function clear() {
    if (busy.value) return
    selectedIds.value = new Set()
    anchor.value = null
    message.value = ''
  }
  function toggle(id: string, event: { shiftKey: boolean }) {
    if (!allowed.value || busy.value || loading.value || !people.value.some((p) => p.id === id))
      return
    const range =
      event.shiftKey &&
      addSelectionRange(
        selectedIds.value,
        people.value.map((p) => p.id),
        anchor.value,
        id,
      )
    if (range) selectedIds.value = range
    else {
      const next = new Set(selectedIds.value)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      selectedIds.value = next
      anchor.value = id
    }
    message.value = ''
  }
  watch(scope, clear, { flush: 'sync' })
  watch(allowed, (value) => {
    if (!value) clear()
  })
  watch([people, loading, busy], () => {
    if (loading.value || busy.value) return
    const available = new Set(people.value.map((p) => p.id))
    selectedIds.value = new Set([...selectedIds.value].filter((id) => available.has(id)))
    if (anchor.value && !available.has(anchor.value)) anchor.value = null
  })
  async function merge(which: 'first' | 'last') {
    if (!allowed.value || busy.value || loading.value || selected.value.length < 2) return
    const snapshot = selected.value.map((person) => person.id)
    const targetEntityId = which === 'first' ? snapshot[0]! : snapshot[snapshot.length - 1]!
    const sourceEntityIds = snapshot.filter((id) => id !== targetEntityId)
    busy.value = true
    message.value = ''
    const requestScope = scope.value
    try {
      await mutation.mutateAsync({ targetEntityId, sourceEntityIds })
      selectedIds.value = new Set()
      anchor.value = null
      message.value = 'People merged.'
    } catch (error) {
      const status = isAxiosError(error) ? error.response?.status : undefined
      message.value =
        status === 403
          ? 'Merge requires admin permission. Check your access and try again.'
          : status === 404
            ? 'A selected person is unavailable. Review the remaining selection and try again.'
            : status === 409 || status === 422
              ? 'These people could not be merged. Review the selection and try again.'
              : 'Merge failed. Check your connection and try again.'
      if (status === 404) {
        // Only confirmed missing records are removed; network failures retain selection.
        const checks = await Promise.allSettled(snapshot.map((id) => fetchEntity(id)))
        checks.forEach((result, index) => {
          if (
            result.status === 'rejected' &&
            isAxiosError(result.reason) &&
            result.reason.response?.status === 404
          )
            selectedIds.value.delete(snapshot[index]!)
        })
        selectedIds.value = new Set(selectedIds.value)
      }
    } finally {
      busy.value = false
      if (requestScope !== scope.value) clear()
    }
  }
  return { allowed, selectedIds, selected, busy, message, clear, toggle, merge }
}
