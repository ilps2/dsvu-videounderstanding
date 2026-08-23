#!/usr/bin/env python3
"""
dsvu vs MiMo 对比实验：同一视频、同一套 10 题，两组各跑一次。
  F1 = DSV 全程：deepseek-v4-flash-vision-exp（主模型+视觉同源，即看即答）
  F2 = MIMO 全程：mimo-v2.5（主模型+视觉）
对比：精度（盲评另行打分）、成本 cost_cny、耗时、token、升级链。

用法:
  python3 experiments/compare_dsv_vs_mimo.py <解说BV> <舞蹈BV> <教程BV>
  # 或指定本地视频（--no-download 语义，见 VIDEO_* 环境变量）

输出: experiments/results/{解说|舞蹈|教程}_{dsv|mimo}.json
"""
import argparse, json, os, re, subprocess, sys, time, yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = os.environ.get("VIDEO_UNDERSTAND_PYTHON", str(REPO / ".venv" / "bin" / "python3"))
if not Path(PY).exists():
    PY = os.environ.get("VIDEO_UNDERSTAND_PYTHON") or "python3"
ENGINE = REPO / "engine" / "understand_video.py"
RESULTS = REPO / "experiments" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

# 固定 10 题（benchmark.md 分类：概括×2 细节×4 推断×2 视觉×2），每视频同一套
QUESTIONS = [
    "这段视频的核心内容是什么？用 3-5 句话概括。",
    "视频的主题是什么？主要人物或主体是谁？",
    "视频中出现了哪些具体人物或角色？分别是谁？",
    "视频中提到了哪些关键数字（数量/价格/时间/克数等）？",
    "视频中出现了哪些重要物品或道具？",
    "视频中的关键事件发生在什么时间或顺序？",
    "这段视频适合什么场景或人群使用？",
    "视频作者想传达的核心意图是什么？",
    "视频中人物的穿着或外观有什么特点？",
    "视频的画面色调、场景氛围或动作细节是怎样的？",
]

def load_keys():
    """读 ~/.dsh/.credentials.yaml，返回 (deepseek_key, xiaomi_key)。"""
    cred = Path(os.path.expanduser("~/.dsh/.credentials.yaml"))
    d = yaml.safe_load(open(cred)) if cred.exists() else {}
    return d.get("DEEPSEEK_API_KEY", ""), d.get("XIAOMI_API_KEY", "")

def get_video(bv, workdir):
    """下载或复用本地视频，返回 (path, title)。"""
    local = workdir / f"{bv}.mp4"
    if local.exists() and local.stat().st_size > 100_000:
        return str(local), ""
    os.makedirs(workdir, exist_ok=True)
    bili = os.path.expanduser("~/.agents/skills/bilibili-downloader/scripts/bili_download.py")
    r = subprocess.run([PY, bili, "download", bv, "--quality", "360", "-o", str(workdir)],
                       capture_output=True, text=True, timeout=1200)
    if r.returncode != 0:
        raise SystemExit(f"下载失败 {bv}: {r.stderr[-300:]}")
    mp4s = sorted(workdir.glob("*.mp4"), key=os.path.getmtime)
    if not mp4s:
        raise SystemExit(f"下载后无 mp4: {bv}")
    # 重命名为 BV 名（方便复用）
    p = mp4s[-1]
    target = workdir / f"{bv}.mp4"
    if p != target:
        target.unlink(missing_ok=True); p.rename(target)
    return str(target), ""

def run_group(bv, workdir, key, model_label, extra_env):
    """跑一组：10 题。返回 JSON 结果 dict。"""
    video, _ = get_video(bv, workdir)
    env = dict(os.environ)
    env.update(extra_env)
    # 使用 --no-download 直接分析本地视频（标题用 BV 名）
    cmd = [PY, str(ENGINE), video, "--no-download", "--no-cache", "--json"]
    for q in QUESTIONS:
        cmd += ["--ask", q]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400, env=env)
    elapsed = time.time() - t0
    if r.returncode != 0:
        print(f"  ❌ {model_label} 失败 rc={r.returncode}: {r.stderr[-400:]}")
        return {"group": model_label, "bv": bv, "error": r.stderr[-400:], "elapsed_s": round(elapsed)}
    text = r.stdout
    start = text.find("{")
    try:
        d = json.JSONDecoder().raw_decode(text, start)[0]
    except Exception as e:
        print(f"  ❌ {model_label} JSON 解析失败: {e}")
        return {"group": model_label, "bv": bv, "error": str(e),
                "elapsed_s": round(elapsed), "stdout_tail": text[-500:]}
    d["group"] = model_label
    d["bv"] = bv
    d["elapsed_s"] = d.get("elapsed_s", round(elapsed))
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+", help="3 个 BV（解说 舞蹈 教程）或本地视频路径")
    ap.add_argument("--workdir", default="/tmp/dsvu_compare")
    args = ap.parse_args()
    bvs = args.targets[:3]
    workdir = Path(args.workdir)

    dk, xk = load_keys()
    if not dk:
        print("⚠️ 未找到 DEEPSEEK_API_KEY，DSV 组将失败", file=sys.stderr)
    if not xk:
        print("⚠️ 未找到 XIAOMI_API_KEY，MIMO 组将失败", file=sys.stderr)

    labels = ["解说", "舞蹈", "教程"]
    all_results = {}
    for bv, label in zip(bvs, labels):
        print(f"\n===== {label}（{bv}）=====", flush=True)
        # 两组共享同一视频 + 同一 AVIS 信息层缓存（/tmp/dsvu_compare/avis_cache）
        if dk:
            print(f"▶ [{label}/dsv] deepseek-v4-flash-vision-exp 全程...", flush=True)
            all_results[f"{label}_dsv"] = run_group(
                bv, workdir, dk, "dsv",
                {"DEEPSEEK_API_KEY": dk, "LLM_API_KEY": "", "LLM_API_URL": "", "LLM_MODEL": ""})
        if xk:
            print(f"▶ [{label}/mimo] mimo-v2.5 全程...", flush=True)
            all_results[f"{label}_mimo"] = run_group(
                bv, workdir, xk, "mimo",
                {"LLM_API_KEY": xk, "DEEPSEEK_API_KEY": ""})
        # 保存
        for tag, res in all_results.items():
            if res.get("bv") == bv:
                out = RESULTS / f"{tag}.json"
                json.dump(res, open(out, "w"), ensure_ascii=False, indent=2)

    # 汇总
    print("\n===== 汇总 =====")
    for tag, res in sorted(all_results.items()):
        if "error" in res:
            print(f"{tag}: ❌ {res['error'][:100]}")
            continue
        costs = res.get("cost_cny", 0)
        print(f"{tag}: 耗时 {res.get('elapsed_s', '?')}s | 成本 {costs} 元 | "
              f"升级 {res.get('upgrades')} | 压缩 {res.get('token_compression_pct', '?')}%")
    print(f"\n原始数据: {RESULTS}/")

if __name__ == "__main__":
    main()
