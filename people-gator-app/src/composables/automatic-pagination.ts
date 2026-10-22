import { onBeforeUnmount, onMounted, watch, type Ref, type MaybeRefOrGetter, toValue } from 'vue'

type PaginationOptions = {
  target: Ref<HTMLElement | null>
  hasNextPage: MaybeRefOrGetter<boolean>
  isFetching: MaybeRefOrGetter<boolean>
  error: MaybeRefOrGetter<unknown>
  enabled: MaybeRefOrGetter<boolean>
  loadMore: () => Promise<unknown>
}

// Read geometry again after every batch: an IntersectionObserver need not emit
// another notification when the list end stays visible throughout the update.
function isVisible(target: HTMLElement) {
  const rect = target.getBoundingClientRect()
  let top = 0
  let bottom = document.documentElement.clientHeight
  let left = 0
  let right = document.documentElement.clientWidth
  for (let parent = target.parentElement; parent; parent = parent.parentElement) {
    const style = getComputedStyle(parent)
    const bounds = parent.getBoundingClientRect()
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      top = Math.max(top, bounds.top + parent.clientTop)
      bottom = Math.min(bottom, bounds.top + parent.clientTop + parent.clientHeight)
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      left = Math.max(left, bounds.left + parent.clientLeft)
      right = Math.min(right, bounds.left + parent.clientLeft + parent.clientWidth)
    }
  }
  return (
    rect.height > 0 &&
    rect.width > 0 &&
    rect.bottom > top &&
    rect.top < bottom &&
    rect.right > left &&
    rect.left < right
  )
}

export function useAutomaticPagination(options: PaginationOptions) {
  let active = false
  let pending = false
  let frame: number | undefined
  let intersection: IntersectionObserver | undefined
  let resize: ResizeObserver | undefined

  function schedule() {
    if (!active || frame !== undefined) return
    frame = requestAnimationFrame(() => {
      frame = undefined
      void check()
    })
  }

  async function check() {
    if (
      !active ||
      pending ||
      !toValue(options.enabled) ||
      !toValue(options.hasNextPage) ||
      toValue(options.isFetching) ||
      toValue(options.error) ||
      !options.target.value ||
      !isVisible(options.target.value)
    )
      return
    pending = true
    try {
      await options.loadMore()
      schedule()
    } catch {
      // The query owns the error and explicit retry UI. Never retry a rejected
      // request automatically; the next successful query transition rechecks it.
    } finally {
      pending = false
    }
  }

  watch(
    () => [
      toValue(options.enabled),
      toValue(options.hasNextPage),
      toValue(options.isFetching),
      toValue(options.error),
    ],
    schedule,
    { flush: 'post' },
  )
  onMounted(() => {
    active = true
    const target = options.target.value
    if (target) {
      if (typeof IntersectionObserver !== 'undefined') {
        intersection = new IntersectionObserver(schedule)
        intersection.observe(target)
      }
      if (typeof ResizeObserver !== 'undefined') {
        resize = new ResizeObserver(schedule)
        // Includes cards, filter expansion, image loading and responsive reflow.
        for (let parent = target.parentElement; parent; parent = parent.parentElement)
          resize.observe(parent)
      }
    }
    window.addEventListener('scroll', schedule, true)
    window.addEventListener('resize', schedule)
    schedule()
  })
  onBeforeUnmount(() => {
    active = false
    if (frame !== undefined) cancelAnimationFrame(frame)
    intersection?.disconnect()
    resize?.disconnect()
    window.removeEventListener('scroll', schedule, true)
    window.removeEventListener('resize', schedule)
  })
}
