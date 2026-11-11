# 线上隧道检查

## 什么时候看这个

手机打开 `ctos2.cn` 出现：

- 一直在加载
- 有时能开、有时打不开
- 页面能开，但接口或静态资源超时

先跑：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_online.ps1
```

如果 `/health`、`/`、`/static/js/app.js` 有任意一项失败，基本可以确定不是手机样式问题。

## 最常见原因：同一个隧道挂了两台机器

Cloudflare Tunnel 同时连了笔记本和家里台式机时，请求会被随机分到其中一台：

- 一台是当前代码，另一台是旧代码
- 表现就是间歇性加载失败、接口 404、页面版本不一致

## 处理步骤

1. 打开 Cloudflare Dashboard
2. 进入 **Zero Trust → Networks → Tunnels**
3. 点 `inori`
4. 看 **Replicas / 副本**
5. 只保留当前这台笔记本
6. 把 `DESKTOP-350EO5K` 之类不用的副本断开/删除

## 如果删掉又自己连回来

说明旧机器的 cloudflared 还在运行，并且拿着旧 token。

1. 在隧道页面点 **Refresh token / 轮换令牌**
2. 旧机器的 token 会失效
3. 在当前笔记本更新 token
4. 重启本机 Cloudflared 服务
5. 再跑一次 `scripts\check_online.ps1`

## 验证

连续跑 3 次都成功：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_online.ps1 -Times 3
```

再用手机打开一次，确认不是只在电脑上正常。

## 注意

这个脚本只能发现“线上有超时”，不能直接分辨请求被分到了哪台机器。  
要确认副本，必须看 Cloudflare Dashboard。
