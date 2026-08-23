# Changelog

## 0.6.5 (2026-08-23)
- fix(deps): **一次安装依赖补齐**——`requirements.txt` 补 `pandas>=2.0`（avis encode 场景/时间线 CSV 硬依赖，此前缺失会导致"装完首次运行即崩"）；`CORE_MODS` 检测列表从 3 项扩到 6 项（faster_whisper/cv2/yt_dlp/**pandas/xxhash/PIL**），避免误判"依赖齐全"
- 现在 `npm install @svenyu/dsvu` → 首次调用自动懒安装全部核心依赖（含 pandas），无额外手动步骤

## 0.6.4 (2026-08-23)
- fix(pricing): **周末取消峰谷定价**（DeepSeek 官方 2026-08-23 起）——周六/周日全天执行空闲价；`is_peak()` 周末返回 False，`peak_hint()` 周末提示"全天低价"，`DSVU_WAIT_OFFPEAK` 周末自动不等待且不打印多余提示（`_maybe_wait_offpeak` 仅实际等待过才输出）
- docs: README 峰谷说明同步（工作日峰谷 / 周末全天谷价）

## 0.6.3 (2026-08-22)
- **决策：模型方案收敛为全程 DSV**（纯 mimo、mimo+qwen 不再作为方案/默认/基准）
  - 依据：3 视频 × 10 题实测，三种方式成本同一量级（0.07-0.09 元），全程 DSV 精度最高（4.77 vs 3.83，+0.9 分）、速度最快（209s vs 1310s，快 6.3 倍）
  - MiMo 组合保留为回退（exp 模型不可用时的保险丝），代码层环境变量可切，不参与默认与基准
- docs: README/SKILL 默认推荐改为 DeepSeek 全程，新增"模型方案对比"小节；修正过时的"优先 XIAOMI_API_KEY / 迁移至 MiMo"表述

## 0.6.2 (2026-08-22)
- feat: **信息层一次注入（前缀缓存）**——回答轮把信息层作为固定 system 前缀（跨轮/跨次一致），动态部分（visual_note/图片）只放 user 消息 → 命中 DeepSeek prompt 缓存
  - 实测：同视频换问题，信息层前缀缓存命中率 **96.6%**（3456/3579 token），输入成本降至约 1/5（0.0054 → ~0.001 元）
- feat: **结果缓存**——同一视频 + 同一问题集 + 同一模型二次调用直接返回（`--no-cache` 关闭）；实测秒回 0.15s、成本 0
- feat: **真实 usage 入库**——result JSON 新增 `llm_usage`（prompt/completion/cache_hit/cache_miss/calls，含回答轮图片 token）与 `visual_tokens`（in/out），不再靠成本反推
- perf: 视觉 token 真实记录（run_visual 返回 pin/pout 累计）

## 0.6.1 (2026-08-22)
- feat: **精细成本核算**（`engine/pricing.py`）——按官方价目 + 峰谷时段
  - DeepSeek V4-Flash-Vision-Exp：峰时（北京 9-12/14-18）输入命中 0.10/未命中 3.0/输出 9.0，谷时 0.05/1.5/4.5（元/百万 token）
  - 图片计费纳入：官方确认每图最高 384 token，按输入价计入 prompt_tokens
  - MiMo v2.5 官方价 0.02/1.0/2.0（无峰谷）
  - `understand_video.py` / `stages.py` 旧 qwen3-vl-flash 近似价（0.2/0.7）替换为按模型取价
- feat: **峰时提醒 + 自动错峰**——运行时打印当前时段价格提示；`DSVU_WAIT_OFFPEAK=1` 时 DeepSeek 峰时自动等待谷时再跑
- perf: 重跑对比实验（谷时）：dsvu 0.089 元（原生 E 0.284 的 1/3.2），比 MIMO 快 6.3 倍

## 0.6.0 (2026-08-22)
- **fork 自 dsh-video-understand 0.5.2，更名 dsvu（DeepSeek-Powered Video Understanding）**，包名 `dsvu`、bin `dsvu`、缓存 `~/.cache/dsvu`，独立演进
- feat: **DeepSeek 视觉模型接入**——`DEEPSEEK_API_KEY` 配对时视觉/主模型改用 `deepseek-v4-flash-vision-exp`（2026-08-21 上线，单图≤384 token、与 V4-Flash 同价、OpenAI 兼容）；`visual_level.py` 与 `understand_video.py` 均支持（`VISION_MODEL` / `VLM_MODEL` 可覆盖）
- feat: **同源即看即答**（`understand_video.py`）——回答轮把抽帧 base64 与 ASR 信息层同一条 user 消息直送视觉模型，消除"VLM 描述→文本→主 LLM"两段式损耗；`DSVU_DIRECT_VISION=0` 关闭退回旧链路；帧上限 12、每轮消费后清空
- feat: **L2 grid 密集拼图**（`visual_level.py --grid NxN|auto`）——一窗密集帧拼成一张大图单次 VLM（≤384 token），30s 时间线证据链成本≈看一帧；每格标注秒数、跨格对比引导 prompt；读画面小字请不加 `--grid` 用单帧 + `--detail high`
- feat: **VLM detail 档位**（`visual_level.py --detail` / 环境 `VLM_DETAIL`，默认 high）——读价格水印/型号等小字用 high/original
- fix: `understand_video.py` 补充 `base64` import（即看即答前置依赖）
- deps: requirements.txt 显式加入 `Pillow>=10.0`（grid 拼图）
- 说明：新 pipeline（`--level l1/l2`，engine/pipeline.py）经共享 `visual_level` 自动受益于 vision 模型配对；grid/即看即答在该路径的接入为后续增强

## 0.5.2 (2026-08-20)
- fix(security): **key/URL 配对缺陷**——`DEEPSEEK_API_KEY` 此前会发往默认的 `api.xiaomimimo.com`（mimo-v2.5）。三个配置加载点（stages.py / understand_video.py / visual_level.py）统一为配对逻辑：LLM_API_KEY 显式覆盖照用其 URL；DEEPSEEK_API_KEY 未设 LLM_API_URL 时配对 DeepSeek 端点与 deepseek-chat；credentials 文件 fallback 保持各自配对。规则：一把 key 绝不发往不是为它选定的主机。（PR #1204 审阅意见）
- fix(entry): 对外条目删除不可验证的三个数字（token 压缩 99.95%+ / 单视频 ~0.006 元 / 重复理解 ~1/20 成本）——README 顶部、package.json description、SKILL.md description、dsh/index.js 工具描述改为"它做什么"；成本测量保留在 docs/blog（含方法）。（PR #1204 审阅意见）
- test: 新增 TestLLMConfigPairing 4 用例（env 三场景 + credentials fallback），pytest fixture 隔离环境防污染

## 0.5.1 (2026-08-20)
- feat: **动态问题路由分层 v0.4**（`engine/router.py`）——视频类型做先验 + 问题意图决定入口 + 证据质量决定升级 + 隐私/预算决定上限
  - `classify_question`：15 类问题意图（规则优先，零模型成本）
  - `choose`：最终路由（意图/证据/隐私/预算四输入），`speech_dense` 不再限制视觉能力
  - `evidence_score`：已有证据充足度评估（or 型源任一命中即够）
  - `split_question`：复杂问题拆解（运动定位 + 视觉确认子任务）
- feat: **L1 obj_tracks 作为 L2 注意力引导器**——轨迹活跃窗口 → L2 只抽窗口帧
- feat: **预算上限 `--budget-cny`**——视觉成本估算超预算自动拦截 L2 降级 L0/L1
- feat: **语义层中间件**——`--layer` 建完整层（base 转写 + CLIP），建层后任何问题直接查层回答（`answered_from_layer`），文本问题 0 帧
- feat: 关键词定位别名表（ASR 误转：夏娃→下瓦/旨女儿），解说词滞后画面时窗口尾段 +5s 扩展
- feat: unknown class 拆分 `motion_confidence`/`class_confidence`（轨迹可信、类别不确定）
- fix: `answer_from_layer` visual_notes 未写回 ctx.avis → 结果缺视觉描述；assemble_result avis 补 `visual_notes` 输出
- fix: Node OUTPUT_SCHEMA.video string→object（Python 0.5.0 新格式），render 兼容双格式，`--l2-window`→`--window`
- perf: transcribe 内容寻址缓存（同一视频二次提问跳过 ASR，45s→0s）
- test: 103 passed（router 29 + 定位辅助 + 别名 + 预算）

## 0.5.0 (2026-08-20)
- feat: 首次调用自动创建插件内 `.venv` 并安装核心依赖（优先 uv，回退 venv+pip 清华镜像）——装完即用，零手动命令，不污染系统 Python
- feat: `npx dsvu doctor` 环境自检（Python/ffmpeg/yt-dlp/pip 依赖/API key/模型缓存），逐项给出修复命令，支持 `--fix` 一键修复与 `--json` 输出
- feat: 分层 requirements——L0 核心 ~300MB；语义层（torch/CLIP/YOLO ~2GB）可选，建层时再装
- fix: `detectPython()` 删除硬编码 macOS framework 路径，跨平台（env → 插件 .venv → 系统 python）
- fix: 补上 `package.json` 引用但缺失的 `engine/requirements.txt`（此前装完即报 ModuleNotFoundError）
- docs: SKILL.md 删除 live-clip 陈旧引用；新增 `experiments/` 对照实验（信息层 vs 字幕基线 vs 抽帧基线）

## 0.4.0 (2026-08-19)
- feat: 默认使用 MiMo v2.5（全模态推理模型），一个 API key 搞定
- feat: 自动从 `~/.dsh/.credentials.yaml` 读取 API key（无需手动配置环境变量）
- feat: 支持 B站 bangumi/番剧链接（直接走 yt-dlp，无需 BV 号）
- feat: Python 自动检测（优先 Framework 3.13 有依赖的版本）
- fix: MiMo v2.5 推理模型 max_tokens 调优（避免推理耗尽导致空内容）
- perf: LLM 调用 max_tokens 提升（locate 600 / keywords 400 / quality 300 / answer 1200）

## 0.1.1 (2026-08-17)
- feat: `video_understand` tool supports L1/L2 visual levels (`level`/`window` params) — on-demand frame sampling + qwen3-vl-flash, +0.0005 CNY for frame-level details
- test: tool registration + schema self-test (mock ctx)
- ci: run self-test on push/PR

## 0.1.0 (2026-08-17)
- feat: `video_understand` tool — Bilibili link / BV / local video → AVIS info layer → summary + Q&A
- token compression 99.95%+ vs frame sampling; ~0.006 CNY/video; repeat understanding ~1/20 via prompt cache
