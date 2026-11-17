/* ============================================================
   presence.js — 在线人数（两套主题共用）
   ------------------------------------------------------------
   做两件事：

     1. 心跳：每 60 秒 POST /presence/ping，告诉后端「我还在」
        —— 后端按 user 记 last_seen_at，同一账号多标签页只算 1 人
     2. 取数：GET /presence/online，拿最近 10 分钟的活跃人数

   后端不可用时静默降级：不报错、不弹窗，界面上显示「—」。
   ============================================================ */

(function (global) {
    'use strict';

    var PING_INTERVAL = 60 * 1000;      // 心跳间隔
    var POLL_INTERVAL = 45 * 1000;      // 拉在线人数间隔

    var apiBase = (global.API && global.API.base) || '';

    function headers() {
        var h = { 'Content-Type': 'application/json' };
        if (typeof global.authHeaders === 'function') {
            return global.authHeaders(h);
        }
        return h;
    }

    function ping() {
        fetch(apiBase + '/presence/ping', {
            method: 'POST',
            headers: headers(),
            keepalive: true
        }).catch(function () { /* 离线就跳过，下一轮再说 */ });
    }

    function getOnline() {
        return fetch(apiBase + '/presence/online?minutes=10')
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) { return d && typeof d.online === 'number' ? d.online : null; })
            .catch(function () { return null; });
    }

    var timerPing = null;
    var timerPoll = null;
    var listeners = [];

    /* 订阅在线人数变化：调用方拿到值时自己决定怎么画 */
    function onChange(fn) {
        if (typeof fn === 'function') {
            listeners.push(fn);
            // 立刻推一次，避免界面空等一轮
            getOnline().then(function (n) {
                if (n != null) listeners.forEach(function (f) { try { f(n); } catch (e) {} });
            });
        }
    }

    function emit(n) {
        listeners.forEach(function (f) { try { f(n); } catch (e) {} });
    }

    function start() {
        if (timerPing) return;

        ping();

        timerPing = setInterval(function () {
            // 页面在后台时不发心跳，省流量也避免「挂机算在线」
            if (document.visibilityState === 'visible') ping();
        }, PING_INTERVAL);

        timerPoll = setInterval(function () {
            if (document.visibilityState !== 'visible') return;
            getOnline().then(function (n) { if (n != null) emit(n); });
        }, POLL_INTERVAL);

        // 切回前台立刻补一次
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') {
                ping();
                getOnline().then(function (n) { if (n != null) emit(n); });
            }
        });
    }

    global.ctosPresence = {
        start: start,
        getOnline: getOnline,
        ping: ping,
        onChange: onChange
    };
})(window);
