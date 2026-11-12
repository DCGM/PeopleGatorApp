<script setup lang="ts">
import ArchiveLink from './ArchiveLink.vue'
import PageReviewControls from './PageReviewControls.vue'
import { useEntityQuery } from '@/query/entities'
import { useDocumentLookupQuery, usePageLookupQuery } from '@/query/media'
import { FileText, User } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'

import PeopleGatorIcon from '@/components/custom/PeopleGatorIcon'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

const route = useRoute()

const pageQuery = usePageLookupQuery(
  () => (route.name === 'document-page' ? String(route.params.libraryId) : ''),
  () => (route.name === 'document-page' ? String(route.params.documentId) : ''),
  () => (route.name === 'document-page' ? String(route.params.pageId) : ''),
)

const documentQuery = useDocumentLookupQuery(
  () => (route.name === 'document-page' ? String(route.params.libraryId) : ''),
  () => (route.name === 'document-page' ? String(route.params.documentId) : ''),
)

// Shares the profile's entity cache, so renames update the label.
const personQuery = useEntityQuery(() =>
  route.name === 'person-detail' ? String(route.params.personId) : '',
)

const breadcrumbs = computed(() => {
  const library = route.params.libraryId
  const document = route.params.documentId
  const items = [
    {
      label: 'PeopleGator',
      to: { name: 'document-list' } as RouteLocationRaw,
    },
  ]
  if (route.name === 'person-detail') {
    items.push({
      label: 'People',
      to: { name: 'people-search' },
    })
    items.push({
      label: personQuery.data.value?.name?.trim() || String(route.params.personId),
      to: { path: route.path, query: route.query },
    })
    return items
  }
  if (route.name === 'document-list') {
    items.push({
      label: 'Documents',
      to: { name: 'document-list' },
    })
    return items
  }
  // Source crumbs keep only their explicit library/document context.
  if (route.name === 'document-page' && typeof library === 'string') {
    items.push({
      label: library,
      to: { name: 'document-list', query: { library } },
    })
    if (typeof document === 'string') {
      items.push({
        label: documentQuery.data.value?.name?.trim() || document,
        to: {
          name: 'document-pages',
          params: { libraryId: library, documentId: document },
          query: { pages_view: 'expanded' },
        },
      })
    }
    items.push({
      label: `Page ${pageQuery.data.value?.page_number ?? String(route.params.pageId)}`,
      to: { path: route.path, query: route.query },
    })
  } else if (route.name === 'document-source' || route.name === 'document-pages') {
    items.push({ label: 'Documents', to: { name: 'document-list' } })
  } else if (route.name === 'people-search') {
    items.push({
      label: 'People',
      to: { name: 'people-search' },
    })
  }
  return items
})

// On phones the logo links home, leaving room for the record's own label.
const hidesHomeCrumbOnPhone = computed(
  () => route.name === 'document-page' || route.name === 'person-detail',
)

const isDocumentRoute = computed(() =>
  ['document-list', 'document-source', 'document-pages', 'page-source', 'document-page'].includes(
    String(route.name),
  ),
)
const isPeopleRoute = computed(
  () => route.name === 'people-search' || route.name === 'person-detail',
)
</script>

<template>
  <nav
    class="sticky top-0 z-50 flex h-13 w-full items-center gap-2 border-b bg-background px-2 sm:gap-3 sm:px-4"
  >
    <div class="flex shrink-0 items-center gap-2">
      <RouterLink
        :to="{ name: 'document-list' }"
        aria-label="PeopleGator"
        class="z-20 flex size-12 shrink-0 items-center justify-center bg-background"
      >
        <PeopleGatorIcon aria-hidden="true" class="size-10 text-primary" stroke-width="1" />
      </RouterLink>
    </div>

    <div class="min-w-0 flex-1">
      <Breadcrumb aria-label="Breadcrumb" class="min-w-0">
        <BreadcrumbList
          class="min-w-0 flex-nowrap gap-1 font-heading text-base font-extralight leading-normal sm:gap-2"
        >
          <template v-for="(crumb, index) in breadcrumbs" :key="index">
            <BreadcrumbSeparator
              v-if="index"
              class="shrink-0"
              :class="index === 1 && hidesHomeCrumbOnPhone ? 'hidden sm:block' : undefined"
            />
            <BreadcrumbItem
              class="min-w-0"
              :class="[
                index === 0 && hidesHomeCrumbOnPhone ? 'hidden sm:inline-flex' : undefined,
                index === breadcrumbs.length - 1 && pageQuery.data.value?.page_number != null
                  ? 'shrink-0'
                  : index === breadcrumbs.length - 1
                    ? 'flex-[0_1_auto]'
                    : 'flex-[0_2_auto]',
              ]"
            >
              <BreadcrumbLink
                as-child
                class="block min-w-0 truncate rounded-sm py-0.5 hover:text-primary focus-visible:outline-2 focus-visible:outline-primary"
                :class="
                  index === breadcrumbs.length - 1 ? 'text-foreground' : 'text-muted-foreground'
                "
              >
                <RouterLink
                  :to="crumb.to"
                  :title="crumb.label"
                  :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined"
                >
                  {{ crumb.label }}
                </RouterLink>
              </BreadcrumbLink>
            </BreadcrumbItem>
          </template>
        </BreadcrumbList>
      </Breadcrumb>
    </div>

    <ArchiveLink
      v-if="route.name === 'document-page'"
      :url="pageQuery.data.value?.url"
      compact
      class="self-center"
    />
    <PageReviewControls
      v-if="route.name === 'document-page' && pageQuery.data.value"
      :page="pageQuery.data.value"
      :document="documentQuery.data.value"
    />

    <div class="flex shrink-0 items-center gap-3 sm:gap-6">
      <slot name="navigation">
        <RouterLink
          :to="{ name: 'document-list' }"
          aria-label="Documents"
          :aria-current="isDocumentRoute ? 'page' : undefined"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            isDocumentRoute
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          "
        >
          <span class="flex items-center gap-2">
            <FileText class="size-[1em]" />
            <span class="hidden 2xl:inline">Documents</span>
          </span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'people-search' }"
          aria-label="People"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            isPeopleRoute
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          "
        >
          <span class="flex items-center gap-2">
            <User class="size-[1em]" />
            <span class="hidden 2xl:inline">People</span>
          </span>
        </RouterLink>
      </slot>
    </div>
  </nav>
</template>
