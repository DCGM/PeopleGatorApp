import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useRoute } from 'vue-router'
import { useRouteQueryPatch } from '@/composables/route-query'

export const GALLERY_PERSON_KEY = 'gallery_person_only'
export const LEGACY_GALLERY_PERSON_KEY = 'gallery_person'

/** The strip toggles a scope; the sidebar owns the selected identity. */
export function useGalleryPerson(selectedPersonId: MaybeRefOrGetter<string | null>) {
  const route = useRoute()
  const patch = useRouteQueryPatch()
  const only = computed({
    get: () =>
      route.query[GALLERY_PERSON_KEY] === 'on' ||
      typeof route.query[LEGACY_GALLERY_PERSON_KEY] === 'string',
    set: (value: boolean) => {
      patch(
        {
          [GALLERY_PERSON_KEY]: value ? 'on' : undefined,
          [LEGACY_GALLERY_PERSON_KEY]: undefined,
          selectedPerson: toValue(selectedPersonId) || undefined,
        },
        'push',
      )
    },
  })
  return {
    only,
    personId: computed(() => (only.value ? toValue(selectedPersonId) || '' : '')),
  }
}

export const GALLERY_NOT_VERIFIED_KEY = 'gallery_not_verified'

/** The strip's "Not verified" setting (#149), kept in the URL like the person scope. */
export function useGalleryNotVerified() {
  const route = useRoute()
  const patch = useRouteQueryPatch()
  return computed({
    get: () => route.query[GALLERY_NOT_VERIFIED_KEY] === 'on',
    set: (value: boolean) =>
      patch({ [GALLERY_NOT_VERIFIED_KEY]: value ? 'on' : undefined }, 'push'),
  })
}
