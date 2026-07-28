"""采集器基类: 统一 HTTP 抓取流程 + 失败回退到确定性模拟数据.

设计说明
--------
真实采集京东 / 淘宝 / 拼多多时, 平台均有强反爬 (登录态、滑块验证、JS 渲染、风控).
本工具采用 "真实请求优先, 模拟数据兜底" 的策略:

1. 先用带浏览器 UA 的 requests 发起真实 HTTP 请求, 尝试从返回的 HTML / 接口中解析商品.
2. 若被反爬拦截 (空结果 / 跳登录 / 超时 / 403), 自动回退到基于关键词的确定性模拟数据,
   保证工具在任何环境下都能直接运行并产出可演示结果.
3. 真实场景接入时, 只需在子类中实现 `_fetch` / `_parse`, 并按需注入 cookies / proxy,
   即可切换为纯真实采集.

模拟数据以关键词 hash 为随机种子, 保证同一关键词多次采集结果一致, 便于对比与趋势展示.
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from ..models import Product


# 通用浏览器请求头, 规避最基础的反爬检测
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

# 模拟数据词库: 用于根据关键词生成真实感强的商品标题 / 店铺名
_BRANDS = ["小米", "华为", "荣耀", "OPPO", "vivo", "联想", "戴尔", "苹果", "三星", "realme", "一加", "iQOO"]
_SUFFIXES = [
    "官方旗舰款", "2024 新品", "大容量长续航", "正品包邮", "快充版", "Pro Max",
    "学生必备", "高配版", "国行正品", "礼盒装", "全国联保", "增强版",
]
_SHOP_SUFFIX = {
    "jd": ["京东自营旗舰店", "官方旗舰店", "数码专营店", "京东电器专卖店"],
    "taobao": ["天猫旗舰店", "淘宝企业店", "品牌直销店", "官方授权店"],
    "pdd": ["拼多多官方店", "百亿补贴店", "品牌特卖店", "工厂直销店"],
}


def _seed(keyword: str, platform: str) -> int:
    """关键词 + 平台 -> 稳定随机种子."""
    h = hashlib.md5(f"{platform}:{keyword}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


class BaseScraper(ABC):
    """采集器基类."""

    platform: str = "base"
    name: str = "基类"
    base_url: str = ""
    timeout: float = 8.0

    def __init__(self, headers: dict[str, str] | None = None, timeout: float | None = None):
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        if timeout is not None:
            self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.last_source: str = ""  # real / mock, 用于结果溯源

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def search(self, keyword: str, limit: int = 10) -> list[Product]:
        """按关键词采集商品. 真实抓取失败则回退模拟数据."""
        products: list[Product] = []
        try:
            html = self._fetch(keyword)
            if html:
                products = self._parse(html, keyword)
        except Exception as e:  # noqa: BLE001 - 任何异常都回退, 保证可运行
            self._log(f"[{self.platform}] 真实抓取失败, 回退模拟数据: {type(e).__name__}: {e}")

        if not products:
            self._log(f"[{self.platform}] 未解析到商品 (可能被反爬拦截), 使用模拟数据")
            products = self._mock(keyword, limit)
            self.last_source = "mock"
        else:
            self.last_source = "real"

        return products[:limit]

    # ------------------------------------------------------------------
    # 子类实现: 真实抓取
    # ------------------------------------------------------------------
    @abstractmethod
    def _fetch(self, keyword: str) -> str:
        """发起 HTTP 请求, 返回页面文本 / 接口原始响应."""

    @abstractmethod
    def _parse(self, html: str, keyword: str) -> list[Product]:
        """从返回内容解析商品列表."""

    # ------------------------------------------------------------------
    # 模拟数据生成 (兜底)
    # ------------------------------------------------------------------
    def _mock(self, keyword: str, limit: int) -> list[Product]:
        rng = random.Random(_seed(keyword, self.platform))
        upper = max(limit, 4)
        lower = max(1, upper - 3)
        n = rng.randint(lower, upper)
        products: list[Product] = []
        used_ids: set[str] = set()
        for i in range(n):
            pid = self._gen_id(rng)
            while pid in used_ids:
                pid = self._gen_id(rng)
            used_ids.add(pid)

            brand = rng.choice(_BRANDS) if rng.random() < 0.7 else ""
            suffix = rng.choice(_SUFFIXES)
            spec = rng.choice(["标准版", "高配版", "尊享版", "青春版", ""]) if rng.random() < 0.5 else ""
            name = " ".join(p for p in [brand, keyword, spec, suffix] if p)

            price = round(rng.uniform(*self._price_range(keyword)), 2)
            sales = rng.randint(0, 50000)
            shop = rng.choice(_SHOP_SUFFIX.get(self.platform, ["官方店"]))
            rating = round(rng.uniform(4.5, 4.99), 2)
            url = self._build_url(pid)

            products.append(Product(
                platform=self.platform,
                product_id=pid,
                name=name,
                price=price,
                sales=sales,
                shop_name=shop,
                shop_rating=rating,
                url=url,
                query=keyword,
            ))
        return products

    # ------------------------------------------------------------------
    # 子类可覆盖的辅助
    # ------------------------------------------------------------------
    def _price_range(self, keyword: str) -> tuple[float, float]:
        """根据关键词粗略推断价格区间, 默认 9.9 - 1999."""
        return (9.9, 1999.0)

    def _gen_id(self, rng: random.Random) -> str:
        return str(rng.randint(10**9, 10**10 - 1))

    def _build_url(self, pid: str) -> str:
        return f"{self.base_url}{pid}"

    def _log(self, msg: str) -> None:
        print(msg)

    # ------------------------------------------------------------------
    # 公共工具
    # ------------------------------------------------------------------
    @staticmethod
    def _to_int(text: str) -> int:
        """'1.2万' / '1.2万+' / '3500' -> int."""
        if not text:
            return 0
        text = re.sub(r"[+,，]", "", text.strip())
        m = re.match(r"^([\d.]+)\s*万?$", text)
        if not m:
            digits = re.sub(r"\D", "", text)
            return int(digits) if digits else 0
        num = float(m.group(1))
        if "万" in text:
            num *= 10000
        return int(num)

    @staticmethod
    def _to_float(text: str) -> float:
        if not text:
            return 0.0
        m = re.search(r"\d+(?:\.\d+)?", text)
        return float(m.group()) if m else 0.0
