// 主题切换：三个主题，选择记在 localStorage 里，下次打开还是上次那个。
// 菜单用 Shoelace 的 sl-dropdown + sl-menu，页面头部的内联脚本会先按 localStorage 设一次。

(function () {
    const STORAGE_KEY = "ctos_theme";
    const THEMES = ["clean", "street", "cyber"];
    const DEFAULT_THEME = "clean";

    const root = document.documentElement;
    const dropdown = document.getElementById("theme-dropdown");
    const menu = document.getElementById("theme-menu");

    if (!menu) return;

    function currentTheme() {
        return THEMES.includes(root.dataset.theme) ? root.dataset.theme : DEFAULT_THEME;
    }

    function applyTheme(theme) {
        if (!THEMES.includes(theme)) theme = DEFAULT_THEME;

        root.dataset.theme = theme;
        root.classList.toggle("sl-theme-dark", theme === "cyber");

        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) {
            // 隐私模式 / 禁用存储时不影响切换
        }

        // 用属性而不是 property：Shoelace 还没升级完时也能正确标出当前项
        menu.querySelectorAll("sl-menu-item").forEach((item) => {
            if (item.getAttribute("value") === theme) {
                item.setAttribute("checked", "");
            } else {
                item.removeAttribute("checked");
            }
        });

        if (dropdown && typeof dropdown.hide === "function") dropdown.hide();
    }

    menu.addEventListener("sl-select", (event) => {
        const item = event.detail.item;
        applyTheme(item.value || item.getAttribute("value"));
    });

    // 初始化：把当前主题对应的菜单项标出来
    applyTheme(currentTheme());

    // 方便在控制台 / 自动化测试里直接切
    window.ctosApplyTheme = applyTheme;
})();
