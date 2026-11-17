/* ============================================================
   theme-ui.js — 指挥台版（主题 B）的「主题 / 风格」面板
   ------------------------------------------------------------
   两个按钮，各管一件事：

     主题：切换版式（B 指挥台版 ↔ A 经典版），整页跳转
     风格：只在当前主题内部换配色（晨光控制台 / 指挥台）

   版式 B 没有侧栏菜单，所以这里用一个浮层面板，从左侧导轨旁边弹出。
   数据来自 /static/shared/js/common/prefs.js。
   ============================================================ */

(function () {
    'use strict';

    var P = window.ctosPrefs;
    if (!P) return;

    var panel = null;
    var current = null;   // 'layout' | 'style'

    function build() {
        if (panel) return panel;

        panel = document.createElement('div');
        panel.className = 'pref-panel';
        panel.innerHTML =
            '<div class="pref-head">' +
                '<span class="pref-title" id="pref-title">主题</span>' +
                '<button class="pref-close" type="button" aria-label="关闭">×</button>' +
            '</div>' +
            '<div class="pref-body" id="pref-body"></div>' +
            '<div class="pref-note" id="pref-note"></div>';

        document.body.appendChild(panel);

        panel.querySelector('.pref-close').onclick = close;
        document.addEventListener('click', function (e) {
            if (!panel.classList.contains('show')) return;
            if (e.target.closest('.pref-panel') || e.target.closest('.rail-nav-action')) return;
            close();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') close();
        });

        return panel;
    }

    function close() {
        if (panel) panel.classList.remove('show');
        document.querySelectorAll('.rail-nav-action.is-open').forEach(function (b) {
            b.classList.remove('is-open');
        });
        current = null;
    }

    function rowHTML(left, name, desc, active) {
        return '<button class="pref-row' + (active ? ' is-active' : '') + '" type="button">' +
            left +
            '<span class="pref-row-text"><b>' + name + '</b><small>' + desc + '</small></span>' +
            (active ? '<span class="pref-check">✓</span>' : '') +
        '</button>';
    }

    function renderLayout() {
        var body = document.getElementById('pref-body');
        var title = document.getElementById('pref-title');
        var note = document.getElementById('pref-note');
        if (!body) return;

        title.textContent = '主题';
        note.textContent = '两套主题是两套完整页面，切换时会重新加载';

        var cur = P.currentLayout();
        var html = '';
        Object.keys(P.LAYOUTS).forEach(function (key) {
            var item = P.LAYOUTS[key];
            var on = key === cur;
            html += rowHTML(
                '<span class="pref-mark">' + key + '</span>',
                item.name, item.desc, on
            ).replace('class="pref-row', 'data-layout="' + key + '" class="pref-row');
        });
        body.innerHTML = html;

        body.querySelectorAll('.pref-row').forEach(function (row) {
            row.onclick = function () {
                var key = row.dataset.layout;
                if (key === cur) { close(); return; }
                P.goLayout(key);
            };
        });
    }

    function renderStyle() {
        var body = document.getElementById('pref-body');
        var title = document.getElementById('pref-title');
        var note = document.getElementById('pref-note');
        if (!body) return;

        title.textContent = '风格';
        note.textContent = '只换配色，页面结构不变';

        var cur = P.currentStyle('B');
        var html = '';
        P.stylesOf('B').forEach(function (s) {
            var on = s.value === cur;
            var sw = '<span class="pref-swatch" style="background:linear-gradient(135deg,' +
                s.swatch[0] + ' 50%,' + s.swatch[1] + ' 50%)"></span>';
            html += rowHTML(sw, s.name, s.desc, on)
                .replace('class="pref-row', 'data-style="' + s.value + '" class="pref-row');
        });
        body.innerHTML = html;

        body.querySelectorAll('.pref-row').forEach(function (row) {
            row.onclick = function () {
                var v = row.dataset.style;
                P.setStyle(v, 'B');
                P.applyStyle(v);
                renderStyle();
                LOG.styleChanged && LOG.styleChanged(v);
            };
        });
    }

    // 让操作日志也能记一笔风格切换
    var LOG = {
        styleChanged: function (v) {
            if (window.ctosLog && typeof window.ctosLog.push === 'function') {
                window.ctosLog.push('ACT', 'theme', '切换配色 → ' + v, { req: '' });
            }
        }
    };

    function open(kind, btn) {
        build();
        document.querySelectorAll('.rail-nav-action.is-open').forEach(function (b) {
            b.classList.remove('is-open');
        });
        if (btn) btn.classList.add('is-open');
        if (kind === 'layout') renderLayout();
        else renderStyle();
        panel.classList.add('show');
        current = kind;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var layoutBtn = document.getElementById('layout-btn');
        var styleBtn = document.getElementById('style-btn');

        if (layoutBtn) {
            layoutBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (current === 'layout') close();
                else open('layout', layoutBtn);
            });
        }

        if (styleBtn) {
            styleBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (current === 'style') close();
                else open('style', styleBtn);
            });
        }
    });
})();
