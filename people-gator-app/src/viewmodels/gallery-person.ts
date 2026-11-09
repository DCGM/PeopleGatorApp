import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export const GALLERY_PERSON_KEY = 'gallery_person'

/** Independent of the sidebar's selected face/person and evidence settings. */
export function useGalleryPerson() {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () =>
      typeof route.query[GALLERY_PERSON_KEY] === 'string' ? route.query[GALLERY_PERSON_KEY] : '',
    set: (value: string) => {
      void router.push({ query: { ...route.query, [GALLERY_PERSON_KEY]: value || undefined } })
    },
  })
}
