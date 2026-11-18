import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：开发时把接口请求代理过去，避免跨域。
// 本地跑 python -X utf8 -m api.main 后就是 127.0.0.1:8080。
const BACKEND = process.env.CTOS_BACKEND || 'http://127.0.0.1:8080'

// 构建产物输出到 ../static/dist：
//   - 后端 api/main.py 已经把 /static 挂出来了
//   - Docker 也只挂载 static/，产物放这里不用改任何部署配置
const OUT_DIR = fileURLToPath(new URL('../static/dist', import.meta.url))

export default defineConfig({
  plugins: [vue()],

  // 产物通过 /static/dist/ 访问，所以静态资源的地址前缀要跟着改
  base: '/static/dist/',

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
