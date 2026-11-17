/* ============================================================
   presence-ui.js — 主题 A 的在线人数显示
   ------------------------------------------------------------
   只负责把 ctosPresence 给的数字画到侧栏底部，
   取数和心跳都在 /static/shared/js/common/presence.js 里。
   ============================================================ */

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var P = window.ctosPresence;
        if (!P) return;

        var num = document.getElementById('presence-num');
        if (!num) return;

        P.start();
        P.onChange(function (n) {
            num.textContent = String(n);
        });
    });
})();
