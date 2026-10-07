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
