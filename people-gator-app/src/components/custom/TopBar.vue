<script setup lang="ts">
import { useEntityQuery } from '@/query/entities'
import { useDocumentLookupQuery, usePageLookupQuery } from '@/query/media'
import { CircleUser, FileText, LogIn, LogOut, User } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'

import PeopleGatorIcon from '@/components/custom/PeopleGatorIcon'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { currentUser, isPublicSession, signOut } from '@/query/client'
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

const sections = computed(() => [
  {
    label: 'Documents',
    icon: FileText,
    to: { name: 'document-list' } as RouteLocationRaw,
    active: [
      'document-list',
      'document-source',
      'document-pages',
      'page-source',
      'document-page',
    ].includes(String(route.name)),
  },
  {
    label: 'People',
    icon: User,
    to: { name: 'people-search' } as RouteLocationRaw,
    active: route.name === 'people-search' || route.name === 'person-detail',
  },
])
</script>

<template>
  <!-- Below `md` the bar packs left to right. From `md` the selector sits in the middle;
       breadcrumbs wider than their half push it aside before they truncate. -->
  <nav
    class="sticky top-0 z-50 grid h-13 w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 border-b bg-background px-2 sm:gap-3 sm:px-4 md:grid-cols-[minmax(auto,1fr)_auto_minmax(auto,1fr)]"
  >
    <div class="flex min-w-0 items-center gap-2 md:w-max md:max-w-[calc(100vw-30rem)]">
      <RouterLink
        :to="{ name: 'document-list' }"
        aria-label="PeopleGator"
        class="z-20 flex size-12 shrink-0 items-center justify-center bg-background"
      >
        <PeopleGatorIcon aria-hidden="true" class="size-10 text-primary" stroke-width="1" />
      </RouterLink>

      <Breadcrumb aria-label="Breadcrumb" class="min-w-0 flex-1">
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

    <div
      class="inline-flex h-9 shrink-0 items-center rounded-lg bg-muted p-0.75 text-muted-foreground"
      data-slot="section-selector"
    >
      <slot name="navigation">
        <RouterLink
          v-for="section in sections"
          :key="section.label"
          :to="section.to"
          :aria-label="section.label"
          :aria-current="section.active ? 'page' : undefined"
          class="inline-flex h-full items-center gap-1.5 rounded-md px-3 text-sm font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50"
          :class="
            section.active ? 'bg-background text-foreground shadow-sm' : 'hover:text-foreground'
          "
        >
          <component :is="section.icon" class="size-4 shrink-0" aria-hidden="true" />
          <span class="hidden sm:inline">{{ section.label }}</span>
        </RouterLink>
      </slot>
    </div>

    <div class="flex min-w-0 items-center justify-end">
      <!-- Leaving the public account opens the login page. -->
      <Button
        v-if="isPublicSession"
        variant="outline"
        class="rounded-lg"
        aria-label="Sign in"
        @click="signOut"
      >
        <LogIn aria-hidden="true" />
        <span class="hidden sm:inline">Sign in</span>
      </Button>
      <DropdownMenu v-else-if="currentUser">
        <DropdownMenuTrigger as-child>
          <Button
            variant="outline"
            class="min-w-0 rounded-lg"
            :aria-label="`Account ${currentUser}`"
          >
            <CircleUser aria-hidden="true" />
            <span class="hidden max-w-32 truncate sm:inline">{{ currentUser }}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel class="max-w-48 truncate">{{ currentUser }}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem @select="signOut">
            <LogOut aria-hidden="true" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </nav>
</template>
