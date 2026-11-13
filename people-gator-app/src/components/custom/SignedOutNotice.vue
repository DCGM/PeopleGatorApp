<script setup lang="ts">
import { LogIn, UserRoundX } from '@lucide/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { Button } from '@/components/ui/button'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'
import { signIn, signInProblem } from '@/query/client'

const queryClient = useQueryClient()
const pending = ref(false)
const forbidden = computed(() => signInProblem.value === 'forbidden')

async function retry() {
  pending.value = true
  try {
    await signIn()
    await queryClient.invalidateQueries()
  } catch {
    // signInProblem keeps this notice visible.
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="flex justify-center p-4 pt-16">
    <Item variant="outline" role="status" class="w-full max-w-md bg-card">
      <ItemMedia variant="icon">
        <UserRoundX aria-hidden="true" />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>{{ forbidden ? 'Access denied' : 'Signed out' }}</ItemTitle>
        <ItemDescription v-if="forbidden">Close the browser to use another account.</ItemDescription>
      </ItemContent>
      <ItemActions>
        <Button :disabled="pending" @click="retry">
          <LogIn aria-hidden="true" />
          Sign in
        </Button>
      </ItemActions>
    </Item>
  </main>
</template>
