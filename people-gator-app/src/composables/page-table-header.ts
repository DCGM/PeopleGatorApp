import { onBeforeUnmount, onMounted, type Ref } from 'vue'

// Horizontal overflow prevents native page-sticky positioning. Keep the original
// header, but measure only on layout changes: scrolling must not trigger Vue
// renders, layout reads, or an extra animation-frame delay.
export function usePageTableHeader(frame: Ref<HTMLElement | null>) {
  let table: HTMLTableElement | null = null
  let header: HTMLTableSectionElement | null = null
  let navigation: Element | null = null
  let originTop = 0
  let maximumOffset = 0
  let navigationBottom = 0
  let lastOffset = Number.NaN
  let animation: number | undefined
  let resize: ResizeObserver | undefined
  let active = false

  function position() {
    if (!header) return
    const offset = Math.max(
      0,
      Math.min(window.scrollY + navigationBottom - originTop, maximumOffset),
    )
    if (offset === lastOffset) return
    lastOffset = offset
    header.style.transform = `translate3d(0, ${offset}px, 0)`
  }

  function measure() {
    if (!table || !header) return
    const bounds = table.getBoundingClientRect()
    originTop = bounds.top + window.scrollY
    maximumOffset = Math.max(0, bounds.height - header.offsetHeight)
    navigationBottom = navigation?.getBoundingClientRect().bottom ?? 0
    position()
  }

  function scheduleMeasurement() {
    if (!active || animation !== undefined) return
    animation = requestAnimationFrame(() => {
      animation = undefined
      measure()
    })
  }

  onMounted(() => {
    table = frame.value?.querySelector('table') ?? null
    header = table?.tHead ?? null
    navigation = document.querySelector('[data-page-navigation]')
    active = true
    measure()
    window.addEventListener('scroll', position, { passive: true, capture: true })
    window.addEventListener('resize', scheduleMeasurement)
    if (typeof ResizeObserver !== 'undefined') {
      resize = new ResizeObserver(scheduleMeasurement)
      // Filters and other ancestors can move the table without changing its size.
      for (let element = frame.value; element; element = element.parentElement) {
        resize.observe(element)
      }
      for (const element of [table, header, navigation]) {
        if (element) resize.observe(element)
      }
    }
  })
  onBeforeUnmount(() => {
    active = false
    window.removeEventListener('scroll', position, true)
    window.removeEventListener('resize', scheduleMeasurement)
    resize?.disconnect()
    if (animation !== undefined) cancelAnimationFrame(animation)
  })
}
