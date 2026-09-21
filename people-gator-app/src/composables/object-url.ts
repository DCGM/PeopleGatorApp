import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

const OBJECT_URL_RETENTION_MS = 5 * 60_000

type ObjectUrlEntry = {
  url: string
  references: number
  revokeTimer?: ReturnType<typeof setTimeout>
}

const objectUrlCache = new Map<Blob, ObjectUrlEntry>()

function retainObjectUrl(blob: Blob) {
  const cached = objectUrlCache.get(blob)
  if (cached) {
    if (cached.revokeTimer) clearTimeout(cached.revokeTimer)
    cached.revokeTimer = undefined
    cached.references += 1
    return cached.url
  }

  const url = URL.createObjectURL(blob)
  objectUrlCache.set(blob, { url, references: 1 })
  return url
}

function releaseObjectUrl(blob: Blob) {
  const cached = objectUrlCache.get(blob)
  if (!cached) return

  cached.references = Math.max(0, cached.references - 1)
  if (cached.references > 0 || cached.revokeTimer) return

  cached.revokeTimer = setTimeout(() => {
    const current = objectUrlCache.get(blob)
    if (!current || current.references > 0) return
    URL.revokeObjectURL(current.url)
    objectUrlCache.delete(blob)
  }, OBJECT_URL_RETENTION_MS)
}

export function useObjectUrl(blob: MaybeRefOrGetter<Blob | null | undefined>) {
  const url = ref('')
  let retainedBlob: Blob | undefined

  watch(
    () => toValue(blob),
    (nextBlob) => {
      if (retainedBlob === nextBlob) return
      if (retainedBlob) releaseObjectUrl(retainedBlob)
      retainedBlob = nextBlob instanceof Blob ? nextBlob : undefined
      url.value = retainedBlob ? retainObjectUrl(retainedBlob) : ''
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    if (retainedBlob) releaseObjectUrl(retainedBlob)
    retainedBlob = undefined
  })

  return url
}

export function useObjectUrlMap(blobs: MaybeRefOrGetter<ReadonlyMap<string, Blob>>) {
  const urls = ref<ReadonlyMap<string, string>>(new Map())
  let retainedBlobs = new Map<string, Blob>()

  watch(
    () => toValue(blobs),
    (nextBlobs) => {
      for (const blob of retainedBlobs.values()) releaseObjectUrl(blob)
      retainedBlobs = new Map(nextBlobs)
      urls.value = new Map([...retainedBlobs].map(([key, blob]) => [key, retainObjectUrl(blob)]))
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    for (const blob of retainedBlobs.values()) releaseObjectUrl(blob)
    retainedBlobs.clear()
  })

  return urls
}
