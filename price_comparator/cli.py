"""命令行工具入口.

用法:
    python -m price_comparator.cli search "蓝牙耳机" --platforms jd taobao pdd --limit 8
    python -m price_comparator.cli trend "蓝牙耳机"
    python -m price_comparator.cli search "手机" --no-charts --json-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .core.pipeline import PLATFORM_MAP, run_pipeline
from .core.visualizer import get_snapshots, plot_price_trend

PLATFORM_NAMES = {"jd": "京东", "taobao": "淘宝", "pdd": "拼多多"}
TAG_CN = {"best_value": "★性价比之选", "popular": "🔥爆款", "premium": "💎优选"}


# ---------------------------------------------------------------------
# 表格打印
# ---------------------------------------------------------------------
def _safe_len(s: str) -> int:
    """中英文混排宽度 (中文算2)."""
    return sum(2 if ord(c) > 127 else 1 for c in s)


def _pad(s: str, width: int, align: str = "left") -> str:
    s = str(s)
    pad = max(0, width - _safe_len(s))
    if align == "right":
        return " " * pad + s
    return s + " " * pad


def _truncate(s: str, width: int) -> str:
    s = str(s)
    if _safe_len(s) <= width:
        return s
    out = ""
    cur = 0
    for c in s:
        w = 2 if ord(c) > 127 else 1
        if cur + w > width - 1:
            return out + "…"
        out += c
        cur += w
    return out


def print_table(products: list[dict]) -> None:
    if not products:
        print("  (无商品)")
        return
    cols = [
        ("排名", 4, "right"),
        ("平台", 6, "left"),
        ("商品名称", 40, "left"),
        ("价格", 10, "right"),
        ("销量", 10, "right"),
        ("评分", 5, "right"),
        ("店铺", 18, "left"),
        ("推荐", 12, "left"),
    ]
    # 表头
    header = "  ".join(_pad(name, w, a) for name, w, a in cols)
    sep = "  ".join("-" * w for _, w, _ in cols)
    print(header)
    print(sep)
    for p in products:
        tag = TAG_CN.get(p.get("recommend_tag", ""), "")
        row = [
            _pad(str(p["price_rank"]), 4, "right"),
            _pad(PLATFORM_NAMES.get(p["platform"], p["platform"]), 6, "left"),
            _pad(_truncate(p["name"], 40), 40, "left"),
            _pad(f"¥{p['price']:.2f}", 10, "right"),
            _pad(str(p["sales"]), 10, "right"),
            _pad(f"{p['shop_rating']:.1f}", 5, "right"),
            _pad(_truncate(p["shop_name"], 18), 18, "left"),
            _pad(tag, 12, "left"),
        ]
        print("  ".join(row))


def print_summary(summary: list[dict]) -> None:
    print("\n各平台汇总:")
    print(f"  {'平台':<8}{'数量':>4}{'最低':>10}{'均价':>10}{'最高':>10}{'均评分':>8}{'总销量':>12}")
    for s in summary:
        print(f"  {s['platform_name']:<6}{s['count']:>4}"
              f"{s['min_price']:>10.2f}{s['avg_price']:>10.2f}{s['max_price']:>10.2f}"
              f"{s['avg_rating']:>8.2f}{s['total_sales']:>12}")


# ---------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------
def cmd_search(args: argparse.Namespace) -> int:
    result = run_pipeline(
        keyword=args.keyword,
        platforms=args.platforms,
        limit_per_platform=args.limit,
        data_dir=args.out,
        with_charts=not args.json_only and not args.no_charts,
    )
    meta = result["meta"]
    print(f"\n关键词: {args.keyword}")
    print(f"采集来源: {meta['sources']}  (real=真实抓取, mock=模拟兜底)")
    print(f"原始 {meta['total_raw']} 条 -> 去重清洗后 {meta['total_clean']} 条, 耗时 {meta['elapsed_sec']}s")

    print("\n商品列表 (按价格升序):")
    print_table(result["products"])
    print_summary(result["summary"])

    # 保存 JSON
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fa5]", "_", args.keyword)[:32]
    json_path = out_dir / f"result_{safe}.json"
    serializable = {**result, "charts": {k: str(v) for k, v in result["charts"].items()}}
    json_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {json_path}")
    if result["charts"]:
        print("图表已生成:")
        for name, path in result["charts"].items():
            print(f"  - {name}: {path}")
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    snaps = get_snapshots(args.keyword, out_dir)
    if not snaps:
        print(f"未找到 [{args.keyword}] 的历史采集记录, 请先运行 search.")
        return 1
    print(f"[{args.keyword}] 共 {len(snaps)} 次采集记录:")
    for i, s in enumerate(snaps, 1):
        prices = [p["price"] for p in s["products"]]
        print(f"  {i}. {s['ts']}  共{len(prices)}件  最低¥{min(prices):.2f} 均价¥{sum(prices)/len(prices):.2f}")
    png = plot_price_trend(args.keyword, out_dir, out_dir / "price_trend.png")
    print(f"趋势图: {png}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="price_comparator",
        description="电商商品价格自动化采集与对比工具 (京东/淘宝/拼多多)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("search", help="按关键词采集并对比")
    ps.add_argument("keyword", help="搜索关键词")
    ps.add_argument("--platforms", nargs="+", default=list(PLATFORM_MAP),
                    choices=list(PLATFORM_MAP), help="采集平台 (默认全部)")
    ps.add_argument("--limit", type=int, default=8, help="每个平台采集条数 (默认8)")
    ps.add_argument("--out", default="data", help="输出目录 (默认 data)")
    ps.add_argument("--no-charts", action="store_true", help="不生成图表")
    ps.add_argument("--json-only", action="store_true", help="仅输出 JSON (隐含 --no-charts)")
    ps.set_defaults(func=cmd_search)

    pt = sub.add_parser("trend", help="查看关键词的历史价格趋势")
    pt.add_argument("keyword", help="搜索关键词")
    pt.add_argument("--out", default="data", help="数据目录 (默认 data)")
    pt.set_defaults(func=cmd_trend)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
