<script setup lang="ts">
/**
 * 角色记忆面板。
 *
 * 后端每聊 6 轮会把对话压缩成一段记忆摘要（见 modules/chat/roleplay/memory.py），
 * 这个角色下次说话时会带上它。这里让用户能看到「它还记着些什么」，也能清空。
 */
import { ref } from 'vue'
import { roleplayStore } from './store'
import { chatStore } from '../store'

const { state } = roleplayStore

const clearing = ref(false)

async function doClear() {
  const roleId = chatStore.state.activeRoleId
  if (!roleId) return
  if (!confirm('清空这个角色的记忆？之后它不会再记得你们之前的对话。')) return

  clearing.value = true
  try {
    await roleplayStore.wipeMemory(roleId)
  } finally {
    clearing.value = false
  }
}
</script>

<template>
  <Transition name="panel">
    <div v-if="state.memoryOpen" class="panel-mask" @click.self="roleplayStore.closeMemory()">
      <aside class="panel">
        <header class="panel-head">
          <div class="panel-title">它记住的事</div>
          <button type="button" class="panel-close" @click="roleplayStore.closeMemory()">
            ✕
          </button>
        </header>

        <div class="panel-body">
          <div v-if="state.memoryLoading" class="panel-loading">加载中…</div>

          <template v-else-if="state.memoryText">
            <div class="memory-text">{{ state.memoryText }}</div>
            <p class="memory-note">
              每聊 6 轮，系统会把对话压缩成一段记忆。角色之后会根据它来理解你说过的事。
            </p>
          </template>

          <div v-else class="memory-empty">
            <div class="empty-icon">🌱</div>
            <div class="empty-title">还没有记忆</div>
            <p class="empty-desc">
              多聊几轮（每 6 轮整理一次），它会慢慢记住你们之间发生过什么。
            </p>
          </div>
        </div>

        <footer v-if="state.memoryText" class="panel-foot">
          <button type="button" class="danger-btn" :disabled="clearing" @click="doClear">
            {{ clearing ? '清空中…' : '清空记忆' }}
          </button>
        </footer>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.panel-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.18);
  z-index: var(--z-modal);
  display: flex;
  justify-content: flex-end;
}

.panel {
  width: min(420px, 92vw);
  height: 100%;
  background: var(--c-bg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--sh-pop);
}

.panel-head {
  height: var(--h-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.panel-title {
  font-size: var(--f-md);
  font-weight: 650;
}

.panel-close {
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  display: grid;
  place-items: center;
  font-size: 13px;
}

.panel-close:hover {
  background: var(--c-bg-hover);
  color: var(--c-text);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-5);
}

.panel-loading {
  text-align: center;
  padding: var(--s-8);
  color: var(--c-text-3);
  font-size: var(--f-sm);
}

.memory-text {
  font-size: var(--f-base);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
  white-space: pre-wrap;
  padding: var(--s-4);
  background: var(--c-bg-soft);
  border-radius: var(--r-lg);
}

.memory-note {
  margin-top: var(--s-3);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

/* ---------- 空状态 ---------- */
.memory-empty {
  text-align: center;
  padding: var(--s-8) var(--s-4);
}

.empty-icon {
  font-size: 28px;
  opacity: 0.6;
}

.empty-title {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text-2);
  margin-top: var(--s-2);
}

.empty-desc {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: var(--s-1);
  line-height: var(--lh-normal);
}

/* ---------- 底部 ---------- */
.panel-foot {
  padding: var(--s-4) var(--s-5);
  border-top: 1px solid var(--c-line);
  flex-shrink: 0;
}

.danger-btn {
  width: 100%;
  padding: 9px;
  border-radius: var(--r-md);
  border: 1px solid var(--c-line-strong);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-danger);
  transition: background var(--t-fast) var(--ease-soft);
}

.danger-btn:hover:not(:disabled) {
  background: var(--c-danger-soft);
}

.danger-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* ---------- 过渡 ---------- */
.panel-enter-active,
.panel-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.panel-enter-active .panel,
.panel-leave-active .panel {
  transition: transform var(--t-normal) var(--ease-soft);
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.panel-enter-from .panel,
.panel-leave-to .panel {
  transform: translateX(100%);
}
</style>
