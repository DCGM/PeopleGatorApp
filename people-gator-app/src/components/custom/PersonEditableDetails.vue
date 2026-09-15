<script setup lang="ts">
import { Plus, Trash2 } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'

import ContentEditable from '@/components/custom/ContentEditable.vue'
import EditableActions from '@/components/custom/EditableActions.vue'
import type { PersonProfile } from '@/components/custom/person-detail.types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'

type EditableField = keyof PersonProfile

const props = defineProps<{
  modelValue: PersonProfile
  personId: string
  portrait: string
  faceCount: number
  mentionCount: number
  libraryCount: number
}>()

const emit = defineEmits<{
  'update:modelValue': [profile: PersonProfile]
}>()

const draft = reactive<PersonProfile>({
  ...props.modelValue,
  aliases: [...props.modelValue.aliases],
})
const editingField = ref<EditableField | null>(null)
let savedFieldValue: string | string[] | null = null

const initials = computed(() =>
  draft.name
    .split(' ')
    .map((part) => part.charAt(0))
    .join(''),
)

function nameFromId(id: string) {
  return id
    .split('-')
    .map((part) => part.charAt(0).toLocaleUpperCase('cs') + part.slice(1))
    .join(' ')
}

function beginEditing(field: EditableField) {
  savedFieldValue = field === 'aliases' ? [...draft.aliases] : draft[field]
  editingField.value = field
}

function saveEditing(field: EditableField) {
  if (field === 'aliases') {
    draft.aliases = draft.aliases.map((alias) => alias.trim()).filter(Boolean)
  } else {
    draft[field] = draft[field].trim()
    if (field === 'name' && !draft.name) draft.name = nameFromId(props.personId)
  }
  emit('update:modelValue', { ...draft, aliases: [...draft.aliases] })
  savedFieldValue = null
  editingField.value = null
}

function cancelEditing(field: EditableField) {
  if (field === 'aliases' && Array.isArray(savedFieldValue)) {
    draft.aliases = savedFieldValue
  } else if (typeof savedFieldValue === 'string' && field !== 'aliases') {
    draft[field] = savedFieldValue
  }
  savedFieldValue = null
  editingField.value = null
}

function addAlias() {
  draft.aliases.push('New alias')
}

function removeAlias(index: number) {
  draft.aliases.splice(index, 1)
}

watch(
  () => props.modelValue,
  (profile) => {
    if (editingField.value) return
    Object.assign(draft, profile, { aliases: [...profile.aliases] })
  },
  { deep: true },
)
</script>

<template>
  <header class="border-b pb-8">
    <div class="flex flex-col gap-6 sm:flex-row sm:items-start">
      <Avatar class="size-24 shrink-0 border bg-card sm:size-28">
        <AvatarImage :src="props.portrait" :alt="draft.name" class="grayscale" />
        <AvatarFallback class="font-serif text-2xl">{{ initials }}</AvatarFallback>
      </Avatar>

      <div class="min-w-0 flex-1">
        <small class="font-semibold uppercase text-secondary"
          >Person record · {{ props.personId }}</small
        >
        <div class="mt-1 flex min-w-0 items-center gap-2">
          <ContentEditable
            v-model="draft.name"
            as="h1"
            :editable="editingField === 'name'"
            single-line
            class="min-w-0 w-fit max-w-full rounded-sm px-2 py-1"
            :class="editingField === 'name' && 'bg-card outline-1 outline-ring'"
          />
          <EditableActions
            :editing="editingField === 'name'"
            label="name"
            @edit="beginEditing('name')"
            @save="saveEditing('name')"
            @cancel="cancelEditing('name')"
          />
        </div>

        <div class="mt-2 flex min-w-0 items-start gap-2">
          <ContentEditable
            v-model="draft.shortDescription"
            as="p"
            :editable="editingField === 'shortDescription'"
            single-line
            class="min-w-0 w-fit max-w-3xl rounded-sm px-2 py-1 text-base text-muted-foreground"
            :class="editingField === 'shortDescription' && 'bg-card outline-1 outline-ring'"
          />
          <EditableActions
            :editing="editingField === 'shortDescription'"
            label="description"
            @edit="beginEditing('shortDescription')"
            @save="saveEditing('shortDescription')"
            @cancel="cancelEditing('shortDescription')"
          />
        </div>

        <div class="mt-5 flex flex-wrap items-center gap-2">
          <span class="mr-1 text-xs font-semibold uppercase text-muted-foreground">Aliases</span>
          <span
            v-for="(alias, index) in draft.aliases"
            :key="index"
            class="inline-flex min-h-7 items-center gap-1 border bg-card px-2.5 py-1 text-sm"
          >
            <ContentEditable
              v-model="draft.aliases[index]!"
              :editable="editingField === 'aliases'"
              single-line
              :class="editingField === 'aliases' && 'min-w-16 outline-none'"
            />
            <Button
              v-if="editingField === 'aliases'"
              type="button"
              size="icon-xs"
              variant="ghost"
              class="ml-1 h-[1em] max-h-[1em] text-muted-foreground hover:text-destructive"
              :aria-label="`Remove alias ${alias}`"
              @click="removeAlias(index)"
            >
              <Trash2 class="size-3.5" aria-hidden="true" />
            </Button>
          </span>
          <Button
            v-if="editingField === 'aliases'"
            size="sm"
            variant="ghost"
            class="h-7 px-2"
            @click="addAlias"
          >
            <Plus aria-hidden="true" /> Add alias
          </Button>
          <EditableActions
            :editing="editingField === 'aliases'"
            label="aliases"
            @edit="beginEditing('aliases')"
            @save="saveEditing('aliases')"
            @cancel="cancelEditing('aliases')"
          />
        </div>
      </div>
    </div>
  </header>

  <section class="grid gap-5 border-b py-8 md:grid-cols-[minmax(0,1fr)_12rem]">
    <div class="min-w-0">
      <div class="flex items-center justify-between gap-3">
        <h2>Biography</h2>
        <EditableActions
          :editing="editingField === 'article'"
          label="biography"
          @edit="beginEditing('article')"
          @save="saveEditing('article')"
          @cancel="cancelEditing('article')"
        />
      </div>
      <ContentEditable
        v-model="draft.article"
        as="p"
        :editable="editingField === 'article'"
        class="mt-3 min-h-32 w-fit max-w-4xl rounded-sm px-3 py-2 whitespace-pre-line font-serif text-lg leading-8"
        :class="editingField === 'article' && 'bg-card outline-1 outline-ring'"
      />
    </div>
    <dl class="grid content-start gap-3 border-l-0 text-sm md:border-l md:pl-5">
      <div>
        <dt class="text-muted-foreground">Face detections</dt>
        <dd class="font-mono text-lg">{{ props.faceCount }}</dd>
      </div>
      <div>
        <dt class="text-muted-foreground">Document mentions</dt>
        <dd class="font-mono text-lg">{{ props.mentionCount }}</dd>
      </div>
      <div>
        <dt class="text-muted-foreground">Libraries</dt>
        <dd class="font-mono text-lg">{{ props.libraryCount }}</dd>
      </div>
    </dl>
  </section>
</template>
