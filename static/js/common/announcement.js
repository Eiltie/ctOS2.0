// 更新公告：每次发版改这里，浏览器只会自动弹一次。

// 每次更新改这四样：id（必须变）、title、date、items。
// 同一个 id 在这台电脑的浏览器里只自动弹一次；手动按钮随时能打开。
const UPDATE_NOTICE = {
    id: "2026-11-11-roleplay",
    title: "角色扮演模块上线",
    date: "2026-11-11",
    version: "v2026.11.11",
    intro: "这次更新把闲聊做成了两种玩法。普通聊天还在，角色扮演是新的。",
    items: [
        "新增角色扮演：预设角色、自己写角色、AI 帮我查",
        "角色记忆：每聊 6 轮自动整理，可以查看和清空",
        "角色档案：聊天顶部可以查看完整设定",
        "角色聊天在左侧独立菜单，和普通聊天分开",
        "三套主题和手机端都做了适配",
    ],
};

// 存在浏览器本地，换电脑或换浏览器会重新弹一次
const NOTICE_SEEN_KEY = "ctos_notice_seen";

function renderNotice() {
    const title = $("notice-title");
    const date = $("notice-date");
    const version = $("notice-version");
    const intro = $("notice-intro");
    const items = $("notice-items");

    if (title) title.textContent = UPDATE_NOTICE.title;
    if (date) date.textContent = UPDATE_NOTICE.date;
    if (version) version.textContent = UPDATE_NOTICE.version;
    if (intro) intro.textContent = UPDATE_NOTICE.intro;

    if (items) {
        items.innerHTML = UPDATE_NOTICE.items
            .map((text) => `<li>${esc(text)}</li>`)
            .join("");
    }
}

function openNotice() {
    renderNotice();

    const modal = $("notice-modal");
    if (modal) modal.classList.add("show");

    // 打开就算看过了，刷新不会重复弹
    try {
        localStorage.setItem(NOTICE_SEEN_KEY, UPDATE_NOTICE.id);
    } catch (e) {
        // 浏览器禁用了本地存储，就不记录，只保证这次能看
    }
}

function closeNotice() {
    const modal = $("notice-modal");
    if (modal) modal.classList.remove("show");
}

function initUpdateNotice() {
    let seen = "";

    try {
        seen = localStorage.getItem(NOTICE_SEEN_KEY) || "";
    } catch (e) {
        seen = "";
    }

    if (seen === UPDATE_NOTICE.id) return;
    openNotice();
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeNotice();
});
