// 光标光晕：跟随鼠标的一团光，带平滑跟随（缓动）。
//
// 纯装饰效果，不参与任何业务逻辑。
// 鼠标离开窗口时淡出，避免光晕停在边缘。
//
// 手机上没有鼠标，跑这个动画只是白耗电，所以触摸设备直接不启动。
//
// ── 性能说明（重要）────────────────────────────────────────
// 原来的写法是「无条件 rAF 递归」：每帧都写一次 aura.style.transform，
// 哪怕鼠标根本没动、光晕也停在原地。
// 后果是每秒 60 次无意义的样式写入 → 每次都会让样式失效、触发重绘，
// 空闲时也在占 CPU（实测空闲 rAF 频率高达 360 次/秒，
// 因为页面上还有别的 rAF 在跑，这个循环叠上去就把空闲帧率拉爆了）。
//
// 现在的做法：
//   1. 只有鼠标移动过、且光晕还没追上目标时才跑动画
//   2. 追上之后自动停下，等下一次 mousemove 再启动
//   3. 页面不可见（切到别的标签）时也停
// 视觉上完全一样（缓动系数没变），但鼠标不动时 CPU 占用归零。
// ──────────────────────────────────────────────────────────

const aura = $("cursor-aura");

// 触摸设备（手机/平板）：不启用光晕
const isTouchDevice = window.matchMedia("(hover: none)").matches;

let mouseX = 0, mouseY = 0;
let auraX = 0, auraY = 0;

/** 缓动系数：越小跟得越慢、越有拖尾感 */
const EASE = 0.15;
/** 距离小于这个值就认为「追上了」，停止动画 */
const SNAP = 0.5;

let rafId = 0;
let running = false;

function tick(){
  rafId = 0;
  if (!aura || !running) return;

  auraX += (mouseX - auraX) * EASE;
  auraY += (mouseY - auraY) * EASE;

  // 只写着色器能直接用的 transform（不会触发重排）
  aura.style.transform = `translate(${auraX}px, ${auraY}px) translate(-50%, -50%)`;

  const dx = Math.abs(mouseX - auraX);
  const dy = Math.abs(mouseY - auraY);

  if (dx < SNAP && dy < SNAP){
    // 已经贴住目标了，停下来等下一次鼠标移动
    auraX = mouseX;
    auraY = mouseY;
    aura.style.transform = `translate(${auraX}px, ${auraY}px) translate(-50%, -50%)`;
    running = false;
    return;
  }

  rafId = requestAnimationFrame(tick);
}

function start(){
  if (running || !aura) return;
  // 页面在后台时不跑（看不到的动画没必要算）
  if (document.hidden) return;
  running = true;
  if (!rafId) rafId = requestAnimationFrame(tick);
}

function stop(){
  running = false;
  if (rafId){
    cancelAnimationFrame(rafId);
    rafId = 0;
  }
}

if (!isTouchDevice){
  document.addEventListener("mousemove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    if (aura && aura.style.opacity === "0") aura.style.opacity = "1";
    start();
  }, { passive: true });

  document.addEventListener("mouseleave", () => {
    if (aura) aura.style.opacity = "0";
    // 鼠标离开窗口：光晕淡出，动画也没必要继续
    stop();
  });

  // 切到后台标签页时停，回来时如果鼠标位置没变就不用重启
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
}
