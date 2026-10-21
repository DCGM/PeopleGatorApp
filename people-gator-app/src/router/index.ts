import { createRouter, createWebHistory } from 'vue-router'

import DocumentPageView from '@/views/DocumentPageView.vue'
import DocumentSearchView from '@/views/DocumentSearchView.vue'
import DocumentListView from '@/views/DocumentListView.vue'
import PeopleSearchView from '@/views/PeopleSearchView.vue'
import PersonDetailView from '@/views/PersonDetailView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: { name: 'document-list' } },
    {
      path: '/scans',
      name: 'document-search',
      component: DocumentSearchView,
      meta: { title: 'Scan search' },
    },
    {
      path: '/documents',
      name: 'document-list',
      component: DocumentListView,
      meta: { title: 'Documents' },
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

router.beforeEach((to) => {
  document.title = `${String(to.meta.title ?? 'People Gator')} | People Gator`
})

export default router
