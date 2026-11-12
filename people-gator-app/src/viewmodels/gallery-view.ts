import { computed } from 'vue'
import { useRoute, type LocationQuery } from 'vue-router'
import { useRouteQueryPatch } from '@/composables/route-query'

export const GALLERY_VIEW_KEY = 'pages_view'

export function galleryExpanded(query: LocationQuery) {
  return query[GALLERY_VIEW_KEY] === 'expanded'
}

/** Expansion belongs to the shared URL, independently of the selected page. */
export function useGalleryView() {
  const route = useRoute()
  const patch = useRouteQueryPatch()
  return computed({
    get: () => galleryExpanded(route.query),
    set: (expanded: boolean) =>
      patch({ [GALLERY_VIEW_KEY]: expanded ? 'expanded' : undefined }, 'push'),
  })
}
