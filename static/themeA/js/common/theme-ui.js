/* ============================================================
   theme-ui.js — 主题 A 的「主题 / 风格」两个菜单
   ------------------------------------------------------------
   两个按钮，各管一件事：

     主题：切换版式（A 经典版 ↔ B 指挥台版），整页跳转
     风格：只在当前主题内部换配色（简洁现代 / 街头黑客 / 赛博暗色）

   数据都来自 /static/shared/js/common/prefs.js，这里只负责画菜单。
   ============================================================ */

(function () {
    'use strict';

    var P = window.ctosPrefs;
    if (!P) return;

    function el(tag, cls, html) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (html != null) n.innerHTML = html;
        return n;
    }

    function closeAll() {
        document.querySelectorAll('.theme-menu.show').forEach(function (m) { m.classList.remove('show'); });
        document.querySelectorAll('[aria-expanded="true"]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
    }

    function toggle(btn, menu) {
        var open = menu.classList.contains('show');
        closeAll();
        if (!open) {
            menu.classList.add('show');
            btn.setAttribute('aria-expanded', 'true');
        }
    }

    /* ---------- 主题菜单：列出版式 ---------- */

    function renderLayoutMenu() {
        var menu = document.getElementById('layout-menu');
        if (!menu) return;

        var current = P.currentLayout();
        var desktop = typeof P.isDesktop === 'function' ? P.isDesktop() : true;
        menu.innerHTML = '';

        Object.keys(P.LAYOUTS).forEach(function (key) {
            // 手机上不列出指挥台版：那个版式要宽屏才放得下，
            // 列出来点了也只会留在经典版，不如干脆不显示。
            if (!desktop && key !== 'A') return;

            var item = P.LAYOUTS[key];
            var on = key === current;
            var row = el('button', 'theme-option' + (on ? ' is-active' : ''));
            row.type = 'button';
            row.setAttribute('role', 'menuitem');
            row.innerHTML =
                '<span class="layout-mark">' + (key === 'A' ? 'A' : 'B') + '</span>' +
                '<span><b>' + item.name + '</b><small>' + item.desc + '</small></span>' +
                (on ? '<span class="opt-check">✓</span>' : '');
            row.onclick = function () {
                closeAll();
                if (on) return;
                // 整页跳到另一个版式；风格各自记忆，跳回来还是原来的配色
                P.goLayout(key);
            };
            menu.appendChild(row);
        });

        var note = el('div', 'theme-note', '两个主题是两套完整页面，切换时会重新加载');
        menu.appendChild(note);
    }

    /* ---------- 风格菜单：只列当前主题的配色 ---------- */

    function renderStyleMenu() {
        var menu = document.getElementById('style-menu');
        if (!menu) return;

        var list = P.stylesOf('A');
        var current = P.currentStyle('A');
        menu.innerHTML = '';

        list.forEach(function (s) {
            var on = s.value === current;
            var row = el('button', 'theme-option' + (on ? ' is-active' : ''));
            row.type = 'button';
            row.setAttribute('role', 'menuitem');
            row.innerHTML =
                '<span class="theme-swatch" style="background:linear-gradient(135deg, ' +
                    s.swatch[0] + ' 50%, ' + s.swatch[1] + ' 50%)"></span>' +
                '<span><b>' + s.name + '</b><small>' + s.desc + '</small></span>' +
                (on ? '<span class="opt-check">✓</span>' : '');
            row.onclick = function () {
                P.setStyle(s.value, 'A');
                P.applyStyle(s.value);
                closeAll();
                renderStyleMenu();
                syncStyleButton();
            };
            menu.appendChild(row);
        });
    }

    function syncStyleButton() {
        var btn = document.getElementById('style-btn');
        if (!btn) return;
        var list = P.stylesOf('A');
        var cur = P.currentStyle('A');
        var hit = null;
        list.forEach(function (s) { if (s.value === cur) hit = s; });
        var dot = btn.querySelector('.style-swatch');
        if (dot && hit) {
            dot.style.background = 'linear-gradient(135deg, ' + hit.swatch[0] + ' 50%, ' + hit.swatch[1] + ' 50%)';
        }
        btn.title = '当前风格：' + (hit ? hit.name : cur);
    }

    /* ---------- 绑定 ---------- */

    document.addEventListener('DOMContentLoaded', function () {
        var layoutBtn = document.getElementById('layout-btn');
        var layoutMenu = document.getElementById('layout-menu');
        var styleBtn = document.getElementById('style-btn');
        var styleMenu = document.getElementById('style-menu');

        renderLayoutMenu();
        renderStyleMenu();
        syncStyleButton();

        if (layoutBtn && layoutMenu) {
            layoutBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                toggle(layoutBtn, layoutMenu);
            });
        }

        if (styleBtn && styleMenu) {
            styleBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                toggle(styleBtn, styleMenu);
            });
        }

        document.addEventListener('click', function (e) {
            if (!e.target.closest('.theme-switcher')) closeAll();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeAll();
        });
    });
})();
