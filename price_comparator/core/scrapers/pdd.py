"""拼多多采集器.

真实抓取入口: https://mobile.yangkeduo.com/proxy/api/searchResult?q=xxx (移动端 API)
拼多多强风控, 需要 anti_content 签名与登录态, 未授权基本无法直连.
此处实现真实请求尝试 + 失败回退模拟数据.
"""
from __future__ import annotations

import json
from urllib.parse import quote

from ..models import Product
from .base import BaseScraper


class PDDScraper(BaseScraper):
    platform = "pdd"
    name = "拼多多"
    base_url = "https://mobile.yangkeduo.com/goods.html?goods_id="

    def _fetch(self, keyword: str) -> str:
        # 移动端搜索接口 (需签名, 此处尝试, 失败由上层兜底)
        url = (
            "https://mobile.yangkeduo.com/proxy/api/searchResult?"
            f"q={quote(keyword)}&page=1&size=20&sort=default"
        )
        resp = self.session.get(url, timeout=self.timeout)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def _parse(self, html: str, keyword: str) -> list[Product]:
        products: list[Product] = []
        try:
            data = json.loads(html)
        except (json.JSONDecodeError, ValueError):
            return products

        items = (
            data.get("data") if isinstance(data, dict) else None
        ) or []
        if isinstance(items, dict):
            items = items.get("list") or items.get("items") or []
        for a in items:
            try:
                goods = a.get("goods") if isinstance(a, dict) else None
                a = goods or a
                gid = str(a.get("goods_id") or a.get("id") or "")
                price = self._to_float(str(a.get("min_normal_price") or a.get("price") or "0"))
                # 拼多多价格单位常为分
                if price > 100000:
                    price /= 100
                products.append(Product(
                    platform=self.platform,
                    product_id=gid,
                    name=(a.get("goods_name") or a.get("name") or "").strip(),
                    price=price,
                    sales=self._to_int(str(a.get("sales_tip") or a.get("cnt") or "0")),
                    shop_name=a.get("mall_name") or "拼多多店铺",
                    shop_rating=self._to_float(str(a.get("mall_rating") or "4.7")) or 4.7,
                    url=f"https://mobile.yangkeduo.com/goods.html?goods_id={gid}",
                    query=keyword,
                ))
            except Exception:  # noqa: BLE001
                continue
        return products
