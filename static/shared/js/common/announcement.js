// 更新公告：内容从后端 config/notice.json 读，前端不写死。
//
// 发新版时改 config/notice.json：
//   id 必须换一个，标题、日期、正文、条目一起改。
// 同一个 id 在这台电脑的浏览器里只自动弹一次；顶栏按钮随时能打开。

const NOTICE_SEEN_KEY = "ctos_notice_seen";

let currentNotice = null;
let noticeAutoChecked = false;

async function loadNotice() {
    // no-store：保证改完 notice.json 刷新就能拿到新内容，不被浏览器缓存
    const data = await getJson("/notice", { cache: "no-store" });
    if (!data || !data.notice || !data.notice.id) return null;
    return data.notice;
}

function renderNotice(notice) {
    const title = $("notice-title");
    const date = $("notice-date");
    const version = $("notice-version");
    const intro = $("notice-intro");
    const items = $("notice-items");

    if (title) title.textContent = notice.title || "更新公告";
    if (date) date.textContent = notice.date || "";
    if (version) version.textContent = notice.version || "";
    if (intro) intro.textContent = notice.intro || "";

    if (items) {
        const list = Array.isArray(notice.items) ? notice.items : [];
        items.innerHTML = list
            .map((text) => `<li>${esc(text)}</li>`)
            .join("");
    }
}

async function openNotice(notice) {
    if (!notice) notice = currentNotice || await loadNotice();
    if (!notice) {
        alert("暂时没有公告");
        return;
    }

    currentNotice = notice;
    renderNotice(notice);

    const modal = $("notice-modal");
    if (modal) modal.classList.add("show");

    // 打开就算看过了，刷新不会重复弹
    try {
        localStorage.setItem(NOTICE_SEEN_KEY, notice.id);
    } catch (e) {
        // 浏览器禁用了本地存储，就不记录，只保证这次能看
    }
}

function closeNotice() {
    const modal = $("notice-modal");
    if (modal) modal.classList.remove("show");
}

async function initUpdateNotice() {
    if (noticeAutoChecked) return;
    noticeAutoChecked = true;

    const notice = await loadNotice();
    if (!notice) return;

    currentNotice = notice;

    let seen = "";
    try {
        seen = localStorage.getItem(NOTICE_SEEN_KEY) || "";
    } catch (e) {
        seen = "";
    }

    if (seen === notice.id) return;
    openNotice(notice);
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeNotice();
});
