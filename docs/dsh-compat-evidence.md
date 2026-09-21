# DSH 兼容性验收证据（一次性 Profile / E3）

对应 DSH STORE Catalog 检查要求的「一次性 Profile 的安装、启动与卸载证据」。
所有操作均在 `DSH_HOME=$(mktemp -d)` 的隔离环境执行，真实 `~/.dsh` 未被触碰。

- 日期：2026-09-21
- 插件：`@svenyu/dsvu` 0.6.6（本地源码 checkout）
- DSH：0.1.5-rc.1（`@deepseek-ai/dsh`，npm 全局）
- Node.js：v22.22.2
- pnpm（dsh plugin 底层）：11.8.0

## 1. 安装

```
export DSH_HOME="$(mktemp -d)"
dsh plugin --profile e3-dsvu add /absolute/path/to/dsvu-checkout
```

结果：成功。pnpm 输出 `+ @svenyu/dsvu link:<checkout>`，无生命周期脚本执行
（package.json 无 `install`/`prepare`/`postinstall`）。

## 2. 启动 / 配置合成

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

## 3. 卸载 / 回滚

```
dsh plugin --profile e3-dsvu remove @svenyu/dsvu
dsh --profile e3-dsvu --dump-config | grep -c "video-understand|dsvu"   # → 0
```

结果：成功。卸载后 dump-config 中 `video-understand` / `dsvu` 匹配数为 0，
无残留条目。一次性 Profile 随后整体删除。

## 4. 兼容范围声明

package.json `dsh.compatibility`：

- `dsh`: `>=0.1.0-rc.8 <0.2.0`（适配层使用 `ctx.skills.register()` 公开服务接口，
  该接口自 0.1.0-rc.8 起提供）
- `dshReleases`: `0.1.5-rc.1: compatible`（即本验收实测版本）

未列出的版本仅表示未测，不表示不可用。后续在更多 dsh 版本上完成 E3 验收后会更新此表。

## 5. 运行时依赖与失败边界（摘要）

- 引擎为 Python 源码（`engine/`），首次调用 `video_understand` 时创建插件本地 venv
  并安装核心依赖（faster-whisper / opencv / yt-dlp，约 200-300MB）；无预编译二进制。
- 凭据：只读 `DEEPSEEK_API_KEY`（及 `DSVU_*` 可选项）与 `~/.dsh/.credentials.yaml`，
  进程内使用，不落盘、不上传至 DeepSeek API 以外的端点。
- 失败边界：依赖缺失 → 工具报错并提示 `dsvu doctor --fix`，不影响宿主；
  key 缺失 → L1/L2 降级 L0 或显式报错；卸载 → 完整回滚（见第 3 节）。
