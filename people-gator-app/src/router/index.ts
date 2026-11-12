import { createRouter, createWebHistory } from 'vue-router'
import { legacyFilterNotice, migrateLegacyFilters } from '@/viewmodels/shared-filters'

import PageSourceView from '@/views/PageSourceView.vue'
import DocumentPageView from '@/views/DocumentPageView.vue'
import DocumentPagesView from '@/views/DocumentPagesView.vue'
import { legacyScanLocation } from '@/viewmodels/document-navigation'
import DocumentListView from '@/views/DocumentListView.vue'
import PeopleSearchView from '@/views/PeopleSearchView.vue'
import PersonDetailView from '@/views/PersonDetailView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/pages/:pageSourceId',
      name: 'page-source',
      component: PageSourceView,
      meta: { title: 'Document page' },
    },
    { path: '/', redirect: { name: 'document-list' } },
    {
      path: '/scans',
      redirect: (to) => legacyScanLocation(to.query),
    },
    {
      path: '/documents',
      name: 'document-list',
      component: DocumentListView,
      meta: { title: 'Documents' },
    },
    {
      path: '/documents/:documentSourceId',
      name: 'document-source',
      component: DocumentPagesView,
      meta: { title: 'Document pages' },
    },
    {
      path: '/libraries/:libraryId/documents/:documentId',
      name: 'document-pages',
      component: DocumentPagesView,
      meta: { title: 'Document pages' },
    },
    {
      path: '/people',
      name: 'people-search',
      component: PeopleSearchView,
      meta: { title: 'People search' },
    },
    {
      path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
      name: 'document-page',
      component: DocumentPageView,
      meta: { title: 'Document page' },
    },
    {
      path: '/people/:personId',
      name: 'person-detail',
      component: PersonDetailView,
      meta: { title: 'Person detail' },
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'document-list' } },
  ],
})

// Copied #31 links: rename same-meaning criteria, drop the rest visibly (#52).
let keepNotice = false
router.beforeEach((to) => {
  const migrated = migrateLegacyFilters(to.name, to.query)
  if (migrated) {
    legacyFilterNotice.value = migrated.dropped
    keepNotice = migrated.dropped.length > 0
    return { ...to, query: migrated.query, replace: true }
  }
  if (keepNotice) keepNotice = false
  else legacyFilterNotice.value = []
  document.title = `${String(to.meta.title ?? 'People Gator')} | People Gator`
})

export default router
