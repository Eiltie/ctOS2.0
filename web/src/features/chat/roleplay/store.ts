/**
 * 角色扮演的状态。
 *
 * 和闲聊的关系（这点必须清楚，否则很容易写乱）：
 *   角色扮演**复用闲聊的会话和消息表**，只是多一个 role_id。
 *   所以发消息仍然调 POST /chat，带 role_id 就走角色分支。
 *
 *   本文件只管「角色」这一层：列表、当前角色、记忆、选角色。
 *   「消息」那一层在 features/chat/store.ts，两边共用一个消息列表。
 *
 * 和 chatStore 的协作：
 *   选角色 → startRole() 建会话 → 把会话 id 告诉 chatStore
 *   → chatStore 加载消息 → 发消息时带上 roleId
 */
import { computed, reactive } from 'vue'
import type { RoleCard, RoleProfile } from '@/shared/types/api'
import {
  clearMemory,
  createRole,
  deleteRole,
  getMemory,
  getRoleProfile,
  getSessionRole,
  listRoles,
  searchRole,
  startRole,
} from './api'

interface State {
  /** 全部角色（预设 + 我的） */
  roles: RoleCard[]
  loading: boolean
  error: string

  /** 当前正在聊的角色（null = 不是角色会话） */
  activeRole: RoleCard | null

  /** 正在打开某个角色档案 */
  profileOpen: boolean
  profile: RoleProfile | null
  profileLoading: boolean

  /** 记忆查看面板 */
  memoryOpen: boolean
  memoryText: string
  memoryLoading: boolean

  /** AI 帮我查：生成中的草稿 */
  drafting: boolean
  draftError: string
  /** 生成的草稿，用于填进表单 */
  draft: RoleProfile | null
  draftNote: string
}

const state = reactive<State>({
  roles: [],
  loading: false,
  error: '',

  activeRole: null,

  profileOpen: false,
  profile: null,
  profileLoading: false,

  memoryOpen: false,
  memoryText: '',
  memoryLoading: false,

  drafting: false,
  draftError: '',
  draft: null,
  draftNote: '',
})

/** 预设角色（后端写死的那几个） */
const presetRoles = computed(() => state.roles.filter((r) => r.source !== 'custom' && r.source !== 'ai_search'))

/** 我自己创建的角色 */
const customRoles = computed(() =>
  state.roles.filter((r) => r.source === 'custom' || r.source === 'ai_search'),
)

// ---------------------------------------------------------------- 列表

async function loadRoles() {
  state.loading = true
  state.error = ''
  try {
    state.roles = await listRoles()
  } catch (error) {
    state.error = error instanceof Error ? error.message : '角色列表加载失败'
  } finally {
    state.loading = false
  }
}

// ---------------------------------------------------------------- 开始对话

/**
 * 开始和某个角色聊天。
 *
 * 返回会话 id，由调用方交给 chatStore 去加载消息。
 * 后端会新建会话并写入开场白，所以这里不需要额外准备什么。
 */
async function beginWith(role: RoleCard): Promise<number> {
  const result = await startRole(role.id)
  state.activeRole = role
  return result.session_id
}

/**
 * 打开一个已有会话时，判断它是不是角色会话。
 *
 * 普通闲聊返回 role: null，不是错误 —— 前端照常当普通对话打开。
 */
async function attachToSession(sessionId: number, roleId: string): Promise<void> {
  try {
    const info = await getSessionRole(sessionId)
    state.activeRole = info.role ?? null
  } catch {
    // 查不到就当作普通会话，不打断用户
    state.activeRole = null
  }
  void roleId
}

/** 退出角色会话，回到普通闲聊 */
function leaveRole() {
  state.activeRole = null
  state.profileOpen = false
  state.memoryOpen = false
}

// ---------------------------------------------------------------- 档案

async function openProfile(roleId: string) {
  state.profileOpen = true
  state.profile = null
  state.profileLoading = true
  try {
    state.profile = await getRoleProfile(roleId)
  } catch {
    state.profileOpen = false
  } finally {
    state.profileLoading = false
  }
}

function closeProfile() {
  state.profileOpen = false
  state.profile = null
}

// ---------------------------------------------------------------- 记忆

async function openMemory(roleId: string) {
  state.memoryOpen = true
  state.memoryText = ''
  state.memoryLoading = true
  try {
    state.memoryText = await getMemory(roleId)
  } catch {
    state.memoryText = ''
  } finally {
    state.memoryLoading = false
  }
}

function closeMemory() {
  state.memoryOpen = false
  state.memoryText = ''
}

async function wipeMemory(roleId: string) {
  await clearMemory(roleId)
  state.memoryText = ''
}

// ---------------------------------------------------------------- AI 帮我查

/**
 * 让 AI 联网搜资料，生成一份角色草稿。
 *
 * 注意：这一步要调模型 + 联网，通常十几秒，界面上必须有明确的等待状态。
 * 生成结果只填表单，**不自动保存** —— 用户确认后再调 createRole。
 */
async function draftRole(query: string) {
  state.drafting = true
  state.draftError = ''
  state.draft = null
  state.draftNote = ''

  try {
    const result = await searchRole(query)
    state.draft = result.role
    state.draftNote = result.note
  } catch (error) {
    state.draftError = error instanceof Error ? error.message : '生成失败，换个说法再试'
  } finally {
    state.drafting = false
  }
}

function clearDraft() {
  state.draft = null
  state.draftNote = ''
  state.draftError = ''
}

// ---------------------------------------------------------------- 增删

async function saveRole(input: Parameters<typeof createRole>[0]): Promise<RoleCard> {
  const role = await createRole(input)
  await loadRoles()
  return role
}

async function removeRole(roleId: string) {
  await deleteRole(roleId)
  state.roles = state.roles.filter((r) => r.id !== roleId)
  if (state.activeRole?.id === roleId) state.activeRole = null
}

// ---------------------------------------------------------------- 对外

export const roleplayStore = {
  state,
  presetRoles,
  customRoles,

  loadRoles,
  beginWith,
  attachToSession,
  leaveRole,

  openProfile,
  closeProfile,

  openMemory,
  closeMemory,
  wipeMemory,

  draftRole,
  clearDraft,

  saveRole,
  removeRole,
}
