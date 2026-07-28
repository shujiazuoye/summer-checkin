"""商品横向对比 / 性价比打分 / 推荐标注."""
from __future__ import annotations

import statistics
from collections import defaultdict

from .models import Product


def compute_value_score(p: Product, price_stats: dict[str, tuple[float, float]]) -> float:
    """性价比分 = 销量分 * 评分分 / 价格分.

    - 价格分: 价格越低于均值越高 (对数压缩, 防止极端值)
    - 销量分: 销量越高越好 (对数压缩)
    - 评分分: 店铺评分
    最终归一化到 0-100.
    """
    import math
    avg_price, _ = price_stats.get(p.platform, (p.price, p.price))
    # 价格分: 均价=1, 价格越低分越高, 上限 2
    price_score = min(2.0, max(0.2, avg_price / max(p.price, 0.01)))
    # 销量分: log 压缩
    sales_score = math.log10(max(p.sales, 1) + 1) + 1
    # 评分分
    rating_score = p.shop_rating / 5.0
    raw = price_score * sales_score * rating_score
    return round(raw, 4)


def tag_recommendations(products: list[Product]) -> list[Product]:
    """按价格从低到高排序, 并打推荐标签."""
    if not products:
        return products

    # 1. 按平台统计价格, 用于性价比计算
    by_platform: dict[str, list[float]] = defaultdict(list)
    for p in products:
        by_platform[p.platform].append(p.price)
    price_stats = {
        plat: (statistics.mean(prices), statistics.stdev(prices) if len(prices) > 1 else 0.0)
        for plat, prices in by_platform.items()
    }

    # 2. 计算性价比分
    for p in products:
        p.value_score = compute_value_score(p, price_stats)

    # 3. 按价格从低到高排序
    products.sort(key=lambda x: (x.price, -x.value_score))
    for i, p in enumerate(products, 1):
        p.price_rank = i

    # 4. 推荐标注
    #    best_value: 性价比分最高 (Top1)
    #    popular: 销量 Top1
    #    premium: 评分最高且价格不低于中位数
    if products:
        best = max(products, key=lambda x: x.value_score)
        best.recommend_tag = "best_value"
        popular = max(products, key=lambda x: x.sales)
        if popular.recommend_tag == "":
            popular.recommend_tag = "popular"
        median_price = statistics.median(p.price for p in products)
        premium_candidates = [p for p in products if p.price >= median_price and p.recommend_tag == ""]
        if premium_candidates:
            premium = max(premium_candidates, key=lambda x: x.shop_rating)
            premium.recommend_tag = "premium"

    return products


def platform_summary(products: list[Product]) -> list[dict]:
    """各平台汇总统计 (用于横向对比展示)."""
    summary: list[dict] = []
    by_platform: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by_platform[p.platform].append(p)
    plat_name = {"jd": "京东", "taobao": "淘宝", "pdd": "拼多多"}
    for plat, ps in by_platform.items():
        prices = [p.price for p in ps]
        summary.append({
            "platform": plat,
            "platform_name": plat_name.get(plat, plat),
            "count": len(ps),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "avg_price": round(statistics.mean(prices), 2),
            "median_price": round(statistics.median(prices), 2),
            "avg_rating": round(statistics.mean(p.shop_rating for p in ps), 2),
            "total_sales": sum(p.sales for p in ps),
        })
    summary.sort(key=lambda x: x["avg_price"])
    return summary
