import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

export function useObjectUrl(blob: MaybeRefOrGetter<Blob | null | undefined>) {
  const url = ref('')

  watch(
    () => toValue(blob),
    (nextBlob) => {
      if (url.value) URL.revokeObjectURL(url.value)
      url.value = nextBlob instanceof Blob ? URL.createObjectURL(nextBlob) : ''
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    if (url.value) URL.revokeObjectURL(url.value)
  })

  return url
}

export function useObjectUrlMap(blobs: MaybeRefOrGetter<ReadonlyMap<string, Blob>>) {
  const urls = ref<ReadonlyMap<string, string>>(new Map())

  watch(
    () => toValue(blobs),
    (nextBlobs) => {
      for (const url of urls.value.values()) URL.revokeObjectURL(url)
      urls.value = new Map(
        [...nextBlobs.entries()].map(([key, value]) => [key, URL.createObjectURL(value)]),
      )
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    for (const url of urls.value.values()) URL.revokeObjectURL(url)
  })

  return urls
}
