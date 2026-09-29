// dsh-store-source-audit.mjs — 本地复现 DSH STORE 的「有界运行时源码」权限信号扫描
//
// 规则来源（逐字抄自上游仓库，非猜测）：
//   - AI-Scarlett/DSH-Store  src/automation-source-policy.mjs     → permissionSignals()
//   - AI-Scarlett/DSH-Store  scripts/automate-catalog.mjs         → SOURCE_FILE / NATIVE_FILE /
//                                                                   EXCLUDED_DIRECTORY /
//                                                                   EXCLUDED_METADATA_FILE /
//                                                                   analyzeFixedSource()
//
// 与上游的差异：上游是「按 commit 从 raw.githubusercontent.com 逐个拉文件」，
// 本脚本改为读本地 git 索引（git ls-files -s），因此需要工作区处于目标 commit 且无未提交改动。
// 判定逻辑保持逐字一致。
//
// 用法：node docs/tools/dsh-store-source-audit.mjs --repo . [--json]
//      通常不用直接跑，用 docs/tools/check-fixed-source.sh 一并做提交前自检

// 背景：本插件在 DSH STORE 被自动策略判定为 blocked（文件/命令/凭据三信号），
// 其中 nativeOrExecutableArtifacts 已清零。本脚本用于回归——任何改动后应保持
// 只剩 files / commands / credentials 三条（前两条或全部消失是进步，多出来即回归）。

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// ── 上游 scripts/automate-catalog.mjs 第 51-54 行，逐字一致 ──────────────────
const SOURCE_FILE = /\.(?:[cm]?[jt]sx?|json|ya?ml|sh|py|rb|go|rs)$/i
const NATIVE_FILE = /\.(?:node|wasm|dll|dylib|so|exe|bin)$/i
const EXCLUDED_DIRECTORY =
  /(?:^|\/)(?:node_modules|vendor|test|tests|docs?|examples?|fixtures?|benchmarks?|coverage|\.github)(?:\/|$)/i
const EXCLUDED_METADATA_FILE = /(?:^|\/)(?:brief\.json|catalog-entry(?:\.draft)?\.json)$/i
const MAX_RUNTIME_FILES = 240
const MAX_FILE_BYTES = 262144
const MAX_TOTAL_RUNTIME_BYTES = 2097152

// ── 上游 src/automation-source-policy.mjs 第 1-22、51-67 行，逐字一致 ────────
const moduleImport = (names) =>
  new RegExp(`(?:\\bfrom\\s*|\\bimport\\s*(?:\\(\\s*)?|\\brequire\\s*\\(\\s*)["'](?:node:)?(?:${names})["']`, 'i')
const FILE_MODULE = moduleImport('fs|fs/promises')
const NETWORK_MODULE = moduleImport('http|https|net|tls|dgram|axios|got|undici')
const COMMAND_MODULE = moduleImport('child_process')
const COMMAND_CALL = /(?:^|[^\w$.'"`])(?:exec|execFile|spawn|fork)\s*\(/im
const TEST_SOURCE_FILE = /^(?:test|spec)[-_.].*\.(?:[cm]?[jt]sx?|json|ya?ml|sh|py|rb|go|rs)$/i
const SUFFIXED_TEST_SOURCE_FILE = /^.+\.(?:test|spec)\.(?:[cm]?[jt]sx?)$/i

const isTestSourceFile = (relativePath) => {
  const name = String(relativePath ?? '').split('/').at(-1) ?? ''
  return TEST_SOURCE_FILE.test(name) || SUFFIXED_TEST_SOURCE_FILE.test(name)
}

// 拆开 permissionSignals 的每个子条件，便于逐条定位证据
const RULES = {
  files: [
    ['import fs|fs/promises', (s) => FILE_MODULE.test(s)],
    ['readFile(/writeFile(/appendFile(/rename(/unlink(/mkdir(/rmdir(/rm(', (s) =>
      /\b(?:readFile|writeFile|appendFile|rename|unlink|mkdir|rmdir|rm)\s*\(/i.test(s)],
    ['$DSH_HOME 或 .dsh/profiles', (s) => /\$DSH_HOME|\.dsh\/profiles/i.test(s)],
  ],
  network: [
    ['import http|https|net|tls|dgram|axios|got|undici', (s) => NETWORK_MODULE.test(s)],
    ['fetch(/WebSocket(/EventSource(', (s) => /\b(?:fetch|WebSocket|EventSource)\s*\(/i.test(s)],
    ['axios.|got(/undici.', (s) => /\b(?:axios|got|undici)\s*(?:\.|\()/i.test(s)],
  ],
  commands: [
    ['import child_process', (s) => COMMAND_MODULE.test(s)],
    ['exec(/execFile(/spawn(/fork(', (s) => COMMAND_CALL.test(s)],
    ['shell:true / Bun.spawn / new Deno.Command', (s) =>
      /shell\s*:\s*true|Bun\.spawn|new\s+Deno\.Command/i.test(s)],
  ],
  credentials: [
    ['process.env', (s) => /process\.env/i.test(s)],
    ['keychain|credentials|oauth 后接 . [ (', (s) => /\b(?:keychain|credentials?|oauth)\b\s*(?:\.|\[|\()/i.test(s)],
    ['api_key|apiKey|access_token|accessToken|client_secret|clientSecret|password', (s) =>
      /\b(?:api[_-]?key|apiKey|access[_-]?token|accessToken|client[_-]?secret|clientSecret|password)\b/i.test(s)],
  ],
  protectedDsh: [
    ['__ModuleLoader__ / loader|fiber 变更 / 官方组件 disabled / tool.call.toolview', (s) =>
      /(?:\b__ModuleLoader__\s*\.\s*(?:unload|remove)\s*\(|\b(?:ctx\s*\.\s*)?(?:loader|fiber|Loader|Fiber)\s*\.\s*(?:insert|remove|patch|enable|disable|write|mutate|replace)\s*\(|@deepseek-ai\/[^\n]{0,160}disabled\s*:\s*true|tool\.call\.toolview)/i.test(s)],
  ],
}

const argv = process.argv.slice(2)
const repoArg = argv.indexOf('--repo')
const repo = resolve(repoArg >= 0 ? argv[repoArg + 1] : '.')
const asJson = argv.includes('--json')

const indexLines = execFileSync('git', ['ls-files', '-s'], { cwd: repo, encoding: 'utf8' })
  .trim().split('\n')

const signals = {
  files: false, network: false, commands: false,
  credentials: false, protectedDsh: false, nativeOrExecutableArtifacts: false,
}
const hits = Object.fromEntries(Object.keys(signals).map((k) => [k, []]))
const runtimeFiles = []
let skippedExcluded = 0

for (const line of indexLines) {
  const m = /^(\d+) ([0-9a-f]+) (\d+)\t(.+)$/.exec(line)
  if (!m) continue
  const [, mode, , size, path] = m
  if (EXCLUDED_DIRECTORY.test(path) || EXCLUDED_METADATA_FILE.test(path)) { skippedExcluded += 1; continue }
  if (isTestSourceFile(path)) { skippedExcluded += 1; continue }

  // 上游：mode 100755 或 NATIVE_FILE 命中 → nativeOrExecutableArtifacts（对**所有** blob 生效）
  if (NATIVE_FILE.test(path) || mode === '100755') {
    signals.nativeOrExecutableArtifacts = true
    hits.nativeOrExecutableArtifacts.push(`${path} (mode ${mode})`)
  }
  if (!SOURCE_FILE.test(path)) continue

  const source = readFileSync(resolve(repo, path), 'utf8')
  runtimeFiles.push({ path, bytes: Buffer.byteLength(source) })
  for (const [signal, conditions] of Object.entries(RULES)) {
    for (const [label, test] of conditions) {
      let matched = false
      try { matched = test(source) } catch { matched = false }
      if (!matched) continue
      signals[signal] = true
      hits[signal].push(`${path} ← ${label}`)
    }
  }
}

const totalBytes = runtimeFiles.reduce((sum, f) => sum + f.bytes, 0)
const largest = runtimeFiles.reduce((max, f) => Math.max(max, f.bytes), 0)
const bounds = {
  files: `${runtimeFiles.length} / ${MAX_RUNTIME_FILES}`,
  largestFileBytes: `${largest} / ${MAX_FILE_BYTES}`,
  totalBytes: `${totalBytes} / ${MAX_TOTAL_RUNTIME_BYTES}`,
}
const withinBounds = runtimeFiles.length > 0
  && runtimeFiles.length <= MAX_RUNTIME_FILES
  && largest <= MAX_FILE_BYTES
  && totalBytes <= MAX_TOTAL_RUNTIME_BYTES

if (asJson) {
  console.log(JSON.stringify({ repo, signals, hits, bounds, withinBounds, runtimeFileCount: runtimeFiles.length }, null, 2))
} else {
  console.log(`repo: ${repo}`)
  console.log(`runtime source: ${runtimeFiles.length} files, ${totalBytes} bytes (largest ${largest})`)
  console.log(`bounds: ${JSON.stringify(bounds)} → ${withinBounds ? 'WITHIN' : 'EXCEEDS'}`)
  console.log(`excluded (dir/metadata/test): ${skippedExcluded}`)
  console.log('')
  for (const [signal, on] of Object.entries(signals)) {
    console.log(`${on ? '✗ BLOCK' : '✓ clear'}  ${signal}`)
    if (!on) continue
    for (const hit of hits[signal]) console.log(`           ${hit}`)
  }
  const blocking = Object.entries(signals).filter(([, on]) => on).map(([k]) => k)
  console.log('')
  console.log(`blocking signals (${blocking.length}): ${blocking.join(', ') || '(none)'}`)
  console.log(blocking.length === 0
    ? '→ 全部信号清零：满足自动 source-verified 通道的源码面要求'
    : '→ 存在阻塞信号：只能走 owner 人工策展（user-reviewed）通道')
}
