/* ============================================================
   prefs.js — 主题 / 风格偏好的读写（两套主题共用）
   ------------------------------------------------------------
   这里有两层概念，别混：

     主题（layout）：整个页面结构，只有两个
       A = 旧版（左侧栏 + 顶栏 tab + 气泡聊天）
       B = 新版（图标导轨 + 右侧控制台）

     风格（style）：主题内部的配色，每个主题有自己的一组
       A：clean 简洁现代 / street 街头黑客 / cyber 赛博暗色
       B：light 晨光控制台 / console 指挥台

   存储：
     ctos_layout  = "A" | "B"                   默认 A
     ctos_style_A = "clean" | "street" | "cyber"  默认 clean
     ctos_style_B = "light" | "console"           默认 light

   两个 key 分开存，是为了「换主题再换回来，风格还记得」。
   清浏览器缓存后回到默认（A + clean），这是正常预期。
   ============================================================ */

(function (global) {
    'use strict';

    var KEY_LAYOUT = 'ctos_layout';
    var KEY_STYLE = { A: 'ctos_style_A', B: 'ctos_style_B' };

    var LAYOUTS = {
        A: { key: 'A', name: '经典版', desc: '左侧栏 + 气泡对话', url: '/static/themeA/index.html' },
        B: { key: 'B', name: '指挥台版', desc: '图标导轨 + 控制台', url: '/static/themeB/index.html' }
    };

    // 每个主题自己的风格列表；value 写进 <html data-theme>
    var STYLES = {
        A: [
            { value: 'clean',  name: '简洁现代', desc: '浅色 · 靛蓝',   swatch: ['#ffffff', '#5850e6'] },
            { value: 'street', name: '街头黑客', desc: '纸感 · 荧光',   swatch: ['#f3efe3', '#ff2e88'] },
            { value: 'cyber',  name: '赛博暗色', desc: '深色 · 霓虹',   swatch: ['#080b12', '#38d6f2'] }
        ],
        B: [
            { value: 'console-light', name: '晨光控制台', desc: '亮色 · 青绿', swatch: ['#ffffff', '#0e9f8f'] },
            { value: 'console',       name: '指挥台',     desc: '深色 · 霓虹', swatch: ['#060a11', '#2ee6d6'] }
        ]
    };

    var DEFAULT_LAYOUT = 'A';
    var DEFAULT_STYLE = { A: 'clean', B: 'console-light' };

    /* ---------- 哪些主题能用 ----------
       指挥台版（B）只有宽屏才有意义：
       它靠「左侧图标导轨 + 右侧控制台」两块固定宽度撑起来，
       手机上这两块都没有空间，塞进去只会挤成一团。

       所以规则很简单：窄屏一律用经典版（A）。
       不管上次选过什么，手机打开都是 A；也不给手机用户切到 B 的入口。 */
    var DESKTOP_MIN_WIDTH = 900;

    function isDesktop() {
        if (typeof window.matchMedia === 'function') {
            return window.matchMedia('(min-width: ' + DESKTOP_MIN_WIDTH + 'px)').matches;
        }
        return (window.innerWidth || 0) >= DESKTOP_MIN_WIDTH;
    }

    // 当前设备实际能用的主题：手机端恒为 A
    // 注意这里读的是 storedLayout()（存下来的偏好），
    // 不能读 currentLayout()，否则两个函数互相调用会无限递归。
    function usableLayout() {
        if (!isDesktop()) return DEFAULT_LAYOUT;
        return storedLayout();
    }

    /* ---------- 底层读写：localStorage 优先，cookie 兜底 ----------
       cookie 的价值：有些浏览器「清除缓存」会清 localStorage 但保留 cookie，
       两边都存一份能少丢几次。都失败就回默认值。 */

    function readCookie(name) {
        var m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return m ? decodeURIComponent(m[1]) : null;
    }

    function writeCookie(name, value) {
        // 一年有效期；SameSite=Lax 避免被第三方场景带出去
        document.cookie = name + '=' + encodeURIComponent(value) +
            '; path=/; max-age=' + (60 * 60 * 24 * 365) + '; SameSite=Lax';
    }

    function get(key) {
        var v = null;
        try { v = localStorage.getItem(key); } catch (e) {}
        if (!v) v = readCookie(key);
        return v;
    }

    function set(key, value) {
        try { localStorage.setItem(key, value); } catch (e) {}
        try { writeCookie(key, value); } catch (e) {}
    }

    /* ---------- 主题 ---------- */

    // 存下来的原始偏好（不看屏幕宽度，手机也可能存过 B）
    function storedLayout() {
        var v = get(KEY_LAYOUT);
        return LAYOUTS[v] ? v : DEFAULT_LAYOUT;
    }

    // 对外统一用这个：手机上拿到的永远是 A
    function currentLayout() {
        return usableLayout();
    }

    function setLayout(layout) {
        if (!LAYOUTS[layout]) return;
        set(KEY_LAYOUT, layout);
    }

    // 跳到指定主题的页面。整页跳转而不是替换 DOM：
    // 两套结构完全不同，跳转最稳，对话数据都在后端不会丢。
    // 手机端即使要求 B 也只会留在 A。
    function goLayout(layout, replace) {
        if (!LAYOUTS[layout]) return;
        if (!isDesktop()) layout = DEFAULT_LAYOUT;

        setLayout(layout);
        var url = LAYOUTS[layout].url;
        if (replace) location.replace(url);
        else location.href = url;
    }

    /* ---------- 风格 ---------- */

    function currentStyle(layout) {
        var l = layout || currentLayout();
        var v = get(KEY_STYLE[l]);
        var list = STYLES[l] || [];
        for (var i = 0; i < list.length; i++) {
            if (list[i].value === v) return v;
        }
        return DEFAULT_STYLE[l];
    }

    function setStyle(value, layout) {
        var l = layout || currentLayout();
        set(KEY_STYLE[l], value);
    }

    function stylesOf(layout) {
        return STYLES[layout || currentLayout()] || [];
    }

    // 把风格写到 <html data-theme>，CSS 靠它切配色
    function applyStyle(value) {
        document.documentElement.dataset.theme = value;
    }

    /* ---------- 首屏防闪 ----------
       在 <head> 里同步执行：先定出主题和风格，再让 CSS 生效，
       否则会先看到默认配色再跳变。 */

    function bootStyle(layout) {
        var l = layout || currentLayout();
        applyStyle(currentStyle(l));
        return l;
    }

    global.ctosPrefs = {
        LAYOUTS: LAYOUTS,
        STYLES: STYLES,
        DESKTOP_MIN_WIDTH: DESKTOP_MIN_WIDTH,
        isDesktop: isDesktop,
        storedLayout: storedLayout,
        currentLayout: currentLayout,
        setLayout: setLayout,
        goLayout: goLayout,
        currentStyle: currentStyle,
        setStyle: setStyle,
        stylesOf: stylesOf,
        applyStyle: applyStyle,
        bootStyle: bootStyle
    };
})(window);
