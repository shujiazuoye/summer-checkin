"""数据清洗 / 去重 / 归一化."""
from __future__ import annotations

import re

from .models import Product


def _normalize_name(name: str) -> str:
    """归一化商品名: 去除多余空白 / 全角符号 / 营销噪音词, 便于去重."""
    if not name:
        return ""
    # 全角转半角
    name = name.translate(str.maketrans({"（": "(", "）": ")", "，": ",", "：": ":"}))
    # 去除连续空白
    name = re.sub(r"\s+", " ", name).strip()
    # 去除常见营销前缀
    name = re.sub(r"^\[(官方|正品|包邮|旗舰)\]\s*", "", name)
    return name


def clean(products: list[Product]) -> list[Product]:
    """清洗: 过滤无效 -> 名称归一化 -> 去重 -> 价格规整."""
    seen: set[str] = set()
    cleaned: list[Product] = []
    for p in products:
        # 过滤无效商品
        if not p.name or p.price <= 0 or p.price > 10_000_000:
            continue
        # 归一化
        p.name = _normalize_name(p.name)
        p.price = round(float(p.price), 2)
        p.sales = max(0, int(p.sales or 0))
        p.shop_rating = round(min(5.0, max(0.0, float(p.shop_rating or 0))), 2)
        # 去重: 同一平台 + 商品ID (或名称+价格)
        key = p.dedup_key
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(p)
    return cleaned
