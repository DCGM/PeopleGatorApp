import { computed, ref } from 'vue'
import { useElementSize } from '@vueuse/core'

export const FACE_GRID_CLASSES =
  'grid grid-cols-[repeat(auto-fill,minmax(min(100%,140px),1fr))] gap-3'

/** Identical portrait tracks and metadata space for linked and found faces. */
export function useFaceGrid() {
  const grid = ref<HTMLElement | null>(null)
  const { width } = useElementSize(grid)
  const columns = computed(() => Math.max(1, Math.floor((width.value + 12) / 152)))
  const style = computed(() => ({
    '--face-card-height': `calc(${Math.max(0, (width.value - (columns.value - 1) * 12) / columns.value)}px + 8rem)`,
  }))
  return { grid, columns, style }
}
