"""数据可视化: matplotlib 生成价格对比 / 价格-销量 / 平台统计 / 价格趋势图表.

图表方案
--------
1. price_comparison.png  - 全量商品价格横向对比 (按价格升序, 平台着色, 标注推荐)
2. price_vs_sales.png    - 价格 vs 销量气泡图 (气泡大小=店铺评分, 高亮性价比)
3. platform_stats.png    - 各平台 价格区间 (min/avg/max) 分组柱状图
4. price_trend.png       - 价格趋势折线图 (基于多次采集历史, TopN 最低价商品)

中文字体: 自动探测系统 CJK 字体, 找不到时回退默认字体 (中文可能显示为方框, 但不影响出图).
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 非交互后端, 适合服务端/CLI
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .models import Product


# ---------------------------------------------------------------------
# 中文字体探测
# ---------------------------------------------------------------------
def _pick_cjk_font() -> str | None:
    candidates = [
        "Noto Sans CJK SC", "Noto Sans CJK", "Source Han Sans SC",
        "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "SimHei",
        "Microsoft YaHei", "PingFang SC", "Heiti SC", "AR PL UMing CN",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    # 扫描系统字体目录
    for d in ("/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts")):
        if not os.path.isdir(d):
            continue
        for p in Path(d).rglob("*"):
            if p.suffix.lower() in (".ttf", ".ttc", ".otf") and any(
                k in p.name.lower() for k in ("cjk", "noto", "wqy", "hei", "yahei", "song")
            ):
                try:
                    font_manager.fontManager.addfont(str(p))
                    return font_manager.FontProperties(fname=str(p)).get_name()
                except Exception:  # noqa: BLE001
                    continue
    return None


_CJK_FONT = _pick_cjk_font()
if _CJK_FONT:
    plt.rcParams["font.sans-serif"] = [_CJK_FONT, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 平台配色
PLATFORM_COLORS = {
    "jd": "#e1251b",      # 京东红
    "taobao": "#ff6a00",  # 淘宝橙
    "pdd": "#e02e24",     # 拼多多红
}
PLATFORM_NAMES = {"jd": "京东", "taobao": "淘宝", "pdd": "拼多多"}


# ---------------------------------------------------------------------
# 历史快照 (用于趋势图)
# ---------------------------------------------------------------------
def history_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "history.json"


def append_snapshot(keyword: str, products: list[Product], data_dir: str | Path) -> None:
    """记录一次采集快照, 供趋势图使用."""
    p = history_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    history: dict = {}
    if p.exists():
        try:
            history = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = {}
    history.setdefault(keyword, []).append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "products": [
            {"name": x.name, "price": x.price, "platform": x.platform}
            for x in products
        ],
    })
    # 仅保留最近 30 次快照
    history[keyword] = history[keyword][-30:]
    p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def get_snapshots(keyword: str, data_dir: str | Path) -> list[dict]:
    p = history_path(data_dir)
    if not p.exists():
        return []
    try:
        history = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return history.get(keyword, [])


# ---------------------------------------------------------------------
# 绘图
# ---------------------------------------------------------------------
def _short(name: str, n: int = 22) -> str:
    name = name.replace(" ", "")
    return name if len(name) <= n else name[:n] + "…"


def plot_price_comparison(products: list[Product], out_path: str | Path) -> str:
    """1. 价格横向对比柱状图 (按价格升序)."""
    if not products:
        return ""
    ps = sorted(products, key=lambda x: x.price)
    labels = [_short(p.name) for p in ps]
    prices = [p.price for p in ps]
    colors = [PLATFORM_COLORS.get(p.platform, "#888") for p in ps]
    # 推荐商品加金色边框
    edge_colors = ["#ffd700" if p.recommend_tag else "none" for p in ps]
    lw = [2.0 if p.recommend_tag else 0 for p in ps]

    fig, ax = plt.subplots(figsize=(10, max(4, 0.42 * len(ps))))
    bars = ax.barh(labels, prices, color=colors, edgecolor=edge_colors, linewidth=lw)
    for bar, p in zip(bars, ps):
        ax.text(bar.get_width() + max(prices) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"¥{p.price}", va="center", fontsize=8)
    ax.set_xlabel("价格 (元)")
    ax.set_title("商品价格横向对比 (升序, 金边=推荐)")
    ax.invert_yaxis()
    # 图例 (平台)
    from matplotlib.patches import Patch
    legend = [Patch(facecolor=c, label=PLATFORM_NAMES.get(k, k)) for k, c in PLATFORM_COLORS.items()]
    ax.legend(handles=legend, loc="lower right", fontsize=8)
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def plot_price_vs_sales(products: list[Product], out_path: str | Path) -> str:
    """2. 价格 vs 销量气泡图."""
    if not products:
        return ""
    fig, ax = plt.subplots(figsize=(10, 6))
    for p in products:
        size = (p.shop_rating / 5.0) * 400 + 60
        color = PLATFORM_COLORS.get(p.platform, "#888")
        ax.scatter(p.price, max(p.sales, 1), s=size, c=color, alpha=0.6, edgecolors="white")
        if p.recommend_tag:
            ax.scatter(p.price, max(p.sales, 1), s=size, facecolors="none",
                       edgecolors="#ffd700", linewidths=2)
            ax.annotate(p.recommend_tag, (p.price, p.sales),
                        fontsize=8, color="#b8860b", ha="left", va="bottom")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("价格 (元, 对数)")
    ax.set_ylabel("销量 (对数)")
    ax.set_title("价格-销量分布 (气泡大小=店铺评分, 金圈=推荐)")
    from matplotlib.patches import Patch
    legend = [Patch(facecolor=c, label=PLATFORM_NAMES.get(k, k)) for k, c in PLATFORM_COLORS.items()]
    ax.legend(handles=legend, loc="upper right", fontsize=8)
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def plot_platform_stats(products: list[Product], out_path: str | Path) -> str:
    """3. 各平台价格区间分组柱状图."""
    if not products:
        return ""
    by_plat: dict[str, list[float]] = defaultdict(list)
    for p in products:
        by_plat[p.platform].append(p.price)
    plats = list(by_plat.keys())
    mins = [min(by_plat[k]) for k in plats]
    avgs = [sum(by_plat[k]) / len(by_plat[k]) for k in plats]
    maxs = [max(by_plat[k]) for k in plats]

    import numpy as np
    x = np.arange(len(plats))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width, mins, width, label="最低价", color="#4caf50")
    ax.bar(x, avgs, width, label="均价", color="#2196f3")
    ax.bar(x + width, maxs, width, label="最高价", color="#f44336")
    ax.set_xticks(x)
    ax.set_xticklabels([PLATFORM_NAMES.get(k, k) for k in plats])
    ax.set_ylabel("价格 (元)")
    ax.set_title("各平台价格区间对比")
    ax.legend()
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def plot_price_trend(keyword: str, data_dir: str | Path, out_path: str | Path, top_n: int = 5) -> str:
    """4. 价格趋势折线图 (基于历史快照, 取 TopN 最低价商品)."""
    snaps = get_snapshots(keyword, data_dir)
    if not snaps:
        return ""
    # 取最近一次快照中价格最低的 TopN 商品名作为追踪对象
    last = snaps[-1]["products"]
    targets = [x["name"] for x in sorted(last, key=lambda x: x["price"])[:top_n]]

    fig, ax = plt.subplots(figsize=(10, 5))
    import numpy as np
    for name in targets:
        xs = list(range(len(snaps)))
        ys = []
        for s in snaps:
            match = next((p["price"] for p in s["products"] if p["name"] == name), None)
            ys.append(match)
        if all(y is None for y in ys):
            continue
        ax.plot(xs, ys, marker="o", label=_short(name, 18))
    ax.set_xticks(range(len(snaps)))
    ax.set_xticklabels([s["ts"][5:16] for s in snaps], rotation=30, fontsize=8)
    ax.set_ylabel("价格 (元)")
    ax.set_title(f"[{keyword}] 价格趋势 ({len(snaps)} 次采集, Top{top_n} 最低价)")
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def render_all(products: list[Product], keyword: str, data_dir: str | Path) -> dict[str, str]:
    """生成全部图表, 返回 {图表名: 文件路径}."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    jobs = [
        ("price_comparison", lambda: plot_price_comparison(products, data_dir / "price_comparison.png")),
        ("price_vs_sales", lambda: plot_price_vs_sales(products, data_dir / "price_vs_sales.png")),
        ("platform_stats", lambda: plot_platform_stats(products, data_dir / "platform_stats.png")),
        ("price_trend", lambda: plot_price_trend(keyword, data_dir, data_dir / "price_trend.png")),
    ]
    for name, fn in jobs:
        try:
            path = fn()
            if path:
                out[name] = path
        except Exception as e:  # noqa: BLE001
            print(f"[visualizer] {name} 绘图失败: {e}")
    return out
