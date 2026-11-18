import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { setStreamTokenProvider } from './shared/api/stream'
import { authStore } from './shared/auth/authStore'

import './shared/styles/tokens.css'

const app = createApp(App)

app.use(router)

// 流式请求也要带 token。
// http.ts 和 stream.ts 各自管自己的请求，这里把「怎么取 token」告诉它们，
// 避免两个模块互相 import。
setStreamTokenProvider(authStore.token)

// 启动前先完成登录（或创建访客账号）。
// 放在 mount 之前，是为了让第一个页面渲染出来时就已经有身份，
// 不会先闪一下「请先登录」再变成正常内容。
void authStore
  .boot()
  .catch(() => {
    // 启动失败也让界面出来，页面里会显示具体错误
  })
  .finally(() => {
    app.mount('#app')
  })
