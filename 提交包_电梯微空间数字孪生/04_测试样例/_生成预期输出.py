#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
【作者工具】由 输入样例/*.json 真实运行生成 预期输出/*.json

评审无需运行本脚本（预期输出已随包提供）；
如需在其它环境重建基线，请在 01_代码 依赖已安装后执行：
    python 04_测试样例/_生成预期输出.py
"""
from __future__ import annotations

import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_DIR = HERE.parent / "01_代码"
IN_DIR = HERE / "输入样例"
OUT_DIR = HERE / "预期输出"

sys.path.insert(0, str(CODE_DIR))

from elevator_twin.model import ElevatorModel          # noqa: E402
from elevator_twin.model_enhanced import EnhancedElevatorModel  # noqa: E402
from elevator_twin.run import sweep                    # noqa: E402

TOL = 0.05
ENV = (
    f"Python {platform.python_version()} / mesa {version('mesa')} / "
    f"numpy {version('numpy')} / pandas {version('pandas')} / "
    f"matplotlib {version('matplotlib')}"
)
FILES = {
    "N1": "N1_基础_正常",
    "N2": "N2_批量_正常",
    "N3": "N3_增强版_正常",
    "B1": "B1_满载边界",
    "B2": "B2_零意愿边界",
    "B3": "B3_单人边界",
    "F1": "F1_容量超限",
    "F2": "F2_非法人数",
}
BASE_KEYS = ("avg_nearest_distance", "min_nearest_distance", "violation_rate",
             "chat_pairs", "chat_pair_distance")
ENH_KEYS = ("avg_nearest_distance_m", "min_nearest_distance_m", "violation_rate",
            "chat_pairs", "current_passengers", "current_floor")


def load(sid):
    return json.loads((IN_DIR / f"{FILES[sid]}.json").read_text(encoding="utf-8"))


def dump(sid, obj):
    obj["generated_by"] = ENV
    obj["tolerance"] = TOL
    path = OUT_DIR / f"{FILES[sid]}.json"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written:", path.name)


def base_model(p):
    return ElevatorModel(
        width=p["width"], height=p["height"], n_passengers=p["n_passengers"],
        comfort_distance=p["comfort_distance"],
        chat_willingness_mean=p["chat_willingness_mean"],
        chat_range=p["chat_range"], chat_threshold=p["chat_threshold"],
        seed=p["seed"],
    )


def read_metrics(model, keys):
    final = model.datacollector.get_model_vars_dataframe().iloc[-1]
    return {k: round(float(final[k]), 4) for k in keys}


def run_base(sid):
    p = load(sid)["params"]
    model = base_model(p)
    series = []
    for _ in range(p["steps"]):
        model.step()
        series.append(read_metrics(model, BASE_KEYS))
    return model, series


def gen_N1():
    model, series = run_base("N1")
    dump("N1", {
        "id": "N1",
        "kind": "base_single",
        "metrics": series[-1],
        "snapshot": model.grid_snapshot(),
        "note": "seed=42 决定论仿真：末态指标 + 空间快照（P=普通乘客, C=交流中, .=空位）。",
    })


def gen_N2():
    p = load("N2")["params"]
    table = sweep(steps=p["steps"], seed=p["seed"], verbose=False)
    rows = []
    for r in table.to_dict(orient="records"):
        rows.append({
            "乘客数": int(r["乘客数"]),
            "交流意愿": float(r["交流意愿"]),
            "平均最近邻距离": round(float(r["平均最近邻距离"]), 4),
            "社交距离违规率": round(float(r["社交距离违规率"]), 4),
            "交流对数": int(r["交流对数"]),
        })
    dump("N2", {
        "id": "N2",
        "kind": "base_sweep",
        "rows": rows,
        "note": "15 组（乘客数 4/6/8/10/12 × 交流意愿 0.2/0.5/0.8）末态指标对比表。",
    })


def gen_N3():
    p = load("N3")["params"]
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
    for _ in range(p["steps"]):
        model.step()
    dump("N3", {
        "id": "N3",
        "kind": "enhanced_single",
        "metrics": read_metrics(model, ENH_KEYS),
        "grid_size": [model.width, model.height],
        "cell_size_m": model.cell_size,
        "note": "米制指标：真实尺寸下平均最近邻距离远小于 1.0m 标准社交距离（违规率恒为 1.0）。",
    })


def gen_B1():
    model, series = run_base("B1")
    dump("B1", {
        "id": "B1",
        "kind": "base_single",
        "metrics": series[-1],
        "agents": len(model.schedule.agents),
        "empty_cells": len(model.empty_cells()),
        "note": "满载边界：无空闲格 → 乘客保持原位；人数恒为 16。",
    })


def gen_B2():
    model, series = run_base("B2")
    dump("B2", {
        "id": "B2",
        "kind": "base_single",
        "metrics": series[-1],
        "chat_pairs_series": [int(s["chat_pairs"]) for s in series],
        "note": "零意愿边界：每一步的交流对数都应为 0。",
    })


def gen_B3():
    model, series = run_base("B3")
    dump("B3", {
        "id": "B3",
        "kind": "base_single",
        "metrics": series[-1],
        "note": "单人边界：无最近邻 → 各指标为 0 且不报错/不出现 NaN。",
    })


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("环境：", ENV)
    gen_N1()
    gen_N2()
    gen_N3()
    gen_B1()
    gen_B2()
    gen_B3()
    print("完成。")
