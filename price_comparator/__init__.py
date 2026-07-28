"""电商商品价格自动化采集与对比工具。

整体架构:
    core.models        - 商品数据模型 (Product)
    core.scrapers      - 平台采集器 (京东/淘宝/拼多多), 真实 HTTP 抓取 + 失败回退到模拟数据
    core.cleaner       - 数据清洗 / 去重 / 归一化
    core.comparator    - 排序 / 性价比打分 / 推荐标注
    core.visualizer    - matplotlib 可视化 (价格对比 / 价格-销量 / 平台统计 / 价格趋势)
    cli                - 命令行入口
    web                - Flask 演示网页 (输入关键词现场运行)
"""
__version__ = "1.0.0"
