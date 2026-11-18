<script setup lang="ts">
/**
 * 角色档案面板（右侧抽屉）。
 *
 * 显示角色的完整设定：性格、事迹、背景、说话方式、开场白。
 * 数据来自 GET /roleplay/roles/{id}。
 */
import { roleplayStore } from './store'

const { state } = roleplayStore

/** 要显示的字段，按展示顺序排 */
const FIELDS: { key: keyof NonNullable<typeof state.profile>; label: string }[] = [
  { key: 'personality', label: '性格' },
  { key: 'speaking', label: '说话方式' },
  { key: 'age', label: '年龄' },
  { key: 'gender', label: '性别' },
  { key: 'deeds', label: '人物事迹' },
  { key: 'background', label: '背景故事' },
  { key: 'extra', label: '补充说明' },
]

/** 只显示有内容的字段 */
function visibleFields() {
  const profile = state.profile
  if (!profile) return []
  return FIELDS.filter(({ key }) => {
    const value = profile[key]
    return typeof value === 'string' && value.trim().length > 0
  })
}
</script>

<template>
  <Transition name="panel">
    <div v-if="state.profileOpen" class="panel-mask" @click.self="roleplayStore.closeProfile()">
      <aside class="panel">
        <header class="panel-head">
          <div class="panel-title">角色档案</div>
          <button type="button" class="panel-close" @click="roleplayStore.closeProfile()">
            ✕
          </button>
        </header>

        <div class="panel-body">
          <div v-if="state.profileLoading" class="panel-loading">加载中…</div>

          <template v-else-if="state.profile">
            <!-- 顶部：头像 + 名字 -->
            <div class="profile-hero">
              <span class="profile-emoji">{{ state.profile.emoji || '🎭' }}</span>
              <div>
                <div class="profile-name">{{ state.profile.name }}</div>
                <div v-if="state.profile.tagline" class="profile-tagline">
                  {{ state.profile.tagline }}
                </div>
              </div>
            </div>

            <!-- 各个字段 -->
            <dl class="profile-fields">
              <template v-for="{ key, label } in visibleFields()" :key="key">
                <dt>{{ label }}</dt>
                <dd>{{ state.profile[key] }}</dd>
              </template>
            </dl>

            <!-- 开场白单独一块，视觉上区分开 -->
            <div v-if="state.profile.opening" class="profile-opening">
              <div class="opening-label">开场白</div>
              <div class="opening-text">{{ state.profile.opening }}</div>
            </div>
          </template>
        </div>
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

/* ---------- 头部 ---------- */
.profile-hero {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--c-line);
  margin-bottom: var(--s-4);
}

.profile-emoji {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  font-size: 28px;
  border-radius: var(--r-lg);
  background: var(--c-bg-soft);
}

.profile-name {
  font-size: var(--f-lg);
  font-weight: 650;
}

.profile-tagline {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 2px;
}

/* ---------- 字段 ---------- */
.profile-fields {
  display: grid;
  gap: var(--s-3);
}

.profile-fields dt {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  font-weight: 600;
}

.profile-fields dd {
  font-size: var(--f-base);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
  margin: 0 0 var(--s-2);
}

/* ---------- 开场白 ---------- */
.profile-opening {
  margin-top: var(--s-4);
  padding: var(--s-3) var(--s-4);
  background: var(--c-bg-soft);
  border-radius: var(--r-lg);
}

.opening-label {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  font-weight: 600;
  margin-bottom: var(--s-1);
}

.opening-text {
  font-size: var(--f-base);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
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
