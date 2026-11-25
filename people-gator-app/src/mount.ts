import { createApp } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import '@/query/client'
import { retryUnlessClientError } from '@/query/api'
import './style.css'
import App from './App.vue'
import router from './router'
import { installAuth } from './router/auth'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: retryUnlessClientError } },
})
installAuth(router, queryClient)

const app = createApp(App)
app.use(router)
app.use(VueQueryPlugin, { enableDevtoolsV6Plugin: true, queryClient })
app.mount('#app')
