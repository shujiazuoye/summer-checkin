"""Flask 演示网页后端.

路由:
    GET  /                  主页 (含架构说明 / 数据示例 / 现场运行)
    GET  /api/sample        返回初始化用 数据示例 + 结果示例
    POST /api/search        现场运行采集流水线, 返回 JSON 结果
    GET  /api/trend?keyword=...   返回某关键词的历史采集快照 (用于趋势图)

启动:
    python -m price_comparator.web.app
    或:   flask --app price_comparator.web.app run --port 5000
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from ..core.pipeline import PLATFORM_MAP, run_pipeline
from ..core.visualizer import get_snapshots

HERE = Path(__file__).resolve().parent
EXAMPLES_DIR = HERE.parent / "examples"
DATA_DIR = HERE.parent / "web_data"  # 网页现场运行的数据/历史目录

app = Flask(__name__, template_folder=str(HERE / "templates"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PLATFORM_NAMES = {"jd": "京东", "taobao": "淘宝", "pdd": "拼多多"}


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


@app.route("/")
def index():
    return render_template("index.html", platforms=PLATFORM_NAMES)


@app.route("/api/sample")
def api_sample():
    """初始化展示用的 数据示例 (原始) + 结果示例 (处理后)."""
    raw = _load_json(EXAMPLES_DIR / "sample_raw.json")
    result = _load_json(EXAMPLES_DIR / "sample_result.json")
    # 结果示例对应的历史快照 (用于趋势图)
    sample_history = _load_json(EXAMPLES_DIR / "data" / "history.json") or {}
    return jsonify({
        "ok": True,
        "raw": raw,
        "result": result,
        "history": sample_history,
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    """现场运行: 接收关键词, 执行采集流水线, 返回结构化结果."""
    payload = request.get_json(silent=True) or {}
    keyword = (payload.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "关键词不能为空"}), 400
    platforms = payload.get("platforms") or list(PLATFORM_MAP.keys())
    # 仅保留合法平台
    platforms = [p for p in platforms if p in PLATFORM_MAP]
    if not platforms:
        platforms = list(PLATFORM_MAP.keys())
    try:
        limit = max(1, min(int(payload.get("limit", 6)), 20))
    except (TypeError, ValueError):
        limit = 6

    result = run_pipeline(
        keyword=keyword,
        platforms=platforms,
        limit_per_platform=limit,
        data_dir=DATA_DIR,
        with_charts=False,  # 网页用 Chart.js 前端绘制
    )
    # charts 字段对网页无用, 移除
    result.pop("charts", None)
    return jsonify({"ok": True, "result": result})


@app.route("/api/trend")
def api_trend():
    """返回某关键词的历史快照 (供前端趋势折线图)."""
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword 必填"}), 400
    snaps = get_snapshots(keyword, DATA_DIR)
    return jsonify({"ok": True, "keyword": keyword, "snapshots": snaps})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
