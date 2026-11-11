import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import '@/query/client'
import { retryUnlessClientError } from '@/query/api'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.use(VueQueryPlugin, {
  enableDevtoolsV6Plugin: true,
  queryClientConfig: { defaultOptions: { queries: { retry: retryUnlessClientError } } },
})
app.mount('#app')
