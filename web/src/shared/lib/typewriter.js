/**
 * 流式文字的合并 —— 决定「最终该显示什么」。
 *
 * 为什么需要它：
 *   后端的流里，同一段文字可能以两种形式到达：
 *     TOKEN 若干个（模型逐字吐的，或者固定话术被切成两字一片）
 *     DONE  一个（这一段的完整定稿）
 *
 *   天真的做法是「收到 TOKEN 就追加，收到 DONE 就覆盖」，但它有个坑：
 *   打字机是匀速往外放的，DONE 到达时队列里往往还压着一大段没显示的字。
 *   这时候如果用「已显示字数」去算差额，就会把同一段话推两遍，
 *   页面上表现为文字重复——上一版就出过这个 bug。
 *
 * 这里的规则很简单，只有一条：
 *   同一段文字只有一个来源。有 DONE 就以 DONE 为准（它是定稿），
 *   没有 DONE 就用 TOKEN 拼起来的。
 *
 * 为什么这个文件是纯 JS 而不是 TS：
 *   它要能被 node 直接加载来跑测试（见 tests/test_typer_frontend.py），
 *   不经过任何编译。它的逻辑也确实不需要类型标注。
 *   配套的类型定义在 typewriter.d.ts 里。
 */

/**
 * 把一段的 tokens 和可能的 done 合成最终文字。
 *
 * 三种情况：
 *   1. 有 done            → 直接用 done（定稿就是权威，哪怕和 tokens 对不上）
 *   2. 没有 done，有 token → 用 tokens 拼起来（还在输出中）
 *   3. 都没有             → 空字符串
 *
 * @param {readonly string[]} tokens 按顺序收到的 TOKEN 片段
 * @param {string | null | undefined} done 这段的定稿（可能还没有）
 * @returns {string}
 */
export function mergeStreamText(tokens, done) {
  if (typeof done === 'string' && done.length > 0) {
    return done
  }
  return tokens.join('')
}

/**
 * 流式状态的累加器。
 *
 * 解析事件时调用它，它会告诉你「现在该显示什么」。
 * 为什么不直接拼接字符串：需要区分「还在流式输出」和「已经定稿」，
 * 前者可以带打字动画，后者应该立刻显示完整。
 */
export class StreamText {
  constructor() {
    /** @type {string[]} */
    this.tokens = []
    /** @type {string | null} */
    this.done = null
  }

  /**
   * 追加一段 TOKEN
   * @param {string} text
   * @returns {this}
   */
  push(text) {
    if (text) this.tokens.push(text)
    return this
  }

  /**
   * 收到 DONE，记下定稿
   * @param {string} text
   * @returns {this}
   */
  finish(text) {
    this.done = text
    return this
  }

  /** 当前应该显示的文字 */
  get text() {
    return mergeStreamText(this.tokens, this.done)
  }

  /** 这一段定稿了没有 */
  get isFinished() {
    return this.done !== null
  }

  /** 清空，用于重开一段 */
  reset() {
    this.tokens = []
    this.done = null
  }
}
