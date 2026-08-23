#!/usr/bin/env python3
"""
grid 拼图 vs 独立帧：同一视频 DSV 全程，视觉链路的成本/质量对比。
  G 组 = DSVU_VISUAL_GRID=1（L2 一窗拼一张大图 + 回答轮发拼图，≤3×384 token）
  F 组 = DSVU_VISUAL_GRID=0（L2 独立帧 + 回答轮 12 张独立图，≤12×384 token）
用法: python3 experiments/compare_grid_vs_frames.py <BV或本地视频> [--workdir /tmp/dsvu_compare]
输出: experiments/results/{tag}_grid.json / {tag}_frames.json
"""
import json, os, subprocess, sys, yaml, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = os.environ.get("VIDEO_UNDERSTAND_PYTHON", str(REPO / ".venv" / "bin" / "python3"))
if not Path(PY).exists():
    PY = "python3"
ENGINE = REPO / "engine" / "understand_video.py"
RESULTS = REPO / "experiments" / "results"

from compare_dsv_vs_mimo import QUESTIONS, load_keys

def run(target, grid_on, workdir, key):
    env = dict(os.environ)
    env.update({"DEEPSEEK_API_KEY": key, "DSVU_VISUAL_GRID": "1" if grid_on else "0",
                "LLM_API_KEY": "", "LLM_API_URL": "", "LLM_MODEL": ""})
    cmd = [PY, str(ENGINE), target, "--no-download", "--no-cache", "--json"]
    for q in QUESTIONS:
        cmd += ["--ask", q]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400, env=env)
    elapsed = time.time() - t0
    if r.returncode != 0:
        return {"error": r.stderr[-400:], "elapsed_s": round(elapsed)}
    text = r.stdout
    start = text.find("{")
    d = json.JSONDecoder().raw_decode(text, start)[0]
    d["elapsed_s"] = d.get("elapsed_s", round(elapsed))
    return d

def main():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--workdir", default="/tmp/dsvu_compare")
    args = ap.parse_args()
    dk, _ = load_keys()
    if not dk:
        sys.exit("无 DEEPSEEK_API_KEY")
    tag = Path(args.target).stem
    out = {}
    for on, name in [(True, "grid"), (False, "frames")]:
        print(f"▶ [{name}] DSVU_VISUAL_GRID={'1' if on else '0'} ...", flush=True)
        d = run(args.target, on, args.workdir, dk)
        d["grid_mode"] = on
        json.dump(d, open(RESULTS / f"{tag}_{name}.json", "w"), ensure_ascii=False, indent=2)
        out[name] = d
        print(f"  {name}: {d.get('elapsed_s','?')}s | 成本 {d.get('cost_cny','?')} | 视觉 {d.get('visual_cost_cny','?')} | 升级 {d.get('upgrades')}", flush=True)
    # 对比
    print("\n===== 对比 =====")
    for n in ("grid", "frames"):
        d = out[n]
        if "error" in d:
            print(f"{n}: ❌ {d['error'][:100]}"); continue
        print(f"{n}: 耗时 {d.get('elapsed_s')}s | 总成本 {d.get('cost_cny')} 元 | 视觉成本 {d.get('visual_cost_cny')} 元 | 升级 {d.get('upgrades')}")

if __name__ == "__main__":
    main()
