"""model_cache.py — 模型文件的本地缓存与按需下载（当前只有 yolov8n.pt）。

## 为什么有这个东西

`yolov8n.pt`（约 6.2 MiB）原先直接提交在仓库里，于是它同时进了 git 历史和 npm 包
（整个 tarball 几乎全是它）。0.6.9 起改为**按需下载**：仓库不再携带任何二进制，
首次真正需要 YOLO 语义标签时才把它落到本地缓存。

## 多源与校验

下面两个源返回的是**字节不同**的两份 yolov8n 快照，因此各自独立做 size + sha256
校验（不是"同一个文件的两个镜像"）：

  1. GitHub Releases（ultralytics/assets v8.3.0）
     —— 与本项目历史上提交的那份逐字节相同（sha256 f59b3d83…）
  2. hf-mirror（Ultralytics/YOLOv8，国内可达）
     —— 同类权重的另一份快照（sha256 31e20dde…）

任一源校验不通过就换下一个；全部失败则明确报错并返回 None，调用方据此降级
（YOLO 语义标签缺失不影响 L0/L1 主流程）。

## 缓存位置

    ~/.cache/dsvu/models/yolov8n.pt          （可用 DSVU_MODEL_DIR 覆盖目录）

## 环境变量

    DSVU_YOLO_MODEL   显式指定模型文件路径（跳过下载；离线/内网场景用）
    DSVU_MODEL_DIR    覆盖缓存目录
    DSVU_NO_DOWNLOAD  设为 1 时只查本地、绝不联网

## CLI

    python3 model_cache.py --status     # 只查状态，不下载
    python3 model_cache.py --ensure     # 缺则下载
    python3 model_cache.py --ensure --force   # 强制重新下载
    python3 model_cache.py --status --json
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

# ── 已知模型：名称 → [(源标签, URL, 字节数, sha256), ...] ─────────────────────
MODELS = {
    "yolov8n.pt": [
        (
            "github-releases",
            "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
            6549796,
            "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
        ),
        (
            "hf-mirror",
            "https://hf-mirror.com/Ultralytics/YOLOv8/resolve/main/yolov8n.pt",
            6534387,
            "31e20dde3def09e2cf938c7be6fe23d9150bbbe503982af13345706515f2ef95",
        ),
    ],
}

DOWNLOAD_TIMEOUT = 300          # 单个源的整体超时（秒）
CHUNK = 1 << 16
UA = "dsvu-model-cache/1.0 (+https://github.com/ilps2/dsvu-videounderstanding)"


def cache_dir() -> Path:
    """模型缓存目录（默认 ~/.cache/dsvu/models）。"""
    override = os.environ.get("DSVU_MODEL_DIR")
    root = Path(override).expanduser() if override else Path.home() / ".cache" / "dsvu" / "models"
    return root


def legacy_paths(name: str) -> list:
    """历史遗留位置，按优先级排列（老版本插件或用户手工放置的副本）。"""
    engine_dir = Path(__file__).resolve().parent
    return [
        engine_dir / "models" / name,           # ≤0.6.8 随包分发的位置
        Path("/tmp") / name,
        Path.home() / ".cache" / name,
    ]


def find_local(name: str = "yolov8n.pt") -> Optional[Path]:
    """查找本地已有副本，按「显式指定 → 缓存目录 → 历史位置」的顺序。"""
    explicit = os.environ.get("DSVU_YOLO_MODEL")
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
    cached = cache_dir() / name
    if cached.is_file():
        return cached
    for p in legacy_paths(name):
        if p.is_file():
            return p
    return None


def verify(path: Path, name: str) -> tuple:
    """校验文件大小与 sha256 是否命中该模型的任一已知源。返回 (ok, 说明)。"""
    try:
        size = path.stat().st_size
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
    except OSError as e:
        return False, f"无法读取 {path}: {e}"

    for label, _url, want_size, want_hash in MODELS.get(name, []):
        if size == want_size and digest == want_hash:
            return True, f"校验通过（{label}）"
    known = ", ".join(f"{s}@{h[:8]}…" for _l, _u, s, h in MODELS.get(name, []))
    return False, f"校验不通过：实际 {size}@{digest[:8]}…，已知 {known}"


def _download_one(name: str, label: str, url: str, want_size: int, want_hash: str,
                  dest: Path, quiet: bool) -> bool:
    part = dest.with_name(dest.name + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        h = hashlib.sha256()
        got = 0
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, part.open("wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                got += len(chunk)
        if got != want_size or h.hexdigest() != want_hash:
            if not quiet:
                print(f"    ✗ {label}: 校验失败（{got}@{h.hexdigest()[:8]}…，"
                      f"期望 {want_size}@{want_hash[:8]}…）", file=sys.stderr)
            part.unlink(missing_ok=True)
            return False
        os.replace(part, dest)
        if not quiet:
            print(f"    ✓ {label}: 已下载并通过校验（{got // 1024} KiB）", file=sys.stderr)
        return True
    except Exception as e:
        part.unlink(missing_ok=True)
        if not quiet:
            print(f"    ✗ {label}: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def ensure(name: str = "yolov8n.pt", force: bool = False, quiet: bool = False) -> Optional[Path]:
    """确保模型在本地可用：已有且校验通过则直接返回；否则按源顺序下载。

    返回 Path 表示可用；返回 None 表示本地没有且下载失败——调用方应当降级，
    不要把它当成致命错误（YOLO 语义标签是可选增强）。

    校验策略（只保护"我们自己的"文件，不干扰用户显式指定的文件）：
      - DSVU_YOLO_MODEL 指定的路径：直接用，不校验（用户自己的权重，可能是自定义模型）
      - 缓存目录内的文件：校验；不通过就改名为 `<名字>.bad` 后重新下载（不静默丢文件）
      - 历史遗留位置：校验，不通过则跳过并说明原因
    """
    if not force:
        explicit = os.environ.get("DSVU_YOLO_MODEL")
        if explicit:
            p = Path(explicit).expanduser()
            if p.is_file():
                return p
            if not quiet:
                print(f"  ⚠️ DSVU_YOLO_MODEL 指向的文件不存在：{p}，改走缓存/下载", file=sys.stderr)

        cached = cache_dir() / name
        if cached.is_file():
            ok, detail = verify(cached, name)
            if ok:
                return cached
            bad = cached.with_name(cached.name + ".bad")
            try:
                os.replace(cached, bad)
                moved = f"，已改名为 {bad.name}"
            except OSError:
                moved = ""
            if not quiet:
                print(f"  ⚠️ 缓存中的 {name} {detail}{moved}；将重新下载", file=sys.stderr)

        for p in legacy_paths(name):
            if not p.is_file():
                continue
            ok, detail = verify(p, name)
            if ok:
                return p
            if not quiet:
                print(f"  ⚠️ 跳过 {p}：{detail}", file=sys.stderr)

    if os.environ.get("DSVU_NO_DOWNLOAD") == "1":
        if not quiet:
            print(f"  ⚠️ 未找到可用的 {name}，且 DSVU_NO_DOWNLOAD=1，跳过下载", file=sys.stderr)
        return None

    sources = MODELS.get(name) or []
    if not sources:
        if not quiet:
            print(f"  ⚠️ {name} 没有已知下载源", file=sys.stderr)
        return None

    dest = cache_dir() / name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if not quiet:
            print(f"  ⚠️ 无法创建缓存目录 {dest.parent}: {e}", file=sys.stderr)
        return None

    if not quiet:
        print(f"  首次使用需要下载 {name}（约 {sources[0][2] // 1024 // 1024} MiB），"
              f"缓存到 {dest}", file=sys.stderr)
    for label, url, want_size, want_hash in sources:
        if _download_one(name, label, url, want_size, want_hash, dest, quiet):
            return dest
    if not quiet:
        print(f"  ⚠️ {name} 全部下载源均失败；可用 DSVU_YOLO_MODEL 指定本地路径，"
              f"或用 DSVU_NO_DOWNLOAD=1 静默降级", file=sys.stderr)
    return None


def status(name: str = "yolov8n.pt") -> dict:
    """诊断用：返回本地状态，不触发下载。"""
    p = find_local(name)
    info = {
        "name": name,
        "cacheDir": str(cache_dir()),
        "found": bool(p),
        "path": str(p) if p else None,
        "legacy": (str(p) in [str(x) for x in legacy_paths(name)]) if p else False,
        "bytes": p.stat().st_size if p else None,
        "verified": None,
        "detail": None,
    }
    if p:
        ok, detail = verify(p, name)
        info["verified"] = ok
        info["detail"] = detail
    return info


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    name = "yolov8n.pt"
    as_json = "--json" in argv
    if "--status" in argv or not ({"--ensure", "--force"} & set(argv)):
        info = status(name)
        if as_json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            if info["found"]:
                print(f"{name}: {info['path']}（{info['bytes']} 字节）— {info['detail']}")
            else:
                print(f"{name}: 本地没有（缓存目录 {info['cacheDir']}）")
        return 0 if info["found"] and info["verified"] is not False else 1

    p = ensure(name, force="--force" in argv, quiet=as_json)
    if as_json:
        print(json.dumps({"ok": bool(p), "path": str(p) if p else None}, ensure_ascii=False))
    elif p:
        print(f"{name}: 就绪 {p}")
    else:
        print(f"{name}: 不可用（见上方原因）", file=sys.stderr)
    return 0 if p else 1


if __name__ == "__main__":
    raise SystemExit(main())
