import { onScopeDispose, ref } from 'vue'

/** Reactive wall clock for ageing relative labels without refetching data. */
export function useNow(intervalMs = 30_000) {
  const now = ref(new Date())
  const timer = setInterval(() => {
    now.value = new Date()
  }, intervalMs)
  onScopeDispose(() => clearInterval(timer))
  return now
}
