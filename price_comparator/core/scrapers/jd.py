"""京东采集器.

真实抓取入口: https://search.jd.com/Search?keyword=xxx&enc=utf-8
京东搜索页服务端返回 HTML, 商品位于 <li class="gl-item"> / <li data-sku="...">,
内含商品名 (.p-name em), 价格 (.p-price i), 店铺 (.p-shop a), 链接, 评论数等.
价格部分由 JS 异步加载, 此处优先取 HTML 内可见价格, 取不到则回退模拟数据.
"""
from __future__ import annotations

from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Product
from .base import BaseScraper


class JDScraper(BaseScraper):
    platform = "jd"
    name = "京东"
    base_url = "https://item.jd.com/"

    def _fetch(self, keyword: str) -> str:
        url = f"https://search.jd.com/Search?keyword={quote(keyword)}&enc=utf-8&wq={quote(keyword)}"
        # 适度延迟, 降低被风控概率
        resp = self.session.get(url, timeout=self.timeout)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def _parse(self, html: str, keyword: str) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.gl-item, li.J_goodsList li, div.gl-i-wrap")
        if not items:
            items = soup.select("li[data-sku]")
        products: list[Product] = []
        for it in items:
            try:
                name_el = it.select_one(".p-name em, .p-name a, .p-name-type-2 a")
                price_el = it.select_one(".p-price i, .p-price strong i, .p-price .J_%s" % "")
                shop_el = it.select_one(".p-shop a, .p-shop span")
                link_el = it.select_one(".p-name a")
                sku = it.get("data-sku") or it.get("data-pid") or ""

                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue
                price = self._to_float(price_el.get_text() if price_el else "")
                if price <= 0:
                    # 价格由 JS 异步加载, 取不到则跳过交给兜底逻辑
                    continue
                shop = shop_el.get_text(strip=True) if shop_el else "京东"
                href = link_el.get("href", "") if link_el else ""
                if href.startswith("//"):
                    href = "https:" + href
                elif href and not href.startswith("http"):
                    href = "https://item.jd.com/" + (sku or href.lstrip("/"))

                products.append(Product(
                    platform=self.platform,
                    product_id=sku or href,
                    name=name,
                    price=price,
                    sales=self._to_int(""),  # 京东搜索页不直接暴露销量, 留空
                    shop_name=shop,
                    shop_rating=4.7,  # 京东搜索页无店铺评分, 给默认值
                    url=href,
                    query=keyword,
                ))
            except Exception:  # noqa: BLE001
                continue
        return products
