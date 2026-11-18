<script setup lang="ts">
/**
 * 新建角色面板。
 *
 * 两种入口共用这一个表单：
 *   自己写一个     —— 空白表单，用户自己填
 *   AI 帮我查      —— 用户输入一句话，点「生成」，AI 联网搜资料后把内容填进表单，
 *                    用户可以先改再保存
 *
 * 几个必须和后端对齐的点：
 *   · 每个字段都有长度上限（见 LIMITS），和后端 clean_text 的截断一致，
 *     前端先限制住，用户能直观看到还能输多少，不至于写完被悄悄截掉。
 *   · 开场白不用单独字段 —— 后端约定写在「补充说明」里，格式是「开场白：xxx」。
 *     为了不让用户记这个格式，这里做了一个独立的开场白输入框，
 *     提交时拼进 extra。
 *   · 不写开场白的话，后端会让模型生成一句，这需要几秒。
 */
import { computed, reactive, ref, watch } from 'vue'
import { roleplayStore } from './store'
import type { RoleCard, RoleProfile } from '@/shared/types/api'

const props = defineProps<{
  open: boolean
  /** 打开时预填的内容（AI 生成的草稿） */
  initial?: RoleProfile | null
}>()

const emit = defineEmits<{
  close: []
  saved: [role: RoleCard]
}>()

/** 和后端 clean_text 的上限一致 */
const LIMITS = {
  name: 20,
  emoji: 4,
  tagline: 30,
  age: 20,
  gender: 10,
  personality: 200,
  deeds: 300,
  background: 300,
  speaking: 200,
  extra: 300,
  opening: 200,
} as const

interface FormState {
  emoji: string
  name: string
  tagline: string
  age: string
  gender: string
  personality: string
  deeds: string
  background: string
  speaking: string
  extra: string
  opening: string
}

function emptyForm(): FormState {
  return {
    emoji: '🎭',
    name: '',
    tagline: '',
    age: '',
    gender: '',
    personality: '',
    deeds: '',
    background: '',
    speaking: '',
    extra: '',
    opening: '',
  }
}

const form = reactive<FormState>(emptyForm())

const saving = ref(false)
const error = ref('')

/** 面板打开时重置表单，有草稿就填进去 */
watch(
  () => props.open,
  (open) => {
    if (!open) return
    Object.assign(form, emptyForm())
    error.value = ''

    if (props.initial) {
      Object.assign(form, {
        emoji: props.initial.emoji || '🎭',
        name: props.initial.name || '',
        tagline: props.initial.tagline || '',
        age: props.initial.age || '',
        gender: props.initial.gender || '',
        personality: props.initial.personality || '',
        deeds: props.initial.deeds || '',
        background: props.initial.background || '',
        speaking: props.initial.speaking || '',
        extra: props.initial.extra || '',
        opening: props.initial.opening || '',
      })
    }
  },
  { immediate: true },
)

const canSave = computed(() => form.name.trim().length > 0 && !saving.value)

/** 这个角色从哪来的：有草稿就是 AI 生成的 */
const source = computed<'custom' | 'ai_search'>(() => (props.initial ? 'ai_search' : 'custom'))

async function save() {
  if (!canSave.value) return

  saving.value = true
  error.value = ''

  try {
    // 开场白按后端约定拼进「补充说明」
    const extra = form.opening.trim()
      ? `${form.extra.trim()}\n开场白：${form.opening.trim()}`.trim()
      : form.extra.trim()

    const role = await roleplayStore.saveRole({
      name: form.name,
      emoji: form.emoji,
      tagline: form.tagline,
      age: form.age,
      gender: form.gender,
      personality: form.personality,
      deeds: form.deeds,
      background: form.background,
      speaking: form.speaking,
      extra,
      source: source.value,
    })

    emit('saved', role)
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    saving.value = false
  }
}

/** 常用 emoji，省得用户自己找 */
const EMOJIS = ['🎭', '🐒', '😼', '💼', '📚', '🧙', '👩‍🏫', '🧑‍🍳', '🎸', '🕵️', '🐱', '🌟']
</script>

<template>
  <Transition name="panel">
    <div v-if="open" class="panel-mask" @click.self="emit('close')">
      <aside class="panel">
        <header class="panel-head">
          <div>
            <div class="panel-title">{{ initial ? '确认 AI 生成的角色' : '自己写一个角色' }}</div>
            <div class="panel-sub">
              {{ initial ? '下面的内容可以改，确认无误再保存' : '填得越具体，角色越像' }}
            </div>
          </div>
          <button type="button" class="panel-close" @click="emit('close')">✕</button>
        </header>

        <div class="panel-body">
          <!-- 头像 + 名字 + 标签 -->
          <div class="form-row form-row--hero">
            <div class="field field--emoji">
              <label class="label">头像</label>
              <input
                v-model="form.emoji"
                class="input input--emoji"
                :maxlength="LIMITS.emoji"
              />
            </div>
            <div class="field">
              <label class="label">名字<span class="req">*</span></label>
              <input
                v-model="form.name"
                class="input"
                :maxlength="LIMITS.name"
                placeholder="角色叫什么"
              />
              <span class="counter">{{ form.name.length }}/{{ LIMITS.name }}</span>
            </div>
          </div>

          <!-- emoji 快选 -->
          <div class="emoji-picks">
            <button
              v-for="e in EMOJIS"
              :key="e"
              type="button"
              class="emoji-pick"
              :class="{ 'emoji-pick--on': form.emoji === e }"
              @click="form.emoji = e"
            >
              {{ e }}
            </button>
          </div>

          <div class="field">
            <label class="label">一句话标签</label>
            <input
              v-model="form.tagline"
              class="input"
              :maxlength="LIMITS.tagline"
              placeholder="比如：狂妄 · 直爽"
            />
            <span class="counter">{{ form.tagline.length }}/{{ LIMITS.tagline }}</span>
          </div>

          <div class="form-row">
            <div class="field">
              <label class="label">年龄</label>
              <input v-model="form.age" class="input" :maxlength="LIMITS.age" placeholder="选填" />
            </div>
            <div class="field">
              <label class="label">性别</label>
              <input
                v-model="form.gender"
                class="input"
                :maxlength="LIMITS.gender"
                placeholder="选填"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">性格</label>
            <textarea
              v-model="form.personality"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.personality"
              placeholder="他/她是个什么样的人"
            />
            <span class="counter">{{ form.personality.length }}/{{ LIMITS.personality }}</span>
          </div>

          <div class="field">
            <label class="label">说话方式</label>
            <textarea
              v-model="form.speaking"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.speaking"
              placeholder="比如：说话短、快、带刺，常用反问句"
            />
            <span class="counter">{{ form.speaking.length }}/{{ LIMITS.speaking }}</span>
          </div>

          <div class="field">
            <label class="label">人物事迹</label>
            <textarea
              v-model="form.deeds"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.deeds"
              placeholder="他做过什么，选填"
            />
            <span class="counter">{{ form.deeds.length }}/{{ LIMITS.deeds }}</span>
          </div>

          <div class="field">
            <label class="label">背景故事</label>
            <textarea
              v-model="form.background"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.background"
              placeholder="他的来历，选填"
            />
            <span class="counter">{{ form.background.length }}/{{ LIMITS.background }}</span>
          </div>

          <div class="field">
            <label class="label">开场白</label>
            <textarea
              v-model="form.opening"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.opening"
              placeholder="角色说的第一句话。留空的话会让 AI 生成一句（需要几秒）"
            />
            <span class="counter">{{ form.opening.length }}/{{ LIMITS.opening }}</span>
          </div>

          <div class="field">
            <label class="label">补充说明</label>
            <textarea
              v-model="form.extra"
              class="input textarea"
              rows="2"
              :maxlength="LIMITS.extra"
              placeholder="兴趣爱好、口头禅之类的，选填"
            />
            <span class="counter">{{ form.extra.length }}/{{ LIMITS.extra }}</span>
          </div>

          <div v-if="error" class="form-error">{{ error }}</div>
        </div>

        <footer class="panel-foot">
          <button type="button" class="ghost-btn" @click="emit('close')">取消</button>
          <button type="button" class="primary-btn" :disabled="!canSave" @click="save">
            {{ saving ? '保存中…' : initial ? '保存这个角色' : '创建角色' }}
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
  width: min(500px, 94vw);
  height: 100%;
  background: var(--c-bg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--sh-pop);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.panel-title {
  font-size: var(--f-md);
  font-weight: 650;
}

.panel-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 2px;
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
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

/* ---------- 字段 ---------- */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}

.form-row--hero {
  grid-template-columns: 64px 1fr;
}

.field {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label {
  font-size: var(--f-sm);
  font-weight: 600;
  color: var(--c-text-2);
}

.req {
  color: var(--c-danger);
  margin-left: 2px;
}

.input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    box-shadow var(--t-fast) var(--ease-soft);
}

.input::placeholder {
  color: var(--c-text-3);
}

.input:focus {
  outline: none;
  border-color: var(--c-brand-line);
  box-shadow: 0 0 0 3px var(--c-brand-glow);
}

.textarea {
  resize: vertical;
  line-height: var(--lh-normal);
  font-family: inherit;
}

.input--emoji {
  text-align: center;
  font-size: 24px;
  padding: 8px 4px;
}

/* 字数提示：贴在字段右下 */
.counter {
  align-self: flex-end;
  font-size: 10px;
  color: var(--c-text-3);
  margin-top: -2px;
}

/* ---------- emoji 快选 ---------- */
.emoji-picks {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
  margin-top: calc(-1 * var(--s-2));
}

.emoji-pick {
  width: 30px;
  height: 30px;
  border-radius: var(--r-sm);
  font-size: 16px;
  display: grid;
  place-items: center;
  transition: background var(--t-fast) var(--ease-soft);
}

.emoji-pick:hover {
  background: var(--c-bg-hover);
}

.emoji-pick--on {
  background: var(--c-bg-hover);
  outline: 1.5px solid var(--c-line-strong);
}

/* ---------- 错误 ---------- */
.form-error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 8px 12px;
}

/* ---------- 底部 ---------- */
.panel-foot {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-4) var(--s-5);
  border-top: 1px solid var(--c-line);
  flex-shrink: 0;
}

.ghost-btn {
  padding: 8px 16px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
}

.ghost-btn:hover {
  background: var(--c-bg-soft);
}

.primary-btn {
  padding: 8px 20px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-sm);
  font-weight: 600;
  transition: background var(--t-fast) var(--ease-soft);
}

.primary-btn:hover:not(:disabled) {
  background: var(--c-brand-deep);
}

.primary-btn:disabled {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
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
