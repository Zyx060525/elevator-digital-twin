"""电梯场域数字孪生 —— Web 前端（Flask 后端）。

运行：
    python webapp.py
然后浏览器打开 http://127.0.0.1:5000

页面功能：
  1. 单次仿真：参数面板 -> 指标卡片 + 空间热力网格（可逐步回放）+ 指标曲线
  2. 批量实验：交流意愿 × 乘客数 -> 对比表格 + 对比图（核心结论）
  3. Agnes 智能分析：真实调用 Agnes 模型（agnes-3.0-flash）输出分析与治理策略
"""
from __future__ import annotations

import base64
import io
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import Flask, jsonify, request, send_from_directory

from elevator_twin.model import ElevatorModel
from elevator_twin.model_enhanced import EnhancedElevatorModel
from elevator_twin.run import sweep
from elevator_twin import agnes_client

plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", "Microsoft YaHei",
    "PingFang SC", "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(ROOT, "templates")

app = Flask(__name__)

# 前后端同域部署（本地 python webapp.py / Render 一体化）时无需跨域；
# 前端放在 Netlify、后端放在 Render 时属跨域调用，这里统一放行。
# 想收紧权限可设置环境变量 CORS_ORIGIN=https://你的站点域名。
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")


@app.after_request
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


def _fig_to_dataurl(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/png;base64," + b64


def _parse_params() -> dict:
    data = request.get_json(silent=True) or {}

    def get(key, default, cast, lo, hi):
        try:
            v = cast(data.get(key, default))
        except (TypeError, ValueError):
            v = cast(default)
        return max(lo, min(hi, v))

    return {
        "width": get("width", 4, int, 2, 12),
        "height": get("height", 4, int, 2, 12),
        "n_passengers": get("n_passengers", 8, int, 1, 144),
        "chat_willingness_mean": get("chat_willingness_mean", 0.5, float, 0.0, 1.0),
        "comfort_distance": get("comfort_distance", 1.5, float, 0.5, 5.0),
        "chat_range": get("chat_range", 1.5, float, 0.5, 6.0),
        "chat_threshold": get("chat_threshold", 1.0, float, 0.0, 2.0),
        "steps": get("steps", 30, int, 1, 200),
        "seed": get("seed", 42, int, 0, 10**9),
    }


def _grid_data(model) -> list:
    """每格 {s: '.', 'P', 'C'; d: 最近邻距离(格) 或 None}。"""
    h, w = model.height, model.width
    cells = [[{"s": ".", "d": None} for _ in range(w)] for _ in range(h)]
    for a in model.schedule.agents:
        if a.pos is None:
            continue
        x, y = a.pos
        d = model.nearest_neighbor_distance(a)
        cells[y][x] = {
            "s": "C" if a.in_chat else "P",
            "d": round(float(d), 2) if d is not None else None,
        }
    return cells


def _curve_dataurl(df) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    df["avg_nearest_distance"].plot(ax=axes[0], marker="o", title="平均最近邻距离")
    df["violation_rate"].plot(ax=axes[1], marker="o", title="社交距离违规率")
    df["chat_pairs"].plot(ax=axes[2], marker="o", title="交流对数")
    for ax in axes:
        ax.set_xlabel("步数")
        ax.grid(True, alpha=0.3)
    fig.suptitle("指标随仿真步变化", fontsize=13)
    fig.tight_layout()
    return _fig_to_dataurl(fig)


def _curve_enhanced_dataurl(df) -> str:
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.4))
    df["avg_nearest_distance_m"].plot(ax=axes[0], marker="o", title="平均最近邻距离(米)")
    df["violation_rate"].plot(ax=axes[1], marker="o", title="社交距离违规率")
    df["chat_pairs"].plot(ax=axes[2], marker="o", title="交流对数")
    df["current_passengers"].plot(ax=axes[3], marker="o", title="当前乘客数")
    for ax in axes:
        ax.set_xlabel("步数")
        ax.grid(True, alpha=0.3)
    fig.suptitle("增强版：真实尺寸 + 上下客 + 社会力（指标随仿真步变化）", fontsize=13)
    fig.tight_layout()
    return _fig_to_dataurl(fig)


def _parse_enhanced_params() -> dict:
    data = request.get_json(silent=True) or {}

    def get(key, default, cast, lo, hi):
        try:
            v = cast(data.get(key, default))
        except (TypeError, ValueError):
            v = cast(default)
        return max(lo, min(hi, v))

    return {
        "width_m": get("width_m", 1.6, float, 0.8, 5.0),
        "depth_m": get("depth_m", 1.4, float, 0.8, 5.0),
        "cell_size": get("cell_size", 0.4, float, 0.1, 1.0),
        "n_floors": get("n_floors", 6, int, 2, 40),
        "board_interval": get("board_interval", 5, int, 1, 50),
        "max_passengers": get("max_passengers", 6, int, 1, 40),
        "comfort_distance_m": get("comfort_distance_m", 1.0, float, 0.3, 2.0),
        "chat_willingness_mean": get("chat_willingness_mean", 0.5, float, 0.0, 1.0),
        "chat_range_m": get("chat_range_m", 0.8, float, 0.3, 2.0),
        "chat_threshold": get("chat_threshold", 1.0, float, 0.0, 2.0),
        "repulsion_strength": get("repulsion_strength", 1.0, float, 0.0, 5.0),
        "attraction_strength": get("attraction_strength", 0.5, float, 0.0, 5.0),
        "steps": get("steps", 30, int, 1, 200),
        "seed": get("seed", 42, int, 0, 10**9),
    }


@app.get("/")
def index():
    return send_from_directory(TEMPLATES, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "agnes_ready": agnes_client.available()})

@app.post("/api/simulate")
def simulate():
    p = _parse_params()
    try:
        model = ElevatorModel(
            width=p["width"], height=p["height"], n_passengers=p["n_passengers"],
            comfort_distance=p["comfort_distance"],
            chat_willingness_mean=p["chat_willingness_mean"],
            chat_range=p["chat_range"], chat_threshold=p["chat_threshold"],
            seed=p["seed"],
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    frames = [model.grid_snapshot()]  # 第 0 步
    for _ in range(p["steps"]):
        model.step()
        frames.append(model.grid_snapshot())

    df = model.datacollector.get_model_vars_dataframe()
    final = df.iloc[-1]
    metrics = {
        "avg_nearest_distance": round(float(final["avg_nearest_distance"]), 3),
        "min_nearest_distance": round(float(final["min_nearest_distance"]), 3),
        "violation_rate": round(float(final["violation_rate"]), 3),
        "chat_pairs": int(final["chat_pairs"]),
        "chat_pair_distance": round(float(final["chat_pair_distance"]), 3),
    }
    return jsonify({
        "metrics": metrics,
        "grid": _grid_data(model),
        "frames": frames,
        "curve": _curve_dataurl(df),
    })


@app.post("/api/simulate_enhanced")
def simulate_enhanced():
    p = _parse_enhanced_params()
    try:
        model = EnhancedElevatorModel(
            width_m=p["width_m"], depth_m=p["depth_m"], cell_size=p["cell_size"],
            n_floors=p["n_floors"], board_interval=p["board_interval"],
            max_passengers=p["max_passengers"],
            comfort_distance_m=p["comfort_distance_m"],
            chat_willingness_mean=p["chat_willingness_mean"],
            chat_range_m=p["chat_range_m"], chat_threshold=p["chat_threshold"],
            repulsion_strength=p["repulsion_strength"],
            attraction_strength=p["attraction_strength"], seed=p["seed"],
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    frames = [model.grid_snapshot()]
    floors = [model.current_floor]
    passengers = [len(model.schedule.agents)]
    for _ in range(p["steps"]):
        model.step()
        frames.append(model.grid_snapshot())
        floors.append(model.current_floor)
        passengers.append(len(model.schedule.agents))

    df = model.datacollector.get_model_vars_dataframe()
    final = df.iloc[-1]
    metrics = {
        "avg_nearest_distance_m": round(float(final["avg_nearest_distance_m"]), 3),
        "min_nearest_distance_m": round(float(final["min_nearest_distance_m"]), 3),
        "violation_rate": round(float(final["violation_rate"]), 3),
        "chat_pairs": int(final["chat_pairs"]),
        "current_passengers": int(final["current_passengers"]),
        "current_floor": int(final["current_floor"]),
        "width": model.width,
        "height": model.height,
        "cell_size": model.cell_size,
    }
    return jsonify({
        "metrics": metrics,
        "grid": _grid_data(model),
        "frames": frames,
        "floors": floors,
        "passengers": passengers,
        "curve": _curve_enhanced_dataurl(df),
        "unit": "m",
    })


@app.post("/api/sweep")
def sweep_api():
    data = request.get_json(silent=True) or {}
    try:
        steps = int(data.get("steps", 30))
        seed = int(data.get("seed", 42))
    except (TypeError, ValueError):
        steps, seed = 30, 42
    table = sweep(steps=steps, seed=seed, verbose=False)
    rows = table.to_dict(orient="records")

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for w, grp in table.groupby("交流意愿"):
        axes[0].plot(grp["乘客数"], grp["平均最近邻距离"], marker="o", label=f"交流意愿={w}")
        axes[1].plot(grp["乘客数"], grp["社交距离违规率"], marker="o", label=f"交流意愿={w}")
        axes[2].plot(grp["乘客数"], grp["交流对数"], marker="o", label=f"交流意愿={w}")
    axes[0].set_title("平均最近邻距离")
    axes[1].set_title("社交距离违规率")
    axes[2].set_title("交流对数")
    for ax in axes:
        ax.set_xlabel("乘客数")
        ax.grid(True, alpha=0.3)
        ax.legend()
    fig.suptitle("交流意愿 × 乘客数 对比实验", fontsize=13)
    fig.tight_layout()
    return jsonify({"table": rows, "plot": _fig_to_dataurl(fig)})


@app.post("/api/agnes")
def agnes():
    if not agnes_client.available():
        return jsonify({"error": "未检测到 Agnes Key（elevator_twin/.agnes_key）"}), 400
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "analyze")
    metrics = data.get("metrics") or {}
    goal = data.get("goal", "优化电梯轿厢内的社交距离")

    if mode == "plan":
        system = (
            "你是 Agnes，密闭空间治理数字孪生仿真智能体。请把任务目标拆解为可执行的仿真实验步骤，"
            "明确轿厢参数、选用工具与评价指标，输出简洁中文。"
        )
        user = (
            f"任务目标：{goal}\n"
            f"可调用工具：run_simulation / grid_snapshot / optimize_social_distance\n请给出任务拆解。"
        )
    else:
        system = (
            "你是 Agnes，密闭空间治理数字孪生仿真智能体。请根据仿真指标，判断交流行为是否压缩了"
            "社交距离，并输出治理策略建议，输出简洁中文。"
        )
        user = f"仿真指标：\n{json.dumps(metrics, ensure_ascii=False, indent=2)}"

    text = agnes_client.chat(system, user).strip()
    if not text:
        return jsonify({"error": "Agnes 调用失败，请检查 Key 与网络"}), 502
    return jsonify({"text": text, "model": agnes_client.MODEL})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"电梯数字孪生 Web 前端已启动：http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

