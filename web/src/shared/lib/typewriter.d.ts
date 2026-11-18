/**
 * typewriter.js 的类型声明。
 *
 * 实现是纯 JS（为了能被 node 直接加载测试），
 * 这里补上类型，让 TypeScript 那边用起来有完整的补全和检查。
 */

export declare function mergeStreamText(
  tokens: readonly string[],
  done?: string | null,
): string

export declare class StreamText {
  push(text: string): this
  finish(text: string): this
  readonly text: string
  readonly isFinished: boolean
  reset(): void
}
