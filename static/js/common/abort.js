// 请求中断控制：同一时刻只允许一个流在跑。
//
// 为什么要统一管：三个模块都会发起流式请求，用户在出行模块等得烦了
// 切到客服去问，如果不中断上一个，两个流会同时往不同区域写字，
// 而且后端还在继续烧模型额度。
//
// 用法：
//   const ctl = newAbortController();      // 自动中断上一个
//   fetch(url, { signal: ctl.signal });
//   finishAbort(ctl);                     // 结束时清掉

let currentAbort = null;

function newAbortController(){
  if (currentAbort) currentAbort.abort();
  currentAbort = new AbortController();
  return currentAbort;
}

// 本次请求正常结束：只有当它还是「当前那个」时才清空
function finishAbort(ctl){
  if (currentAbort === ctl) currentAbort = null;
}

function currentSignal(){
  return currentAbort ? currentAbort.signal : undefined;
}

// 主动中断（切换视图、点新会话时调用）
function abortCurrent(){
  if (currentAbort) currentAbort.abort();
  currentAbort = null;
}
