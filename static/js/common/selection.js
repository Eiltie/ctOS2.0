// 会话列表的「多选删除」：闲聊和出行共用这一套。
//
// 进入多选后标题变成「选择对话」，每行前面出现圆形勾选圈，
// 底部出现「N 项已选 / 删除」操作条。
//
// 为什么抽出来：闲聊和出行的列表长得不一样，但多选逻辑完全一致。
// 原来这段写在 app.js 里，出行那边要调用就得依赖 app.js 的全局变量。

// 是否处在多选模式
let historySelectMode = false;

// 被勾选的 id 集合
let historyPicked = new Set();

// 图标：三横线 + 圆圈，表示「列表多选」
const ICON_SELECT_SVG = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none"
    stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
    <circle cx="3" cy="4" r="1.1" fill="currentColor" stroke="none"/>
    <circle cx="3" cy="8" r="1.1" fill="currentColor" stroke="none"/>
    <circle cx="3" cy="12" r="1.1" fill="currentColor" stroke="none"/>
    <line x1="6.5" y1="4" x2="14" y2="4"/>
    <line x1="6.5" y1="8" x2="14" y2="8"/>
    <line x1="6.5" y1="12" x2="14" y2="12"/>
  </svg>`;

// 图标：叉号，表示「退出多选」
const ICON_CLOSE_SVG = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none"
    stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
    <line x1="4" y1="4" x2="12" y2="12"/>
    <line x1="12" y1="4" x2="4" y2="12"/>
  </svg>`;

// 当前模块支不支持多选：客服不支持（它没有会话列表）
function historySelectable(){
  return state.view === "chat" || state.view === "trip";
}

// 更新左侧标题行：文字 + 右上角多选按钮
function renderHistoryTitle(){
  const text = $("history-title-text");
  const btn = $("history-select-btn");
  if (!text || !btn) return;

  text.textContent = historySelectMode ? "选择对话" : "会话记录";

  btn.style.display = historySelectable() ? "" : "none";
  btn.innerHTML = historySelectMode ? ICON_CLOSE_SVG : ICON_SELECT_SVG;
  btn.title = historySelectMode ? "退出多选" : "多选";
  btn.onclick = () => {
    historySelectMode = !historySelectMode;
    historyPicked.clear();
    renderHistory();
  };
}

// 生成一行的勾选圈；不在多选模式时返回空字符串
function pickDotHTML(id){
  if (!historySelectMode) return "";
  const on = historyPicked.has(Number(id)) ? " on" : "";
  return `<span class="pick-dot${on}" data-pick="${id}"></span>`;
}

// 给列表里的勾选圈绑定点击
function bindPickDots(box, repaint){
  box.querySelectorAll(".pick-dot").forEach((dot) => {
    dot.onclick = (e) => {
      e.stopPropagation();               // 别触发打开会话
      const id = Number(dot.dataset.pick);
      if (historyPicked.has(id)) historyPicked.delete(id);
      else historyPicked.add(id);
      repaint();
    };
  });
}

// 多选模式下底部的操作条
function selectBarHTML(){
  if (!historySelectMode) return "";
  const n = historyPicked.size;
  return `<div class="history-select-bar">` +
           `<span class="hsb-link" data-hsb="all">${n} 项已选</span>` +
           `<span class="hsb-del${n ? "" : " disabled"}" data-hsb="del">删除</span>` +
         `</div>`;
}

// 给底部操作条绑定点击
//   total     总条数，用来判断「全选」还是「清空」
//   onPickAll 全选时怎么填 historyPicked
//   onDelete  点删除时调什么
//   repaint   重画列表的函数（闲聊和出行各自的）
function bindSelectBar(box, total, onPickAll, onDelete, repaint){
  const all = box.querySelector('[data-hsb="all"]');
  if (all){
    all.onclick = () => {
      if (total && historyPicked.size === total) historyPicked.clear();
      else onPickAll();
      repaint();
    };
  }

  const del = box.querySelector('[data-hsb="del"]');
  if (del && historyPicked.size){
    del.onclick = () => onDelete([...historyPicked]);
  }
}
