#!/usr/bin/env node
/**
 * 接口契约校验：确认前端认的字段，和后端 /contract 声明的字段一致。
 *
 * 解决什么问题：
 *   后端把 "turn_count" 改成 "turnCount"，Python 和前端都不会报错，
 *   要等用户在浏览器里点开出行列表，才看到一片空白。
 *   这个脚本在提交前和 CI 里跑一次，对不上就红，问题当场暴露。
 *
 * 怎么跑：
 *   npm run check:api                                 # 连 127.0.0.1:8080
 *   CTOS_BACKEND=https://ctos2.cn npm run check:api   # 校验线上
 *
 * 后端没启动时：
 *   退回直接读 api/contract.py 的声明，能打印接口清单和版本，
 *   但没法确认「真实接口是否真的这么返回」。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = resolve(HERE, '..', '..')
const BACKEND = process.env.CTOS_BACKEND || 'http://127.0.0.1:8080'

// ============================================================================
// 前端实际依赖的东西
// 改了 web/src/shared/types/api.ts，就要同步改这里。
// ============================================================================

/**
 * 前端会读取的接口。value 是「前端会用到的字段」。
 *
 * 和后端契约 API[path].response / response_item 对照：
 *   前端用到的字段，后端必须声明 —— 否则说明后端把字段改名/删掉了。
 */
const FRONTEND_API = {
  // ---- 认证 ----
  'POST /auth/login': { response: ['token', 'user'] },
  'POST /auth/register': { response: ['token', 'user'] },
  'POST /auth/trial': { response: ['token', 'user', 'is_trial'] },
  'GET /auth/me': { response: ['id', 'email', 'display_name'] },

  // ---- 会话 ----
  'GET /sessions': {
    response_item: ['id', 'title', 'created_at', 'updated_at', 'role_id'],
  },
  'GET /sessions/{id}/messages': { response_item: ['role', 'content', 'images'] },
  'DELETE /sessions/{id}': { response: ['deleted'] },
  'POST /sessions/delete-batch': { request: ['ids'], response: ['deleted'] },

  // ---- 附件 ----
  'POST /chat/attachment': { response: ['image_id', 'mime', 'bytes', 'url'] },

  // ---- 角色扮演 ----
  'GET /roleplay/roles': {
    response: ['roles'],
    response_item: ['id', 'name', 'group', 'emoji', 'tagline', 'opening'],
  },
  'GET /roleplay/roles/{role_id}': { response: ['role'] },
  'POST /roleplay/roles': { response: ['role'] },
  'POST /roleplay/roles/search': { response: ['role', 'note'] },
  'POST /roleplay/start': { response: ['session_id', 'opening', 'memory', 'role'] },
  'GET /roleplay/session/{session_id}': { response: ['session_id', 'role', 'memory'] },
  'GET /roleplay/memory/{role_id}': { response: ['role_id', 'memory'] },

  // ---- 智能出行 ----
  'GET /trip/list': {
    response_item: ['id', 'title', 'created_at', 'updated_at', 'turn_count', 'last_kind'],
  },
  'GET /trip/{trip_id}': { response: ['id', 'title', 'created_at', 'updated_at', 'turns'] },
  'DELETE /trip/{trip_id}': { response: ['deleted'] },
  'POST /trip/delete-batch': { response: ['deleted'] },

  // ---- 其他 ----
  'GET /notice': { response: ['notice'] },
  'GET /presence/online': { response: ['online', 'window_minutes'] },
  'GET /health': { response: ['ok', 'database', 'user'] },
}

/** 前端处理的 SSE 事件类型 */
const FRONTEND_SSE_KINDS = [
  'SAY',
  'START',
  'STEP',
  'TOKEN',
  'DONE',
  'CHAT',
  'SAVED',
  'ERROR',
  'ASK',
  'ASK_PLACE',
  'ASK_SPOTS',
  // 生图：出行侧主动提议后画出来的图，events.ts 的 IMAGE 分支处理
  'IMAGE',
]

/** 前端认识的段落 key（出行里 TOKEN/DONE 的 key） */
const FRONTEND_SECTION_KEYS = {
  ROUTE: ['route_need', 'route_compare', 'route_decision', 'route_tips'],
  TRAVEL: ['weather', 'spots', 'itinerary', 'advice'],
}

/** 前端认识的轮次类型 */
const FRONTEND_TURN_KINDS = ['CHAT', 'ROUTE', 'TRAVEL']

// ============================================================================
// 取后端契约
// ============================================================================

async function loadBackendContract() {
  try {
    const response = await fetch(`${BACKEND}/contract`, { signal: AbortSignal.timeout(5000) })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return { source: `${BACKEND}/contract`, data: await response.json(), offline: false }
  } catch (error) {
    // 连不上就退回读源码里的版本号，至少能确认两边对着同一版
    const path = resolve(PROJECT_ROOT, 'api', 'contract.py')
    let version = null
    try {
      const source = readFileSync(path, 'utf-8')
      version = source.match(/^CONTRACT_VERSION\s*=\s*"([^"]+)"/m)?.[1] ?? null
    } catch {
      throw new Error(`连不上后端（${BACKEND}），也读不到 api/contract.py：${error.message}`)
    }

    console.log(`⚠️  连不上后端（${BACKEND}）`)
    console.log('   只能读取 api/contract.py 里的版本号，无法确认真实接口\n')

    return {
      source: 'api/contract.py（离线）',
      data: { version },
      offline: true,
    }
  }
}

// ============================================================================
// 比对
// ============================================================================

const problems = []

function compareList(label, frontendList, backendList) {
  if (!Array.isArray(backendList)) {
    problems.push(`${label}：后端契约里没有这一项`)
    return
  }
  const missing = frontendList.filter((item) => !backendList.includes(item))
  if (missing.length) {
    problems.push(`${label}：后端没有 → ${missing.join(', ')}（多半是改名或删掉了）`)
  }
}

function checkApi(backendApi) {
  if (!backendApi) return

  for (const [path, needs] of Object.entries(FRONTEND_API)) {
    const declared = backendApi[path]
    if (!declared) {
      problems.push(`${path}：后端契约里没有这个接口`)
      continue
    }

    for (const key of ['response', 'response_item']) {
      if (needs[key]) {
        compareList(`${path} ${key}`, needs[key], declared[key])
      }
    }
  }
}

/**
 * 校验 SSE 事件：两个方向都要查。
 *
 *   前端处理了后端没声明的 → 打错字，或者后端删了
 *   后端声明了前端没处理的 → 后端新加了事件，前端会静默丢掉（用户看不到内容）
 *
 * 后者往往不报错，是最隐蔽的一类：用户以为没反应，其实是前端不认识那条事件。
 */
function checkSseKinds(backendKinds) {
  if (!backendKinds || typeof backendKinds !== 'object') {
    problems.push('后端契约里没有 sse_kinds')
    return
  }

  const backendList = Object.keys(backendKinds)

  compareList('sse_kinds（前端用的）', FRONTEND_SSE_KINDS, backendList)

  const unhandled = backendList.filter((kind) => !FRONTEND_SSE_KINDS.includes(kind))
  if (unhandled.length) {
    problems.push(
      `sse_kinds（后端新增的）：${unhandled.join(', ')} —— 前端还没处理，这类事件会被静默丢弃`,
    )
  }
}

// ============================================================================
// 主流程
// ============================================================================

async function main() {
  const { data, source, offline } = await loadBackendContract()

  console.log(`契约来源：${source}`)
  console.log(`契约版本：${data.version ?? '未知'}\n`)

  if (offline) {
    // 默认失败：否则 CI 里后端没起来时，这个检查会「假绿」，等于没查。
    // 确实只想看契约版本时，显式设置 CTOS_ALLOW_OFFLINE=1。
    if (process.env.CTOS_ALLOW_OFFLINE === '1') {
      console.log('（已允许离线模式，跳过比对）')
      process.exit(0)
    }
    console.error('❌ 校验失败：连不上后端，无法比对字段。')
    console.error('   先启动后端（python -X utf8 -m api.main），')
    console.error('   或设置 CTOS_BACKEND 指向正确的地址。')
    console.error('   只想看契约版本、不做比对：CTOS_ALLOW_OFFLINE=1')
    process.exit(1)
  }

  // 字段
  checkApi(data.api)

  // SSE 事件（两个方向都查）
  checkSseKinds(data.sse_kinds)

  // 段落 key
  for (const [mode, keys] of Object.entries(FRONTEND_SECTION_KEYS)) {
    compareList(`section_keys.${mode}`, keys, data.section_keys?.[mode])
  }

  // 轮次类型
  compareList('turn_kinds', FRONTEND_TURN_KINDS, Object.keys(data.turn_kinds ?? {}))

  console.log(
    `已比对：${Object.keys(FRONTEND_API).length} 个接口、` +
      `${FRONTEND_SSE_KINDS.length} 种事件、` +
      `${Object.keys(FRONTEND_SECTION_KEYS).length} 组段落\n`,
  )

  if (problems.length) {
    console.error('❌ 前后端接口对不上：\n')
    for (const problem of problems) console.error(`   - ${problem}`)
    console.error('\n处理办法：')
    console.error('   后端确实改了 → 改 web/src/shared/types/api.ts 和本脚本的 FRONTEND_*')
    console.error('   前端写错了   → 同上')
    console.error('   两边都改     → 同步改 api/contract.py 并更新 CONTRACT_VERSION\n')
    process.exit(1)
  }

  console.log('✅ 前后端接口一致')
}

main().catch((error) => {
  console.error('校验脚本出错：', error.message)
  process.exit(1)
})
