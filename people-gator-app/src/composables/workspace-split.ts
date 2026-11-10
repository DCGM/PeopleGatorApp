import { nextTick, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'

type Direction = 'horizontal' | 'vertical'
export type WorkspacePanel = {
  getSize: () => number
  resize: (size: number) => void
  collapse?: () => void
}
const STORAGE_KEY = 'document-workspace-layouts-v1'

function validSize(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 15 && value <= 70
}

/** Restore each orientation explicitly, without remounting either panel. */
export function useWorkspaceSplit(
  direction: Ref<Direction>,
  panel: Ref<WorkspacePanel | null>,
  visible: MaybeRefOrGetter<boolean> = true,
) {
  const sizes: Record<Direction, number> = { horizontal: 40, vertical: 30 }
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    for (const mode of ['horizontal', 'vertical'] as const) {
      if (validSize(stored?.[mode])) sizes[mode] = stored[mode]
      else {
        // Retain sizes saved by the earlier, orientation-keyed splitter.
        const legacy = JSON.parse(localStorage.getItem(`reka:document-workspace-${mode}`) ?? '{}')
        const state = Object.values(legacy).find((value) =>
          validSize((value as { layout?: number[] })?.layout?.[0]),
        ) as { layout: number[] } | undefined
        if (state) sizes[mode] = state.layout[0]!
      }
    }
  } catch {
    // Blocked storage and invalid settings must not prevent opening a scan.
  }
  const defaultSize = sizes[direction.value]
  let restoring = false
  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sizes))
    } catch {
      // The layout still works when storage is unavailable.
    }
  }
  function layoutChanged(layout: number[]) {
    if (!toValue(visible) || restoring || !validSize(layout[0])) return
    sizes[direction.value] = layout[0]
    save()
  }
  watch([direction, () => toValue(visible)], async ([value, shown], [previous], onCleanup) => {
    let cancelled = false
    onCleanup(() => {
      cancelled = true
    })
    // Save before the direction change reaches the DOM. The splitter does not
    // reload auto-save settings or defaultSize when direction changes in place.
    const departing = panel.value?.getSize?.()
    if (!restoring && shown && validSize(departing)) sizes[previous] = departing
    if (!shown) return
    restoring = true
    await nextTick()
    if (cancelled) return
    panel.value?.resize?.(sizes[value])
    restoring = false
    save()
  })
  return { defaultSize, layoutChanged }
}

const SIDEBAR_STORAGE_KEY = 'document-sidebar-width-v1'
export const SIDEBAR_WIDTH = { default: 400, min: 320, max: 800 }

function validWidth(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= SIDEBAR_WIDTH.min &&
    value <= SIDEBAR_WIDTH.max
  )
}

/**
 * The scan sidebar's width in pixels, resizable only on wide screens. Narrow
 * layouts stack the sidebar, so their splitter sizes are neither saved nor kept.
 */
export function useSidebarWidth(
  wide: Ref<boolean>,
  panel: Ref<WorkspacePanel | null>,
  visible: MaybeRefOrGetter<boolean> = true,
) {
  let width = SIDEBAR_WIDTH.default
  try {
    const stored = JSON.parse(localStorage.getItem(SIDEBAR_STORAGE_KEY) ?? 'null')
    if (validWidth(stored)) width = stored
  } catch {
    // Blocked storage and invalid settings must not prevent opening a scan.
  }
  const defaultSize = width
  let restoring = false
  function layoutChanged(layout: number[]) {
    // Pixel sizes arrive converted from percentages, e.g. 319.99 at the minimum.
    const next = Math.round(layout[1] ?? Number.NaN)
    if (!toValue(visible) || !wide.value || restoring || !validWidth(next)) return
    width = next
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, JSON.stringify(width))
    } catch {
      // The layout still works when storage is unavailable.
    }
  }
  watch([wide, () => toValue(visible)], async ([value, shown], _previous, onCleanup) => {
    restoring = value && shown
    if (!value || !shown) return
    let cancelled = false
    onCleanup(() => {
      cancelled = true
    })
    // A pixel size converts through the group width, which the splitter only
    // measures after the wide layout has rendered.
    await nextTick()
    for (let frame = 0; frame < 2; frame++)
      await new Promise((resolve) => requestAnimationFrame(resolve))
    if (cancelled) return
    panel.value?.resize?.(width)
    restoring = false
  })
  return { defaultSize, layoutChanged }
}
