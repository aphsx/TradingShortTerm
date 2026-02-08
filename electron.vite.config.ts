import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        external: ['child_process']
      }
    }
  },
  preload: {},
  renderer: {
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src'),
        '@': resolve('src/renderer/src')
      }
    },
    plugins: [react()],
    build: {
      outDir: 'dist'
    },
    server: {
      middlewareMode: false,
      hmr: {
        host: 'localhost',
        port: 5173
      }
    }
  }
})
