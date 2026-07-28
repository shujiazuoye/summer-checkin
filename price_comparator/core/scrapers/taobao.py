"""淘宝采集器.

真实抓取入口: https://s.taobao.com/search?q=xxx
淘宝搜索强依赖登录态与风控, 未登录访问会跳转登录页或返回空壳.
此处实现真实请求 + 尽力解析, 失败自动回退模拟数据.
若需纯真实采集, 在 __init__ 注入 cookies (含登录态) 后效果更佳.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Product
from .base import BaseScraper


class TaobaoScraper(BaseScraper):
    platform = "taobao"
    name = "淘宝"
    base_url = "https://item.taobao.com/item.htm?id="

    def _fetch(self, keyword: str) -> str:
        url = f"https://s.taobao.com/search?q={quote(keyword)}&imgfile=&js=1&stats_click=search_radio_all"
        resp = self.session.get(url, timeout=self.timeout)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def _parse(self, html: str, keyword: str) -> list[Product]:
        products: list[Product] = []

        # 1) 优先尝试解析页面内嵌的 JSON (g_page_config / __INITIAL_DATA__ 等)
        for pattern in (
            r"g_page_config\s*=\s*(\{.*?\});",
            r"__INITIAL_DATA__\s*=\s*(\{.*?\});",
            r'"auctions"\s*:\s*(\[.*?\])',
        ):
            m = re.search(pattern, html, re.S)
            if not m:
                continue
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            auctions = data if isinstance(data, list) else (
                data.get("mods", {}).get("itemlist", {}).get("data", {}).get("auctions")
                or data.get("auctions")
                or []
            )
            for a in auctions:
                try:
                    products.append(Product(
                        platform=self.platform,
                        product_id=str(a.get("nid") or a.get("item_id") or ""),
                        name=(a.get("raw_title") or a.get("title") or "").strip(),
                        price=self._to_float(str(a.get("view_price") or a.get("price") or "0")),
                        sales=self._to_int(str(a.get("view_sales") or a.get("sale") or "0")),
                        shop_name=a.get("nick") or a.get("shop_name") or "淘宝店铺",
                        shop_rating=self._to_float(str(a.get("shop_rating") or "4.8")) or 4.8,
                        url=f"https://item.taobao.com/item.htm?id={a.get('nid') or a.get('item_id')}",
                        query=keyword,
                    ))
                except Exception:  # noqa: BLE001
                    continue
            if products:
                return products

        # 2) 回退到 HTML 解析 (老版页面结构)
        soup = BeautifulSoup(html, "html.parser")
        for it in soup.select(".J_MouserOnverReq, .items .item, [class*='Card--']"):
            try:
                name_el = it.select_one(".title, .J_ClickStat, [class*='title']")
                price_el = it.select_one(".price, .price strong, [class*='price']")
                sale_el = it.select_one(".deal-cnt, [class*='sale']")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                price = self._to_float(price_el.get_text() if price_el else "")
                if not name or price <= 0:
                    continue
                nid = it.get("data-nid") or ""
                products.append(Product(
                    platform=self.platform,
                    product_id=nid,
                    name=name,
                    price=price,
                    sales=self._to_int(sale_el.get_text() if sale_el else ""),
                    shop_name="淘宝店铺",
                    shop_rating=4.8,
                    url=f"https://item.taobao.com/item.htm?id={nid}" if nid else "",
                    query=keyword,
                ))
            except Exception:  # noqa: BLE001
                continue
        return products
