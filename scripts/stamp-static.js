#!/usr/bin/env node
/**
 * 给 HTML 里引用的本地静态资源加版本号
 *
 * 背景：
 *   站点走 Cloudflare，.js / .css 的响应头会被 CF 覆盖成
 *   max-age=14400（后端设的 no-cache 不起作用）。
 *   浏览器拿到旧文件后，新功能要等 4 小时才生效，
 *   手机端还停在旧版就是这个原因。
 *
 * 做法：
 *   给每个 /static/... 的引用后面加 ?v=<版本>。
 *   版本一变，CF 和浏览器都当成新资源，立刻拿最新的。
 *
 * 用法：
 *   node scripts/stamp-static.js              # 用当前时间做版本号
 *   node scripts/stamp-static.js 20261117b    # 指定版本号
 */

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const staticDir = path.join(root, 'static');

if (!fs.existsSync(staticDir)) {
  console.error('找不到 static 目录：' + staticDir);
  process.exit(1);
}

const version =
  process.argv[2] ||
  (() => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}`;
  })();

// 收集所有 html（跳过 vendor）
function walk(dir, out) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const st = fs.statSync(full);
    if (st.isDirectory()) {
      if (name === 'vendor') continue;
      walk(full, out);
    } else if (name.endsWith('.html')) {
      out.push(full);
    }
  }
  return out;
}

const files = walk(staticDir, []);
let changed = 0;

for (const file of files) {
  const text = fs.readFileSync(file, 'utf8');
  // 先剥掉旧版本号，避免 ?v=a?v=b 叠加
  const next = text.replace(
    /((?:src|href)=")(\/static\/[^"?]+)(\?v=[^"]*)?(")/g,
    (m, pre, url, oldVer, post) => `${pre}${url}?v=${version}${post}`
  );

  if (next !== text) {
    fs.writeFileSync(file, next, 'utf8');
    const n = (next.match(/\?v=/g) || []).length;
    console.log(`  ${path.relative(staticDir, file)}  (${n} 处)`);
    changed++;
  }
}

console.log('');
console.log(`版本号：${version}`);
console.log(`更新文件：${changed} 个`);
