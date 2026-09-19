import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'

import '@/query/client'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(router)
app.use(VueQueryPlugin, { enableDevtoolsV6Plugin: true })

app.mount('#app')
