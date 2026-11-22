import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：开发时把接口请求代理过去，避免跨域。
// 本地跑 python -X utf8 -m api.main 后就是 127.0.0.1:8080。
const BACKEND = process.env.CTOS_BACKEND || 'http://127.0.0.1:8080'

// 构建产物输出到 web/dist：
//   - 前端的东西全在这一个目录里（源码 src/ + 产物 dist/）
//   - 后端 api/main.py 只挂 web/dist，不会把 src 暴露出去
const OUT_DIR = fileURLToPath(new URL('./dist', import.meta.url))

export default defineConfig({
  plugins: [vue()],

  // 产物通过 /static/ 访问（URL 前缀保持 /static 不变，
  // 前端代码里写死的 /static/... 路径都不用动）
  base: '/static/',

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    port: 5174,
    // 开发时所有接口都转发给后端。
    // 新增后端路由时，把路径第一段加到这里即可。
    proxy: Object.fromEntries(
      [
        '/auth',
        '/chat',
        '/trip',
        '/guide',
        '/customer',
        '/roleplay',
        '/sessions',
        '/presence',
        '/feedback',
        '/notice',
        '/contract',
        '/health',
      ].map((path) => [path, { target: BACKEND, changeOrigin: true }]),
    ),
  },

  build: {
    outDir: OUT_DIR,
    emptyOutDir: true, // 每次构建先清空，避免旧文件残留
    sourcemap: false,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // 把不常变的库单独拆出来，用户升级后只需要重新下载自己改过的部分
        manualChunks: {
          vue: ['vue', 'vue-router'],
        },
      },
    },
  },
})
