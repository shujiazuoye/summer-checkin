"""商品数据模型."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Product:
    """统一的商品数据结构, 覆盖各平台采集到的关键字段."""

    platform: str            # jd / taobao / pdd
    product_id: str          # 平台内商品唯一ID
    name: str                # 商品标题
    price: float             # 价格 (元)
    sales: int               # 销量 (月销 / 已售)
    shop_name: str           # 店铺名称
    shop_rating: float       # 店铺评分 (0-5)
    url: str                 # 商品链接
    image_url: str = ""      # 主图链接
    query: str = ""          # 采集时使用的关键词

    # 对比阶段填充的字段
    value_score: float = 0.0       # 性价比分 (越高越值得)
    recommend_tag: str = ""        # 推荐标注: best_value / popular / premium / ""
    price_rank: int = 0            # 价格排名 (1 = 最便宜)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """去重键: 平台 + 商品ID (回退到 名称归一化 + 价格)."""
        if self.product_id:
            return f"{self.platform}:{self.product_id}"
        norm = "".join(c for c in self.name.lower() if c.isalnum())
        return f"{self.platform}:{norm}:{self.price:.2f}"
