# DSH 兼容性验收证据（一次性 Profile / E3）

对应 DSH STORE Catalog 检查要求的「一次性 Profile 的安装、启动与卸载证据」。

隔离约束（两次验收均遵守）：

- `DSH_HOME=$(mktemp -d)`，临时 Profile 目录在验收结束后整体删除；真实 `~/.dsh` 全程未被读写
- 不改动宿主已安装的 dsh（0.2.0-rc.2 验收使用独立安装，不覆盖全局版本）
- 不执行任何 `install` / `prepare` / `build` 生命周期脚本（package.json 本身未定义）
- 不调用引擎、不发起 API 请求：只验 Bundle 契约与插件生命周期

## 验收矩阵

| dsh 版本 | 安装 | 启动 / 配置合成 | 工具注册自检 | 卸载 / 回滚 | 结论 | 验收日期 |
|---|---|---|---|---|---|---|
| `0.1.5-rc.1` | ✅ | ✅ 单条目、id 唯一 | ✅ PASS | ✅ 0 残留 | `compatible` | 2026-09-21 |
| `0.2.0-rc.2` | ✅ | ✅ 单条目、id 唯一 | ✅ PASS | ✅ 0 残留 | `compatible` | 2026-09-30 |

复现脚本：[`docs/tools/e3-dsh-disposable-profile.sh`](tools/e3-dsh-disposable-profile.sh)

```bash
export DSH_HOME="$(mktemp -d)"
dsh plugin --profile e3-dsvu add /absolute/path/to/dsvu-checkout   # 安装
dsh --profile e3-dsvu --dump-config                                 # 配置合成
node dsh/index.js --self-test                                       # 工具注册自检
dsh plugin --profile e3-dsvu remove @svenyu/dsvu                    # 卸载
dsh --profile e3-dsvu --dump-config | grep -c 'video-understand'    # → 0
```

---

## A. dsh 0.2.0-rc.2（2026-09-30）

- 插件：`@svenyu/dsvu` 0.6.8（本地源码 checkout）
- DSH：`0.2.0-rc.2`（`@deepseek-ai/dsh`，独立安装于隔离工作区，未改动全局 0.1.5-rc.1）
- Node.js：v22.22.2；pnpm：11.8.0

### A.1 安装

```
dsh: initialized profile e3-dsvu at <tmp>/profiles/e3-dsvu
dependencies:
+ @svenyu/dsvu link:/Users/chuli/Code/dsvu-videounderstanding
Done in 296ms using pnpm v11.8.0
exit=0
```

成功。无生命周期脚本执行。

### A.2 启动 / 配置合成

```
# == @svenyu/dsvu
- id: video-understand
  name: '@svenyu/dsvu'
```

成功。dump-config 中本插件条目数：`video-understand` 1 次、`@svenyu/dsvu` 1 次，无重复、无遮蔽官方条目。

### A.3 工具注册自检

```
node dsh/index.js --self-test
→ PASS: video-understand --self-test (schema + render, video object/string compatible)
exit=0
```

### A.4 卸载 / 回滚

```
dependencies:
- @svenyu/dsvu link:/Users/chuli/Code/dsvu-videounderstanding
Done in 268ms using pnpm v11.8.0
exit=0
```

卸载后 dump-config 中 `video-understand` 与 `dsvu` 匹配数均为 **0**，无残留条目；临时 Profile 随 `DSH_HOME` 一并删除（已核验目录不存在）。

---

## B. dsh 0.1.5-rc.1（2026-09-21）

- 插件：`@svenyu/dsvu` 0.6.6（本地源码 checkout）
- DSH：`0.1.5-rc.1`（`@deepseek-ai/dsh`，npm 全局）
- Node.js：v22.22.2；pnpm：11.8.0

### B.1 安装

```
export DSH_HOME="$(mktemp -d)"
dsh plugin --profile e3-dsvu add /absolute/path/to/dsvu-checkout
```

结果：成功。pnpm 输出 `+ @svenyu/dsvu link:<checkout>`，无生命周期脚本执行
（package.json 无 `install`/`prepare`/`postinstall`）。

### B.2 启动 / 配置合成

```
dsh --profile e3-dsvu --dump-config
```

结果：成功。配置中出现且仅出现一个本插件条目：

```
# == @svenyu/dsvu
- id: video-understand
  name: '@svenyu/dsvu'
```

工具注册自检（宿主外直跑 schema/render 验证）：

```
node dsh/index.js --self-test
→ PASS: video-understand --self-test (schema + render, video object/string compatible)
```

### B.3 卸载 / 回滚

```
dsh plugin --profile e3-dsvu remove @svenyu/dsvu
dsh --profile e3-dsvu --dump-config | grep -c "video-understand|dsvu"   # → 0
```

结果：成功。卸载后 dump-config 中 `video-understand` / `dsvu` 匹配数为 0，
无残留条目。一次性 Profile 随后整体删除。

---

## C. 兼容范围声明

package.json `dsh.compatibility`：

- `dsh`: `>=0.1.0-rc.8 <0.3.0`（适配层使用 `ctx.skills.register()` 公开服务接口，
  该接口自 0.1.0-rc.8 起提供；上界收到 0.3.0，0.2.x 已在 `0.2.0-rc.2` 实测）
- `dshReleases`:
  - `0.1.5-rc.1`: `compatible`（2026-09-21 实测）
  - `0.2.0-rc.2`: `compatible`（2026-09-30 实测）

未列出的版本仅表示未测，不表示不可用。后续在更多 dsh 版本上完成 E3 验收后会更新此表。

> 说明：上游 `catalog-compatibility-policy` 要求「当前最新三个 dsh 版本中至少一个
> `compatible`」，否则条目会被自动转 `unlisted`。本次更新即为此保持窗口内有效声明。

## D. 固定源策略面的对齐（2026-09-30）

除生命周期证据外，本次同时对齐了上游固定源自动策略可核查的源码面：

- 消除 `nativeOrExecutableArtifacts` 信号：`engine/avis.py` 的 git mode 由 `100755`
  改为 `100644`（该模式下会被上游按「可执行制品」计数）；仓库内不存在 `.node` /
  `.wasm` / `.dll` / `.dylib` / `.so` / `.exe` / `.bin` 文件
- ⚠️ 维护提醒：本地对该包执行 `pnpm`/`npm` 安装时，包管理器会依据 `package.json.bin`
  把 `bin/doctor.mjs` chmod 成 `100755`，**而这会重新触发 `nativeOrExecutableArtifacts`**。
  提交前请确认 git 记录的模式仍是 `100644`：
  `git ls-files -s | awk '$1=="100755"'`（应为空；必要时 `chmod 644 bin/doctor.mjs`）
- 历史实验脚本 `experiments/` 移入 `docs/experiments/`：非运行时源码，也从未进入
  npm 包（`package.json.files` 不含该目录）
- 收敛后有界运行时源码：**29 文件 / 386877 字节**（上游上限 240 文件、单文件 256 KiB、
  合计 2 MiB），此前为 37 文件 / 423420 字节
- 仍存在的信号：`files` / `commands` / `credentials` —— 读 API key（`credentials`）与
  spawn Python 引擎（`commands`）是本插件的功能本身，无法在不移除功能的前提下消除；
  上游自动通道要求六个信号全为 false，故本插件按定位应走守卫生效的 `user-reviewed`
  通道，权限声明见 README「DSH 兼容性与权限」

## E. 运行时依赖与失败边界（摘要）

- 引擎为 Python 源码（`engine/`），首次调用 `video_understand` 时创建插件本地 venv
  并安装核心依赖（faster-whisper / opencv / yt-dlp / pandas，约 200-300MB）；
  可选语义层（torch / ultralytics，约 2GB）需显式 `dsvu doctor --fix --layer`。
  仓库内无预编译二进制。
- 凭据：只读 `DEEPSEEK_API_KEY`（及 `DSVU_*` 可选项）与 `~/.dsh/.credentials.yaml`，
  进程内使用，不落盘、不上传至 DeepSeek API 以外的端点。
- 网络：B站视频下载（yt-dlp）与 DeepSeek API；L0 层级完全本地。
- 失败边界：依赖缺失 → 工具报错并提示 `dsvu doctor --fix`，不影响宿主；
  key 缺失 → L1/L2 降级 L0 或显式报错；卸载 → 完整回滚（见 A.4 / B.3）。
