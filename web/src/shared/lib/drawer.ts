/**
 * 移动端侧栏抽屉的开合状态。
 *
 * 为什么放这里而不是放在某个页面里：
 *   按钮在顶栏（TopBar），要控制的是页面里的侧栏（SessionList / TripList）。
 *   两者不在同一个组件树分支上，只能通过共享状态沟通。
 *
 * 为什么不用 provide/inject：
 *   AppShell 只是 RouterView 的容器，抽屉状态要跨到 RouterView 里面，
 *   用模块级状态最直接，也和项目里其他 store 的写法一致。
 *
 * 桌面端（> 768px）永远当作「展开」—— 那边侧栏是常驻的，没有抽屉这回事。
 * 组件里判断时应该用 isMobile()，不要直接读 open。
 */
import { ref } from 'vue'

/** 抽屉是否打开 */
const open = ref(false)

/** 现在的视口是不是手机尺寸 */
function isMobile(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(max-width: 768px)').matches
}

function toggle() {
  open.value = !open.value
}

function close() {
  open.value = false
}

/** 打开（点汉堡按钮时用） */
function show() {
  open.value = true
}

export const drawer = {
  open,
  isMobile,
  toggle,
  close,
  show,
}
