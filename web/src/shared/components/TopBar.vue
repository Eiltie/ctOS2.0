<script setup lang="ts">
/**
 * 顶栏：品牌 + 三个模块 + 右侧状态。
 *
 * 顶栏只放「模块」，不放玩法。
 * 玩法在对话页内部那条玩法条上 —— 玩法再多也不会挤爆顶栏。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MODULES, moduleOfRoute } from '@/shared/lib/navigation'
import { authStore } from '@/shared/auth/authStore'
import AccountMenu from '@/shared/auth/AccountMenu.vue'
import AuthDialog from '@/shared/auth/AuthDialog.vue'
import FeedbackDialog from '@/shared/components/FeedbackDialog.vue'
import { drawer } from '@/shared/lib/drawer'

const route = useRoute()
const router = useRouter()

const currentModule = computed(() => moduleOfRoute(route.name))

/** 登录/注册弹层、反馈弹层 */
const authOpen = ref(false)
const feedbackOpen = ref(false)

/** 移动端：打开侧栏抽屉 */
function toggleDrawer() {
  drawer.toggle()
}

function go(path: string) {
  void router.push(path)
}
</script>

<template>
  <header class="topbar">
    <!--
      移动端：打开侧栏抽屉的汉堡按钮。
      桌面端隐藏（侧栏是常驻的，不需要按钮）。
    -->
    <button
      type="button"
      class="drawer-btn"
      aria-label="打开侧栏"
      @click="toggleDrawer"
    >
      <svg
        width="19"
        height="19"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        aria-hidden="true"
      >
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
    </button>

    <div class="brand">
      <span class="brand-mark">ct</span>
      <span class="brand-name">ctOS 2.0</span>
    </div>

    <nav class="tabs">
      <button
        v-for="mod in MODULES"
        :key="mod.path"
        class="tab"
        :class="{ 'tab--active': mod.path === currentModule.path }"
        type="button"
        @click="go(mod.path)"
      >
        <svg
          class="tab-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.9"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path :d="String(mod.icon)" />
        </svg>
        <span>{{ mod.label }}</span>
      </button>
    </nav>

    <div class="topbar-right">
      <!-- 账号：访客显示「访客」，点开能登录/注册/反馈 -->
      <AccountMenu
        v-if="!authStore.state.booting"
        @open-auth="authOpen = true"
        @open-feedback="feedbackOpen = true"
      />
      <span v-else class="who">连接中…</span>

      <slot name="right" />
    </div>

    <!-- 登录 / 注册弹层 -->
    <AuthDialog :open="authOpen" @close="authOpen = false" />

    <!-- 意见反馈 -->
    <FeedbackDialog :open="feedbackOpen" @close="feedbackOpen = false" />
  </header>
</template>

<style scoped>
.topbar {
  height: var(--h-topbar);
  display: flex;
  align-items: center;
  gap: var(--s-6);
  padding: 0 var(--s-6);
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

/* ---------- 品牌 ---------- */
.brand {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: var(--r-md);
  background: linear-gradient(140deg, #4a5058, var(--c-text));
  color: #fff;
  display: grid;
  place-items: center;
  font-size: var(--f-sm);
  font-weight: 700;
}

.brand-name {
  font-size: var(--f-lg);
  font-weight: 700;
  color: var(--c-coffee);
  letter-spacing: 0.2px;
}

/* ---------- 模块标签 ---------- */
.tabs {
  display: flex;
  gap: 2px;
  align-self: stretch;
}

.tab {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: 0 var(--s-4);
  margin: 12px 2px;
  border-radius: var(--r-md);
  font-size: var(--f-base);
  color: var(--c-text-2);
  transition:
    color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.tab:hover {
  color: var(--c-text);
  background: var(--c-bg-soft);
}

.tab--active {
  color: var(--c-coffee);
  font-weight: 600;
}

/* 选中时的下划线：压在顶栏底边线上 */
.tab--active::after {
  content: '';
  position: absolute;
  left: var(--s-4);
  right: var(--s-4);
  bottom: -1px;
  height: 2px;
  background: var(--c-brand);
  border-radius: 2px 2px 0 0;
}

.tab-icon {
  width: 16px;
  height: 16px;
  opacity: 0.75;
}

.tab--active .tab-icon {
  opacity: 1;
  color: var(--c-brand);
}

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.who {
  font-size: var(--f-sm);
  color: var(--c-text-2);
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--c-coffee-soft);
  color: var(--c-text-2);
  display: grid;
  place-items: center;
  font-size: var(--f-sm);
  font-weight: 600;
}

/* ============================================================================
   移动端（≤ 768px）
   ============================================================================ */

/* 汉堡按钮：桌面端不显示 */
.drawer-btn {
  display: none;
  width: 34px;
  height: 34px;
  border-radius: var(--r-md);
  color: var(--c-text-2);
  place-items: center;
  flex-shrink: 0;
}

.drawer-btn:hover {
  background: var(--c-bg-soft);
}

@media (max-width: 768px) {
  .topbar {
    gap: var(--s-2);
    padding: 0 var(--m-pad);
    height: var(--m-head);
  }

  .drawer-btn {
    display: grid;
  }

  /* 手机上品牌只留图标，省地方 */
  .brand-name {
    display: none;
  }

  .brand-mark {
    width: 28px;
    height: 28px;
    font-size: var(--f-xs);
  }

  /* 标签页：缩小、禁止换行。
     关键：white-space: nowrap —— 不然「对话」两个字会被拆成两行竖排 */
  .tabs {
    gap: 0;
    margin-left: auto;
    min-width: 0;
  }

  .tab {
    padding: 0 var(--s-2);
    margin: 0;
    gap: 0;
    font-size: var(--f-sm);
    white-space: nowrap;
    min-height: 34px;
  }

  /* 手机上标签只留文字，图标省掉 */
  .tab-icon {
    display: none;
  }

  .topbar-right {
    gap: 0;
    flex-shrink: 0;
  }

  /* 账号名占地方，手机上只留头像（点开菜单里能看到全名） */
  .topbar-right :deep(.who) {
    display: none;
  }
}</style>



