import { onBeforeUnmount, shallowRef } from 'vue'

export const HOVER_CARD_OPEN_DELAY = 250
export const HOVER_CARD_CLOSE_DELAY = 200

/**
 * Hover intent for a floating card (#203): the card opens after a short rest on
 * its target and stays while the pointer travels from the target into the card.
 */
export function useHoverCard<T>() {
  const target = shallowRef<T | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined

  /** Keep the current state, such as while the pointer is inside the card. */
  function hold() {
    clearTimeout(timer)
    timer = undefined
  }
  function open(value: T, immediate = false) {
    hold()
    if (immediate) target.value = value
    else timer = setTimeout(() => (target.value = value), HOVER_CARD_OPEN_DELAY)
  }
  function close(immediate = false) {
    hold()
    if (immediate || target.value === null) target.value = null
    else timer = setTimeout(() => (target.value = null), HOVER_CARD_CLOSE_DELAY)
  }
  onBeforeUnmount(hold)

  return { target, open, close, hold }
}

/** The pointer moved from a card into a layer the card opened, such as a face gallery. */
export function movedIntoNestedLayer(event: MouseEvent, card: Element) {
  const to = event.relatedTarget
  if (!(to instanceof Element) || card.contains(to)) return false
  return Boolean(to.closest('[data-reka-popper-content-wrapper]'))
}

/** The card holds focus or an open form, such as a new person's name: keep it. */
export function cardInUse(card: Element | null | undefined) {
  return Boolean(card && (card.contains(document.activeElement) || card.querySelector('form')))
}
