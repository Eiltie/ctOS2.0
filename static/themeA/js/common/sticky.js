// 吸顶高度同步：把元素实际高度写进 CSS 变量 --sticky-h。
//
// 解决什么问题：出行页的标题骨架是 position: sticky 吸顶的，
// 下面的内容区要留出和它一样高的 padding-top，否则会被盖住。
// 但骨架高度会变（示例卡显示/隐藏时），写死一个值会错位，
// 所以这里用 JS 实测高度再写回 CSS 变量。
//
// 挂在 resize / load / ResizeObserver 上，页面尺寸一变自动重算。

const stickyHeads = new WeakMap();

function syncStickyHeads(){
  document.querySelectorAll("[data-sticky-head]").forEach((head) => {
    const host = head.parentElement;
    if (!host) return;
    const h = head.offsetHeight;
    if (stickyHeads.get(host) === h) return;   // 没变就不写，省得反复触发重排
    stickyHeads.set(host, h);
    host.style.setProperty("--sticky-h", h + "px");
  });
}

window.addEventListener("resize", syncStickyHeads);
window.addEventListener("load", syncStickyHeads);

if (typeof ResizeObserver === "function"){
  const ro = new ResizeObserver(() => syncStickyHeads());
  document.querySelectorAll("[data-sticky-head]").forEach((h) => ro.observe(h));
}
