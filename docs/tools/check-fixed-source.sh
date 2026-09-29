#!/bin/bash
# check-fixed-source.sh — 提交前自检：确保改动没有让 DSH STORE 的固定源策略回归。
#
# 为什么需要它：DSH STORE 的自动策略会把「git mode 100755 的文件」算作
# nativeOrExecutableArtifacts 权限信号（scripts/automate-catalog.mjs）。
# 而本地用 pnpm/npm 安装本包时，包管理器会依据 package.json.bin 把
# bin/doctor.mjs 自动 chmod 成 100755 —— 于是"修好的信号会被自己装回来"。
# 这个坑在 2026-09-30 一天内触发过两次，所以用脚本兜住。
#
# 用法：
#   bash docs/tools/check-fixed-source.sh          # 提交前跑（需先 git add，脚本读索引）
#   bash docs/tools/check-fixed-source.sh --audit  # 追加运行完整权限信号审计（需 node）
#
# 退出码：0 = 通过；1 = 有回归

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

fail=0

echo "=== 1. 可执行位（索引中除 docs/ 外不应有 100755）==="
# docs/ 被上游 EXCLUDED_DIRECTORY 排除，不参与信号计算，因此允许脚本可执行
exe_modes="$(git ls-files -s | awk '$1=="100755"{print $4}' | grep -v '^docs/' || true)"
if [ -n "$exe_modes" ]; then
  echo "❌ 发现会被计入 nativeOrExecutableArtifacts 的可执行位文件："
  echo "$exe_modes" | sed 's/^/   /'
  echo "   修复：git update-index --chmod=-x <文件> && chmod 644 <文件>"
  fail=1
else
  echo "✅ 通过"
fi

echo
echo "=== 2. 原生制品（NATIVE_FILE 正则中的扩展名）==="
native="$(git ls-files | grep -Ei '\.(node|wasm|dll|dylib|so|exe|bin)$' || true)"
if [ -n "$native" ]; then
  echo "❌ 仓库内出现原生制品："
  echo "$native" | sed 's/^/   /'
  fail=1
else
  echo "✅ 通过（无 .node/.wasm/.dll/.dylib/.so/.exe/.bin）"
fi

echo
echo "=== 3. 模型权重（0.7.0 起不随仓库/包分发）==="
weights="$(git ls-files | grep -Ei '\.(pt|pth|onnx|safetensors|gguf|h5)$' || true)"
if [ -n "$weights" ]; then
  echo "❌ 仓库内出现模型权重（0.7.0 起已移除权重分发；如需模型请走本地自备，不要入库）："
  echo "$weights" | sed 's/^/   /'
  fail=1
else
  echo "✅ 通过"
fi

if [ "${1:-}" = "--audit" ]; then
  echo
  echo "=== 4. 打包卫生：__pycache__ / .pyc 不得存在（会被打进 npm 包）==="
  # 成因：package.json 的 files 白名单会盖过 .npmignore，所以 engine/ 下的
  # __pycache__ 照样入包（2026-09-30 实测：5 个 .pyc 让 tarball 从 188KB 涨到 267KB）。
  # 现已把 files 改成 engine/**/*.py + engine/**/*.txt，从根上挡住；这里再兜一道。
  pycache="$(find . -name '__pycache__' -not -path './.git/*' -type d 2>/dev/null)"
  if [ -n "$pycache" ]; then
    echo "❌ 工作区存在 __pycache__（发布前先删，或确认 files 白名单不含它）："
    echo "$pycache" | sed 's/^/   /'
    fail=1
  else
    echo "✅ 通过"
  fi

  echo
  echo "=== 5. 完整权限信号审计 ==="
  if command -v node >/dev/null 2>&1; then
    node docs/tools/dsh-store-source-audit.mjs --repo . || fail=1
  else
    echo "跳过：未找到 node"
  fi
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "✅ 固定源自检通过，可以提交。"
else
  echo "❌ 固定源自检未通过，先修上方问题再提交。"
fi
exit "$fail"
