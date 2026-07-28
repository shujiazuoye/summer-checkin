"""采集-清洗-对比-可视化 流水线: CLI 与 Web 共用的核心编排."""
from __future__ import annotations

import time
from pathlib import Path

from .cleaner import clean
from .comparator import platform_summary, tag_recommendations
from .models import Product
from .scrapers import JDScraper, PDDScraper, TaobaoScraper
from .visualizer import append_snapshot, render_all

PLATFORM_MAP = {
    "jd": JDScraper,
    "taobao": TaobaoScraper,
    "pdd": PDDScraper,
}


def run_pipeline(
    keyword: str,
    platforms: list[str] | None = None,
    limit_per_platform: int = 8,
    data_dir: str | Path = "data",
    with_charts: bool = True,
) -> dict:
    """执行完整流程, 返回结构化结果.

    返回:
        {
            keyword, meta: {耗时, 来源, 各平台数量},
            products: [...],        # 排序+推荐标注后
            summary: [...],         # 平台汇总
            charts: {...},          # 图表路径 (仅 with_charts=True)
        }
    """
    platforms = platforms or list(PLATFORM_MAP.keys())
    start = time.time()

    # 1. 采集
    raw: list[Product] = []
    sources: dict[str, str] = {}
    counts: dict[str, int] = {}
    for plat in platforms:
        cls = PLATFORM_MAP.get(plat)
        if not cls:
            continue
        scraper = cls()
        items = scraper.search(keyword, limit=limit_per_platform)
        sources[plat] = scraper.last_source
        counts[plat] = len(items)
        raw.extend(items)

    # 2. 清洗 + 去重
    cleaned = clean(raw)

    # 3. 排序 + 性价比 + 推荐
    ranked = tag_recommendations(cleaned)

    # 4. 平台汇总
    summary = platform_summary(ranked)

    # 5. 记录历史快照
    data_dir = Path(data_dir)
    try:
        append_snapshot(keyword, ranked, data_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[pipeline] 写入历史失败: {e}")

    # 6. 可视化
    charts: dict[str, str] = {}
    if with_charts:
        charts = render_all(ranked, keyword, data_dir)

    elapsed = round(time.time() - start, 2)
    meta = {
        "elapsed_sec": elapsed,
        "total_raw": len(raw),
        "total_clean": len(ranked),
        "sources": sources,        # 各平台数据来源 real / mock
        "counts": counts,
    }
    return {
        "keyword": keyword,
        "meta": meta,
        "products": [p.to_dict() for p in ranked],
        "summary": summary,
        "charts": charts,
    }
