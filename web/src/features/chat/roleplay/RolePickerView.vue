<script setup lang="ts">
/**
 * 对话 · 角色扮演 —— 选角色。
 *
 * 结构：
 *   左侧仍然是会话列表（角色会话和闲聊共用一套）
 *   右侧是角色卡片墙：预设角色 / 我创建的角色 / 新建入口
 *
 * 两个新建入口：
 *   自己写一个   → RoleFormPanel（空表单）
 *   AI 帮我查    → RoleSearchPanel（生成草稿）→ RoleFormPanel（预填，可改后保存）
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SessionList from '../SessionList.vue'
import SidebarDrawer from '@/shared/components/SidebarDrawer.vue'
import { chatStore } from '../store'
import { roleplayStore } from './store'
import RoleCardItem from './RoleCardItem.vue'
import RoleFormPanel from './RoleFormPanel.vue'
import RoleSearchPanel from './RoleSearchPanel.vue'
import EmptyState from '@/shared/components/EmptyState.vue'
import type { RoleCard, RoleProfile } from '@/shared/types/api'

const router = useRouter()
const { state } = roleplayStore

// 三个面板的开关
const formOpen = ref(false)
const searchOpen = ref(false)
/** 表单打开时要预填的草稿（AI 生成的） */
const formInitial = ref<RoleProfile | null>(null)

onMounted(() => {
  void roleplayStore.loadRoles()
})

/** 打开空白表单：自己写一个 */
function openBlankForm() {
  formInitial.value = null
  formOpen.value = true
}

/** 打开 AI 查询面板 */
function openSearch() {
  searchOpen.value = true
}

/** AI 生成完成：关掉查询面板，打开预填好的表单 */
function onDraftReady() {
  formInitial.value = roleplayStore.state.draft
  searchOpen.value = false
  formOpen.value = true
}

/** 表单保存成功 */
function onSaved(role: RoleCard) {
  formInitial.value = null
  // 列表已经在 saveRole 里刷新过了，这里不用再做别的
  void role
}

/** 选一个角色开始聊 */
async function pick(role: RoleCard) {
  try {
    // 1. 后端建会话 + 写入开场白，返回会话 id
    const sessionId = await roleplayStore.beginWith(role)

    // 2. 让 chatStore 接手：打开这个会话
    //    preserveRole：这个会话刚建好，本地列表里还没有它，
    //    不保留的话就会被当成普通闲聊
    chatStore.setActiveRole(role.id)
    await chatStore.openSession(sessionId, { preserveRole: true })

    // 3. 切到对话页
    await router.push({ name: 'chat' })
  } catch (error) {
    state.error = error instanceof Error ? error.message : '开始对话失败'
  }
}
</script>

<template>
  <div class="roles-view">
    <SidebarDrawer>
      <SessionList />
    </SidebarDrawer>

    <main class="roles-main">
      <div class="roles-head">
        <div>
          <div class="roles-title">对话 · 角色扮演</div>
          <div class="roles-sub">挑一个角色开始对话，或者自己捏一个</div>
        </div>
        <button type="button" class="ghost-btn" @click="router.push({ name: 'chat' })">
          返回闲聊
        </button>
      </div>

      <div class="roles-feed">
        <div class="roles-inner">
          <!-- 加载中 -->
          <div v-if="state.loading" class="roles-loading">角色加载中…</div>

          <!-- 加载失败 -->
          <EmptyState
            v-else-if="state.error"
            icon="⚠️"
            title="角色列表加载失败"
            :description="state.error"
          >
            <button type="button" class="retry-btn" @click="roleplayStore.loadRoles()">
              重试
            </button>
          </EmptyState>

          <template v-else>
            <div class="roles-hero">
              <h2>和谁聊？</h2>
              <p>每个角色有自己的性格、说话方式和记忆</p>
            </div>

            <!-- 预设角色 -->
            <div class="group-label">预设角色</div>
            <div class="role-grid">
              <RoleCardItem
                v-for="role in roleplayStore.presetRoles.value"
                :key="role.id"
                :role="role"
                @pick="pick"
              />
            </div>

            <!-- 我创建的角色 -->
            <div class="group-label">我创建的角色</div>
            <div class="role-grid">
              <RoleCardItem
                v-for="role in roleplayStore.customRoles.value"
                :key="role.id"
                :role="role"
                mine
                @pick="pick"
                @remove="roleplayStore.removeRole(role.id)"
              />

              <button type="button" class="role-card role-card--add" @click="openBlankForm">
                <span class="add-icon">＋</span>
                <span class="add-label">自己写一个</span>
                <span class="add-hint">按你的设定来</span>
              </button>
              <button type="button" class="role-card role-card--add" @click="openSearch">
                <span class="add-icon">✨</span>
                <span class="add-label">AI 帮我查</span>
                <span class="add-hint">联网搜资料生成</span>
              </button>
            </div>
          </template>
        </div>
      </div>

      <!-- 三个面板：空白表单 / AI 查询 / AI 草稿确认表单 -->
      <RoleFormPanel
        :open="formOpen"
        :initial="formInitial"
        @close="formOpen = false"
        @saved="onSaved"
      />
      <RoleSearchPanel :open="searchOpen" @close="searchOpen = false" @done="onDraftReady" />
    </main>
  </div>
</template>

<style scoped>
.roles-view {
  flex: 1;
  display: flex;
  min-height: 0;
}

.roles-sidebar {
  width: var(--w-sidebar);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-bg-sidebar);
  border-right: 1px solid var(--c-line);
  min-height: 0;
}

.roles-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.roles-head {
  height: var(--h-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.roles-title {
  font-size: var(--f-md);
  font-weight: 650;
}

.roles-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 1px;
}

.ghost-btn {
  padding: 6px 11px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  transition: background var(--t-fast) var(--ease-soft);
}

.ghost-btn:hover {
  background: var(--c-bg-soft);
}

.roles-feed {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.roles-inner {
  max-width: var(--w-content);
  margin: 0 auto;
  padding: var(--s-6) var(--s-5) var(--s-8);
}

.roles-loading {
  text-align: center;
  padding: var(--s-8);
  color: var(--c-text-3);
  font-size: var(--f-sm);
}

.roles-hero {
  text-align: center;
  padding: var(--s-2) 0 var(--s-6);
}

.roles-hero h2 {
  font-size: var(--f-xl);
  font-weight: 650;
  color: var(--c-text);
}

.roles-hero p {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 6px;
}

.group-label {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: var(--s-5) 0 var(--s-3);
  font-size: var(--f-sm);
  font-weight: 650;
  color: var(--c-text-3);
  letter-spacing: 0.4px;
}

.group-label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--c-line);
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: var(--s-3);
}

/* ---------- 新建入口卡 ---------- */
.role-card--add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1.5px dashed var(--c-line-strong);
  border-radius: var(--r-xl);
  background: transparent;
  padding: var(--s-5) var(--s-3);
  min-height: 132px;
  cursor: pointer;
  color: var(--c-text-3);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft);
}

.role-card--add:hover {
  border-color: var(--c-text-3);
  background: var(--c-bg-soft);
  color: var(--c-text-2);
}

.add-icon {
  font-size: 22px;
  line-height: 1;
}

.add-label {
  font-size: var(--f-base);
  font-weight: 600;
  margin-top: var(--s-2);
  color: var(--c-text-2);
}

.add-hint {
  font-size: var(--f-xs);
  margin-top: 3px;
}

.retry-btn {
  margin-top: var(--s-3);
  padding: 6px 14px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-brand-deep);
}

/* ---------- 窄屏（≤ 768px）---------- */
@media (max-width: 768px) {
  .roles-head {
    padding: 0 var(--m-pad);
  }

  .roles-feed {
    padding-top: var(--s-5);
  }

  .roles-inner {
    padding: 0 var(--m-pad);
  }

  /* 角色卡片：手机上两列太挤，改成一列 */
  .role-grid {
    grid-template-columns: 1fr;
  }
}</style>


