# dsvu

[![npm version](https://img.shields.io/npm/v/@svenyu%2Fdsvu)](https://www.npmjs.com/package/@svenyu/dsvu)
[![GitHub stars](https://img.shields.io/github/stars/ilps2/dsvu-videounderstanding)](https://github.com/ilps2/dsvu-videounderstanding)
[![license](https://img.shields.io/github/license/ilps2/dsvu-videounderstanding)](https://github.com/ilps2/dsvu-videounderstanding/blob/main/LICENSE)
[![language](https://img.shields.io/github/languages/top/ilps2/dsvu-videounderstanding)](https://github.com/ilps2/dsvu-videounderstanding)

低成本视频理解插件：给 dsh agent 注册 `video_understand` 工具——B站链接 / BV 号 / 本地视频 → AVIS 信息层（ASR 转写 + 场景结构 + 运动对象轨迹 + YOLO 语义）→ 摘要+问答。采用 Python 引擎：核心层需 faster-whisper / opencv / yt-dlp（约 200-300MB），可选语义层另需约 2GB 的 torch / transformers / ultralytics，内置 doctor --fix 一键建 venv 并装齐两者。

**dsvu 与 dsh-video-understand 的差异**（v0.6.0，fork 自 0.5.2）：
- **DeepSeek 视觉模型**：`DEEPSEEK_API_KEY` 配对时，视觉与主模型用 `deepseek-v4-flash-vision-exp`（2026-08-21 上线，单图≤384 token，与 V4-Flash 同价）
- **同源即看即答**：回答轮把抽帧画面与 ASR 信息层同一条消息直送视觉模型，消除"VLM 转述→文本→主 LLM"两段式损耗（`DSVU_DIRECT_VISION=0` 关闭）
- **L2 grid 密集拼图**：一窗密集帧拼成一张大图单次 VLM（≤384 token），30s 时间线证据链成本≈看一帧（`visual_level.py l2 ... --grid 6x6`）
- **信息层前缀缓存 + 结果缓存**：同视频追问缓存命中 96.6%，边际成本降至 ~1/5；同参数二次调用秒回
- **模型方案收敛**：默认全程 DeepSeek（主模型=视觉模型同源）；MiMo 组合降为回退选项（见"模型方案对比"）
- 包名/命令/缓存独立：`dsvu` / `npx dsvu` / `~/.cache/dsvu`

## 安装

```bash
# npm 安装
npm install @svenyu/dsvu

# 或 dsh plugin add @svenyu/dsvu
```

**装完即用**：首次调用 `video_understand` 时自动创建插件本地隔离环境（`.venv`）并安装核心依赖（优先 `uv`，回退 `venv`+pip 清华镜像）——无需手动执行任何命令，不污染系统 Python。

**引擎已内含**，无需额外克隆外部仓库。

### 环境自检

```bash
npx dsvu doctor        # 逐项检测 + 给出修复命令
npx dsvu doctor --fix  # 一键自动修复（建环境 + 装依赖）
```

前置条件仅两个：`ffmpeg`（macOS `brew install ffmpeg` / Ubuntu `sudo apt install ffmpeg`）和一个 LLM API key（见下表）。语义层依赖（torch/CLIP/YOLO，约 2GB）为可选，仅建完整语义层时再装：`pip install -r engine/requirements-layer.txt`。

## ⚠️ 数据流披露

| 级别 | 数据流向 | 说明 |
|---|---|---|
| **L0**（默认） | **完全本地** | ASR + 场景分类 + 运动检测，不上传任何数据 |
| **L1** | DeepSeek/MiMo API | 视频帧发送至 VLM 服务器进行视觉分析（DeepSeek key → `deepseek-v4-flash-vision-exp`；MiMo key → `mimo-v2.5`） |
| **L2** | DeepSeek/MiMo API | 视频帧发送至 VLM 服务器进行视觉分析 |

- L0 级别（默认）仅使用本地 ASR + 场景分类 + 运动检测，不涉及云服务
- L1/L2 级别会将视频帧（JPEG 编码）发送至 VLM API 进行视觉理解（DeepSeek 时含回答轮的"即看即答"直看帧）
- 帧数据仅用于单次 VLM 推理，不会被存储或用于训练

## 环境变量

| 变量 | 必需 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅* | **默认推荐**：只设这一个即可——主模型/定位器/视觉/回答轮统一用 `deepseek-v4-flash-vision-exp`（同源即看即答） |
| `LLM_API_KEY` | ❌ | **备选（回退）**：设小米/自定义 key 时按 LLM_API_URL/LLM_MODEL 走对应模型（如 mimo-v2.5） |
| `LLM_API_URL` | ❌ | 自定义 API endpoint（默认 `https://api.xiaomimimo.com/v1/chat/completions`，仅 LLM_API_KEY 模式用） |
| `LLM_MODEL` | ❌ | 自定义模型名（仅 LLM_API_KEY 模式用） |
| `VISION_MODEL` | ❌ | 视觉模型名（默认 `deepseek-v4-flash-vision-exp`，DeepSeek key 配对时用） |
| `VLM_DETAIL` | ❌ | 视觉图片 detail 档位（`low`/`high`/`original`/`auto`，默认 `high`） |
| `DSVU_DIRECT_VISION` | ❌ | 同源即看即答开关（默认 `1` 开；`0` 退回"VLM 描述→文本"旧链路） |
| `DSVU_VISUAL_GRID` | ❌ | L2 密集拼图开关（默认 `1` 开；`0` 用独立帧逐帧发，读小字更保真） |
| `DSVU_WAIT_OFFPEAK` | ❌ | 峰时自动等谷时再跑（默认关；批量任务设 `1` 省钱，DeepSeek 工作日谷时半价、周末全天低价） |
| `VIDEO_UNDERSTAND_PYTHON` | ❌ | Python 解释器路径（自动检测有依赖的 Python） |
| `BILI_DOWNLOAD_SCRIPT` | ❌ | bilibili-downloader 脚本路径（下载 B站视频用） |

> \* 未设置显式 key 时自动读 `~/.dsh/.credentials.yaml`，**DeepSeek 优先**（主模型=视觉模型，同源）。一个 key 搞定。
> **仅 DeepSeek 不可用时**才走备选：`export LLM_API_KEY=<小米key>` → 全程 mimo-v2.5（成本相近但质量低 ~0.9 分，见"模型方案对比"）。

## 工具

`video_understand(target, questions?, noDownload?, level?, window?)`

| 参数 | 类型 | 说明 |
|---|---|---|
| target | string | B站 URL / BV 号 / 本地视频绝对路径 |
| questions | string[] | 可选，自定义问题（默认 3 问） |
| noDownload | boolean | 本地文件置 true |
| level | string | `l0`(默认) / `l1`(+3-5帧VLM视觉摘要) / `l2`(+时间窗密集帧证据) |
| window | string | L2 时间窗，如 `10-30` 或秒数（auto=轨迹最活跃30s） |
| budgetCny | number | 单次问题预算上限（元），视觉成本估算超预算自动降级（拦截 L2 用 L0/L1 回答） |

返回 JSON：`video / duration_s / token_compression_pct / cost_cny / answers[]`。

## 结构

```
dsvu/
├── package.json
├── cordis.patch.yml
├── dsh/
│   └── index.js          # host 端：注册 video_understand 工具
├── engine/               # Python 引擎（核心层 + 可选语义层依赖）
│   ├── understand_video.py
│   ├── avis.py
│   ├── visual_level.py
│   ├── frame_prep.py
│   └── livestream-highlight/
│       └── asr.py
└── skills/
    └── video-understand/SKILL.md
```

## 模型方案对比（2026-08-22 实测：3 视频 × 10 题）

| 方案 | 配置 | 质量（盲评 1-5） | 成本（3 视频，谷时） | 耗时 |
|---|---|---|---|---|
| **全程 DSV**（推荐）| deepseek-v4-flash-vision-exp 主模型+视觉 | **4.77** | **0.089 元** | **209s** |
| 纯 mimo | mimo-v2.5 主模型+视觉 | 3.83 | 0.074 元 | 1310s |
| mimo+qwen | mimo 主模型 + qwen3-vl-flash 视觉 | ~3.8（估算）| ~0.09 元（估算）| ~1000s+ |

**结论：成本同一量级（0.07-0.09 元），全程 DSV 精度最高（+0.9 分）、速度最快（快 6.3 倍）**。
额外优势：单模型简化（无双模型维护）；信息层前缀缓存命中 96.6% → 同视频追问边际成本降至 ~1/5；谷时（工作日非 9-12/14-18，**以及周末全天**）再半价。
因此**模型方案收敛为全程 DSV**；MiMo 组合保留为回退（exp 模型不可用时的保险丝），不参与默认与基准。详见 [docs/blog-dsvu-vs-mimo-对比实验-2026-08-22.md](docs/blog-dsvu-vs-mimo-对比实验-2026-08-22.md)。

## 分级实测（2026-08）

| 层级 | 内容 | 数据流向 | 成本（估算*） |
|---|---|---|---|
| L0 信息层 | ASR+场景+轨迹+YOLO → 摘要/问答 | 本地 | 仅 LLM 文本成本 |
| L1 视觉级 | 3-5 帧 VLM → 颜色/姿态/衣着 | DeepSeek API | +数帧 VLM 成本 |
| L2 证据级 | 时间窗密集帧（可 grid 拼图）→ 时间线 | DeepSeek API | 按窗长（grid=单图） |

> \* 成本按 `engine/pricing.py` 官方价目 + 峰谷时段核算（可配置输入），实际随厂商定价变化。详见 [docs/blog-视频理解性价比实验](docs/blog-视频理解性价比实验-2026-08-20.md)（方法 + 实测）。

实测：电影解说 L1 补出「白色立领衬衫/神情凝重/暗色调诊室」（L0 完全给不出）；舞蹈 L2 逐帧「头部转 15-20°→45°、口型开口→闭合→微笑」。

## 已知边界

- **短视频快剪/变身合集**（非主流）：3-5 秒高速切换 + BGM 无语音 + 角色细节密集，模型抽帧易漏、识别不全（2026-08-22 实测 3:21 变身混剪识别约 5/8）。主流场景（解说/教程/直播/长片段纯视觉）不受影响，实测质量 4.5-4.9/5。

## 设计背景

本插件的核心目标是**低成本视频理解**：用信息层代替逐帧像素喂 LLM，单视频 LLM 调用仅需几千 token（具体成本取决于所选模型定价，见上）。

- **LLM 选型**：默认全程 DeepSeek（`deepseek-v4-flash-vision-exp`）——主模型与视觉同源，单模型简化 + 前缀缓存，性价比与精度最优；MiMo 保留为回退（见"模型方案对比"）
- **视觉级（L1/L2）**：DeepSeek 原生多模态，同源即看即答（帧图直进回答轮）+ grid 密集拼图（单图≤384 token）；L0 仍可纯本地

## 原理

引擎把视频压缩成**信息层**（ASR 转写 + 场景结构 + 运动对象轨迹 + YOLO 语义，约 1k token）再喂 LLM；同一视频重复理解时信息层缓存复用（内容哈希，二次提问跳过 ASR）。成本与 token 对比的具体测量见 [docs/blog-视频理解性价比实验](docs/blog-视频理解性价比实验-2026-08-20.md)。

## License

MIT
