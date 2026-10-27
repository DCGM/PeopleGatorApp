import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

// A native sticky thead sticks to the horizontal overflow wrapper, not the page.
// Move the original semantic header so its sort buttons stay usable and aligned.
export function usePageTableHeader(frame: Ref<HTMLElement | null>) {
  const offset = ref(0)
  let animation: number | undefined
  let resize: ResizeObserver | undefined

  function update() {
    const table = frame.value?.querySelector('table')
    const header = table?.tHead
    if (!table || !header) return
    const bounds = table.getBoundingClientRect()
    const navigation = document.querySelector('[data-page-navigation]')
    const top = navigation?.getBoundingClientRect().bottom ?? 0
    offset.value = Math.max(0, Math.min(top - bounds.top, bounds.height - header.offsetHeight))
  }

  function schedule() {
    if (animation !== undefined) return
    animation = requestAnimationFrame(() => {
      animation = undefined
      update()
    })
  }

  onMounted(() => {
    update()
    window.addEventListener('scroll', schedule, { passive: true, capture: true })
    window.addEventListener('resize', schedule)
    if (typeof ResizeObserver !== 'undefined') {
      resize = new ResizeObserver(schedule)
      // Ancestors can move the table when filters or content above it expand.
      for (let element = frame.value; element; element = element.parentElement) {
        resize.observe(element)
      }
      for (const element of [
        frame.value?.querySelector('table'),
        frame.value?.querySelector('thead'),
        document.querySelector('[data-page-navigation]'),
      ]) {
        if (element) resize.observe(element)
      }
    }
  })
  onBeforeUnmount(() => {
    window.removeEventListener('scroll', schedule, true)
    window.removeEventListener('resize', schedule)
    resize?.disconnect()
    if (animation !== undefined) cancelAnimationFrame(animation)
  })

  return offset
}
