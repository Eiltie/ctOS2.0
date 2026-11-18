<script setup lang="ts">
/**
 * 登录 / 注册弹层。
 *
 * 为什么是弹层而不是独立页面：
 *   访客模式下用户已经在用了，登录是把「访客记录」升级成「正式账号」的动作，
 *   不该把他踢到一个空白的登录页。
 *
 * 后端的规则（api/routes/auth.py）：
 *   邮箱：简单正则，够用就好
 *   密码：至少 6 位，最多 72 位（bcrypt 只看前 72 字节）
 *   错误文案直接显示后端返回的 detail
 */
import { computed, reactive, ref, watch } from 'vue'
import { authStore } from '@/shared/auth/authStore'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

type Mode = 'login' | 'register'

const mode = ref<Mode>('login')
const submitting = ref(false)
const error = ref('')

const form = reactive({
  email: '',
  password: '',
  displayName: '',
  /** 注册时的确认密码 */
  confirm: '',
})

/** 切模式时清掉错误和密码（别让用户以为登录失败） */
watch(mode, () => {
  error.value = ''
  form.password = ''
  form.confirm = ''
})

/** 打开时重置 */
watch(
  () => props.open,
  (open) => {
    if (!open) return
    error.value = ''
    form.password = ''
    form.confirm = ''
  },
)

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** 前端先校验一遍，错在哪能立刻说 */
const validation = computed(() => {
  if (!form.email.trim()) return '请输入邮箱'
  if (!EMAIL_RE.test(form.email.trim())) return '邮箱格式不对'
  if (form.password.length < 6) return '密码至少要 6 位'
  if (form.password.length > 72) return '密码不能超过 72 位'
  if (mode.value === 'register' && form.password !== form.confirm) {
    return '两次输入的密码不一样'
  }
  return ''
})

const canSubmit = computed(
  () => !validation.value && !submitting.value,
)

async function submit() {
  if (!canSubmit.value) return

  submitting.value = true
  error.value = ''

  try {
    if (mode.value === 'login') {
      await authStore.login(form.email.trim(), form.password)
    } else {
      await authStore.register(
        form.email.trim(),
        form.password,
        form.displayName.trim(),
      )
    }
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败，请稍后再试'
  } finally {
    submitting.value = false
  }
}

/** 游客身份下也能直接退出登录，回到访客模式 */
async function backToGuest() {
  submitting.value = true
  try {
    await authStore.startGuest()
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Transition name="modal">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="dialog" role="dialog" aria-modal="true">
        <button type="button" class="dialog-close" @click="emit('close')">✕</button>

        <div class="dialog-head">
          <div class="brand">ct</div>
          <h2>{{ mode === 'login' ? '登录' : '注册' }}</h2>
          <p class="sub">
            {{
              mode === 'login'
                ? '登录后可以在不同设备上查看记录'
                : '注册一个账号，聊天和出行记录都会保存'
            }}
          </p>
        </div>

        <!-- 当前是访客时，说明一下 -->
        <div v-if="authStore.state.isGuest" class="guest-tip">
          你现在是访客模式，记录只存在当前浏览器。登录或注册后可以保留到账号里。
        </div>

        <div class="dialog-body">
          <label class="field">
            <span class="label">邮箱</span>
            <input
              v-model="form.email"
              class="input"
              type="email"
              autocomplete="email"
              placeholder="you@example.com"
              @keydown.enter="submit"
            />
          </label>

          <label v-if="mode === 'register'" class="field">
            <span class="label">昵称（选填）</span>
            <input
              v-model="form.displayName"
              class="input"
              maxlength="20"
              placeholder="怎么称呼你"
              @keydown.enter="submit"
            />
          </label>

          <label class="field">
            <span class="label">密码</span>
            <input
              v-model="form.password"
              class="input"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              placeholder="至少 6 位"
              @keydown.enter="submit"
            />
          </label>

          <label v-if="mode === 'register'" class="field">
            <span class="label">再输一次密码</span>
            <input
              v-model="form.confirm"
              class="input"
              type="password"
              autocomplete="new-password"
              placeholder="确认密码"
              @keydown.enter="submit"
            />
          </label>

          <!-- 前端校验提示：只在用户开始输入后才显示，别一打开就报错 -->
          <p v-if="validation && (form.email || form.password)" class="hint">
            {{ validation }}
          </p>

          <p v-if="error" class="error">{{ error }}</p>
        </div>

        <div class="dialog-foot">
          <button type="button" class="primary" :disabled="!canSubmit" @click="submit">
            {{ submitting ? '处理中…' : mode === 'login' ? '登录' : '注册并登录' }}
          </button>

          <div class="switch-row">
            <template v-if="mode === 'login'">
              还没有账号？
              <button type="button" class="link" @click="mode = 'register'">注册一个</button>
            </template>
            <template v-else>
              已有账号？
              <button type="button" class="link" @click="mode = 'login'">去登录</button>
            </template>
          </div>

          <div v-if="authStore.state.isGuest" class="guest-row">
            <button type="button" class="link-muted" :disabled="submitting" @click="backToGuest">
              继续用访客模式
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: rgba(16, 24, 40, 0.28);
  display: grid;
  place-items: center;
  padding: var(--s-5);
}

.dialog {
  position: relative;
  width: min(400px, 100%);
  background: var(--c-bg);
  border-radius: var(--r-2xl);
  box-shadow: var(--sh-pop);
  padding: var(--s-7) var(--s-6) var(--s-6);
}

.dialog-close {
  position: absolute;
  top: var(--s-4);
  right: var(--s-4);
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  display: grid;
  place-items: center;
  font-size: 13px;
}

.dialog-close:hover {
  background: var(--c-bg-hover);
  color: var(--c-text);
}

/* ---------- 头部 ---------- */
.dialog-head {
  text-align: center;
  margin-bottom: var(--s-5);
}

.brand {
  width: 40px;
  height: 40px;
  margin: 0 auto var(--s-3);
  border-radius: var(--r-lg);
  background: linear-gradient(140deg, #4a5058, var(--c-text));
  color: #fff;
  display: grid;
  place-items: center;
  font-size: var(--f-sm);
  font-weight: 700;
}

.dialog-head h2 {
  font-size: var(--f-xl);
  font-weight: 650;
  color: var(--c-text);
}

.sub {
  margin-top: var(--s-1);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

/* ---------- 访客提示 ---------- */
.guest-tip {
  margin-bottom: var(--s-4);
  padding: 9px 12px;
  border-radius: var(--r-md);
  background: var(--c-brand-soft);
  color: var(--c-brand-deep);
  font-size: var(--f-sm);
  line-height: var(--lh-normal);
}

/* ---------- 表单 ---------- */
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label {
  font-size: var(--f-sm);
  font-weight: 600;
  color: var(--c-text-2);
}

.input {
  width: 100%;
  padding: 10px 12px;
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

.hint {
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 8px 12px;
  line-height: var(--lh-normal);
}

/* ---------- 底部 ---------- */
.dialog-foot {
  margin-top: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.primary {
  width: 100%;
  padding: 11px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-base);
  font-weight: 600;
  transition: background var(--t-fast) var(--ease-soft);
}

.primary:hover:not(:disabled) {
  background: var(--c-brand-deep);
}

.primary:disabled {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
  cursor: default;
}

.switch-row {
  text-align: center;
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.link {
  color: var(--c-brand-deep);
  font-size: var(--f-sm);
  font-weight: 600;
  margin-left: 2px;
}

.link:hover {
  text-decoration: underline;
}

.guest-row {
  text-align: center;
  padding-top: var(--s-1);
  border-top: 1px solid var(--c-line);
}

.link-muted {
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.link-muted:hover:not(:disabled) {
  color: var(--c-text-2);
  text-decoration: underline;
}

/* ---------- 过渡 ---------- */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.modal-enter-active .dialog,
.modal-leave-active .dialog {
  transition: transform var(--t-normal) var(--ease-soft);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .dialog,
.modal-leave-to .dialog {
  transform: scale(0.96) translateY(8px);
}
</style>
