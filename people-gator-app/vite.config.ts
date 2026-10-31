import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import tailwindcss from '@tailwindcss/vite'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = env.ALLOWED_VITE_HOSTS?.split(',')
    .map((host) => host.trim())
    .filter(Boolean)

  return {
    build: { rollupOptions: { input: {
      app: fileURLToPath(new URL('./index.html', import.meta.url)),
      login: fileURLToPath(new URL('./login.html', import.meta.url)),
    } } },
    plugins: [vue(), vueJsx(), tailwindcss(), vueDevTools()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      allowedHosts: allowedHosts && allowedHosts.length > 0 ? allowedHosts : ['localhost'],
    },
  }
})
