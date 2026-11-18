// 一个只读本地 JSON 的假后端，用来验证 check-api-contract 能否抓到字段错误。
// 用法：FAKE_FILE=<json路径> node fake_backend.mjs
import http from 'node:http'
import { readFileSync } from 'node:fs'

const file = process.env.FAKE_FILE
if (!file) {
  console.error('需要设置 FAKE_FILE 环境变量')
  process.exit(1)
}

const data = JSON.parse(readFileSync(file, 'utf-8'))

http
  .createServer((_req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    res.end(JSON.stringify(data))
  })
  .listen(8099, '127.0.0.1', () => console.log('fake backend listening on 8099'))
