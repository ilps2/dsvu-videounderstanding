# -*- coding: utf-8 -*-
"""
dsvu 成本核算模块：按模型官方价目 + 峰谷时段。

官方价目（元 / 百万 token）：
  DeepSeek V4-Flash-Vision-Exp（= V4-Flash 价，2026-08-17 起峰谷计费）：
    峰时（北京 9:00-12:00 / 14:00-18:00，仅工作日）  输入命中 0.10 / 未命中 3.0 / 输出 9.0
    谷时（其余，含周末全天）                        输入命中 0.05 / 未命中 1.5 / 输出 4.5
    图片：官方确认每张图片最高折算 384 tokens，按输入价计入（含在 API 的 prompt_tokens 中）。
  MiMo v2.5（国内定价，2026-05-27 永久降价后）：
    输入命中 0.02 / 未命中 1.0 / 输出 2.0（无峰谷）

  注：2026-08-23 起周末（周六/日）取消峰谷定价，全天按空闲价执行。

模型选择优先级（与 _load_*_config 配对一致）：deepseek 前缀 → deepseek-vision；mimo → mimo-v2.5。
"""
from datetime import datetime, timedelta

# 价目表：元 / 百万 token，每项 (谷时价, 峰时价)
PRICES = {
    "deepseek-vision": {"hit": (0.05, 0.10), "miss": (1.5, 3.0), "out": (4.5, 9.0)},
    "mimo-v2.5":       {"hit": (0.02, 0.02), "miss": (1.0, 1.0), "out": (2.0, 2.0)},
}

# DeepSeek 峰时（北京 9-12、14-18）；MiMo 无峰谷
PEAK_SLOTS = ((9, 12), (14, 18))


def price_key(model):
    """模型名 → 价目 key（前缀匹配，容错版本后缀）。"""
    m = (model or "").lower()
    if "mimo" in m:
        return "mimo-v2.5"
    return "deepseek-vision"   # 默认按 DeepSeek（含 deepseek-chat / deepseek-v4-flash-*）


def is_peak(now=None):
    """当前是否 DeepSeek 高峰时段（北京 9:00-12:00 / 14:00-18:00）。
    2026-08-23 起：周末（周六/周日）无峰谷定价，全天按空闲价执行。"""
    if now is None:
        now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() >= 5:      # 5=周六, 6=周日 → 无峰谷，全天空闲价
        return False
    h = now.hour
    return any(a <= h < b for a, b in PEAK_SLOTS)


def get_prices(model):
    """返回当前时段单价 (hit, miss, out)，元/百万 token。"""
    k = price_key(model)
    p = PRICES[k]
    idx = 1 if (k == "deepseek-vision" and is_peak()) else 0
    return p["hit"][idx], p["miss"][idx], p["out"][idx]


def calc_cost(usage, model=None):
    """按模型 + 当前时段算成本。返回 (cost_cny, hit_tokens, miss_tokens)。"""
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit) or 0
    out = usage.get("completion_tokens", 0) or 0
    ph, pm, po = get_prices(model)
    return hit / 1e6 * ph + miss / 1e6 * pm + out / 1e6 * po, hit, miss


def calc_visual_cost(pin, pout, model=None):
    """视觉 VLM 调用成本（pin 已含图片 token，DeepSeek 每图≤384 token）。
    返回 (cost_cny, 单价说明)。"""
    _, pm, po = get_prices(model)
    return pin / 1e6 * pm + pout / 1e6 * po, f"输入{pm}/输出{po}元每百万(当前时段)"


def peak_hint(model=None):
    """运行时段提示：峰时提醒可等谷时，谷时提示当前低价。"""
    if price_key(model) != "deepseek-vision":
        return "✓ MiMo 无峰谷价，随时跑成本一致。"
    now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() >= 5:
        return "✓ 周末无峰谷定价，全天执行空闲价（输入未命中 1.5 元/百万），随时跑成本最低。"
    if is_peak():
        return ("⚠ 当前为 DeepSeek 高峰时段（北京 9:00-12:00 / 14:00-18:00），价格约为谷时 2 倍"
                "（输入未命中 3.0 vs 1.5 元/百万）。批量视频理解建议设 DSVU_WAIT_OFFPEAK=1，"
                "脚本将自动等待谷时再开始。")
    return "✓ 当前为 DeepSeek 空闲时段，成本最低（输入未命中 1.5 元/百万）。"


def next_offpeak_minutes(now=None):
    """距下一次谷时开始的分钟数（仅在峰时调用有意义）。"""
    if now is None:
        now = datetime.utcnow() + timedelta(hours=8)
    h, m = now.hour, now.minute
    for a, b in PEAK_SLOTS:
        if a <= h < b:
            end_h = b
            break
    else:
        return 0
    minutes_to = (end_h * 60) - (h * 60 + m)
    return max(1, minutes_to)
