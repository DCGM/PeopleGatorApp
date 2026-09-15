import type { InjectionKey, Ref } from 'vue'

export const topBarContextKey = Symbol('topBarContext') as InjectionKey<
  Readonly<Ref<HTMLElement | null>>
>
