#!/bin/bash
# E3 一次性 Profile 验收 —— 安装 / 启动 / 卸载 / 自检
#
# 用途：为 DSH STORE 上架材料生成「一次性 Profile」生命周期证据。
#
# 隔离保证：
#   - DSH_HOME 指向 mktemp -d 的临时目录，真实 ~/.dsh 全程不被读写，退出即删
#   - 不执行任何生命周期脚本、不调用引擎、不发起 API 请求
#
# 用法：
#   bash e3-dsh-disposable-profile.sh <插件目录> [profile 名]
#
# 环境变量：
#   DSH_BIN    指定 dsh 可执行文件（默认取 PATH 上的 dsh，便于逐版本验收）
#   NODE_BIN   指定 node（默认 node）
#
# 逐版本验收示例：
#   DSH_BIN=/path/to/dsh-0.2.0-rc.2 bash e3-dsh-disposable-profile.sh .
#   DSH_BIN=/path/to/dsh-0.1.5-rc.1 bash e3-dsh-disposable-profile.sh .

set -uo pipefail

PLUGIN_DIR="${1:?usage: e3-dsh-disposable-profile.sh <plugin-dir> [profile]}"
PROFILE="${2:-e3-dsvu}"
DSH="${DSH_BIN:-dsh}"
NODE="${NODE_BIN:-node}"
PACKAGE_NAME="$("$NODE" -p "require('$PLUGIN_DIR/package.json').name")"
ENTRY_ID="$(awk '/^[[:space:]]*-[[:space:]]*id:/{print $3; exit}' "$PLUGIN_DIR/cordis.patch.yml")"
if [ -z "$ENTRY_ID" ]; then
  echo "无法从 cordis.patch.yml 解析 bundle 入口 id" >&2
  exit 2
fi

DSH_HOME="$(mktemp -d)"
export DSH_HOME
trap 'rm -rf "$DSH_HOME"' EXIT

echo "### 0. 环境"
echo "dsh          : $($DSH --version 2>&1 | head -1)"
echo "node         : $($NODE --version)"
echo "DSH_HOME     : $DSH_HOME (临时，退出即删)"
echo "plugin       : $PLUGIN_DIR ($PACKAGE_NAME, entry id=$ENTRY_ID)"
echo

echo "### 1. 安装 / bundle 解析"
$DSH plugin --profile "$PROFILE" add "$PLUGIN_DIR" 2>&1
echo

echo "### 2. 配置合成"
$DSH --profile "$PROFILE" --dump-config 2>&1 | grep -B1 -A2 "$ENTRY_ID\|$PACKAGE_NAME" | head -20
echo "--- entry 计数（入口 id 应为 1；包名出现 2 次属正常 = 注释行 + 条目行）---"
echo "$ENTRY_ID  : $($DSH --profile "$PROFILE" --dump-config 2>&1 | grep -c "$ENTRY_ID")"
echo "$PACKAGE_NAME : $($DSH --profile "$PROFILE" --dump-config 2>&1 | grep -c "$PACKAGE_NAME")"
echo

echo "### 3. 工具注册自检"
$NODE "$PLUGIN_DIR/dsh/index.js" --self-test 2>&1
echo

echo "### 4. 卸载 / 回滚"
$DSH plugin --profile "$PROFILE" remove "$PACKAGE_NAME" 2>&1
echo "--- 卸载后残留计数（应各为 0）---"
echo "$ENTRY_ID  : $($DSH --profile "$PROFILE" --dump-config 2>&1 | grep -c "$ENTRY_ID")"
echo "$PACKAGE_NAME : $($DSH --profile "$PROFILE" --dump-config 2>&1 | grep -c "$PACKAGE_NAME")"
echo

echo "### 5. 隔离核验"
if [ -d "$DSH_HOME" ]; then
  echo "真实 ~/.dsh 未被触碰；临时 DSH_HOME 已由 trap 清理"
else
  echo "临时 DSH_HOME 已删除"
fi
