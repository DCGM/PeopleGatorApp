<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { login, finishLogout, safeReturnPath } from '@/query/auth'

const busy = ref(false)
const params = new URLSearchParams(location.search)
const message = ref(params.has('error') ? 'Sign-in could not be completed. Try again.' : '')
async function submit() {
  busy.value = true
  message.value = ''
  try {
    await login(safeReturnPath(params.get('return')))
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Unable to sign in. Try again.'
    busy.value = false
  }
}
onMounted(async () => {
  if (params.has('state')) {
    try {
      await finishLogout()
    } catch {
      message.value = 'Sign-out could not be completed. Try again.'
    }
  } else if (!params.has('error')) await submit()
})
</script>
<template>
  <main class="min-h-screen bg-background px-6 py-16 text-foreground">
    <div class="mx-auto flex w-full max-w-sm flex-col gap-6">
      <p class="text-muted-foreground">PeopleGator</p>
      <h1 class="text-2xl font-semibold">Sign in</h1>
      <p v-if="message" role="alert">{{ message }}</p>
      <Button :disabled="busy" @click="submit">{{ busy ? 'Opening sign in…' : 'Sign in' }}</Button>
    </div>
  </main>
</template>
