"""采集器子包."""
from .base import BaseScraper
from .jd import JDScraper
from .taobao import TaobaoScraper
from .pdd import PDDScraper

__all__ = ["BaseScraper", "JDScraper", "TaobaoScraper", "PDDScraper"]
