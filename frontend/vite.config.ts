import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Windows 挂载盘在 WSL 和 Docker 中使用轮询，接收宿主机的文件修改。
    watch: process.env.WSL_DISTRO_NAME || process.env.DOCKER_DEV === '1'
      ? { usePolling: true, interval: 500 }
      : undefined,
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
