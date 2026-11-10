// 主题切换：三个主题，选择记在 localStorage 里，下次打开还是上次那个。
// 页面头部的内联脚本会先按 localStorage 设一次 data-theme，避免刷新时闪一下。

(function () {
    const STORAGE_KEY = "ctos_theme";
    const THEMES = ["clean", "street", "cyber"];
    const DEFAULT_THEME = "clean";

    const root = document.documentElement;
    const button = document.getElementById("theme-btn");
    const menu = document.getElementById("theme-menu");

    if (!button || !menu) return;

    function currentTheme() {
        return THEMES.includes(root.dataset.theme) ? root.dataset.theme : DEFAULT_THEME;
    }

    function closeMenu() {
        menu.classList.remove("show");
        button.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
        menu.classList.add("show");
        button.setAttribute("aria-expanded", "true");
    }

    function applyTheme(theme) {
        if (!THEMES.includes(theme)) theme = DEFAULT_THEME;

        root.dataset.theme = theme;

        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) {
            // 隐私模式 / 禁用存储时不影响切换
        }

        document.querySelectorAll(".theme-option").forEach((option) => {
            option.classList.toggle("is-active", option.dataset.themeChoice === theme);
        });

        closeMenu();
    }

    button.addEventListener("click", (event) => {
        event.stopPropagation();
        if (menu.classList.contains("show")) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    document.querySelectorAll(".theme-option").forEach((option) => {
        option.addEventListener("click", () => applyTheme(option.dataset.themeChoice));
    });

    document.addEventListener("click", (event) => {
        if (!menu.contains(event.target) && !button.contains(event.target)) {
            closeMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMenu();
    });

    // 初始化：把当前主题对应的选项标出来
    applyTheme(currentTheme());

    // 方便在控制台 / 自动化测试里直接切
    window.ctosApplyTheme = applyTheme;
})();
