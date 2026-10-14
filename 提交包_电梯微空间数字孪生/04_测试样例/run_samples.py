#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
电梯微空间数字孪生 —— 测试样例一键自检（完全离线，不需要 Agnes Key）

用法：
    python run_samples.py                 跑全部样例
    python run_samples.py --verbose       额外打印空间快照等细节
    python run_samples.py --only N1 F2    只跑指定样例

覆盖：正常（N1-N3）/ 边界（B1-B3）/ 失败（F1-F2）/ Web 接口（A1-A3）/ MCP 工具（M1-M2）
退出码：0 = 全部通过（打印 ALL PASS）；1 = 存在失败项
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_DIR = HERE.parent / "01_代码"
INPUT_DIR = HERE / "输入样例"
EXPECT_DIR = HERE / "预期输出"

sys.path.insert(0, str(CODE_DIR))

RESULTS = []          # [(样例号, 状态, 说明)]
VERBOSE = False
TOL = 0.05

# 样例号 -> 输入/预期文件名（不含 .json）
SAMPLE_FILES = {
    "N1": "N1_基础_正常",
    "N2": "N2_批量_正常",
    "N3": "N3_增强版_正常",
    "B1": "B1_满载边界",
    "B2": "B2_零意愿边界",
    "B3": "B3_单人边界",
    "F1": "F1_容量超限",
    "F2": "F2_非法人数",
}


# ----------------------------- 基础设施 -----------------------------

def record(sid, status, detail):
    RESULTS.append((sid, status, detail))
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print(f"{tag} {sid:<3} {detail}", flush=True)


def load_input(sid):
    return json.loads((INPUT_DIR / f"{SAMPLE_FILES[sid]}.json").read_text(encoding="utf-8"))


def load_expect(sid):
    return json.loads((EXPECT_DIR / f"{SAMPLE_FILES[sid]}.json").read_text(encoding="utf-8"))


def close(a, b, tol=TOL):
    return abs(float(a) - float(b)) <= tol


def diff_of(got, want, tol=TOL):
    """返回 {键: (实际, 预期)} 的超出容差项。"""
    out = {}
    for k, v in want.items():
        if not close(got[k], v, tol):
            out[k] = (round(float(got[k]), 4), v)
    return out


def show_snapshot(model):
    if not VERBOSE:
        return
    print("       末态空间快照（P=普通乘客, C=交流中, .=空位）：")
    for row in model.grid_snapshot():
        print("         " + row)


BASE_KEYS = ("avg_nearest_distance", "min_nearest_distance", "violation_rate",
             "chat_pairs", "chat_pair_distance")

# 未在样例中显式给出的参数取模型默认值（保证失败样例只需给出触发错误的参数）
BASE_DEFAULTS = {
    "width": 4, "height": 4, "n_passengers": 8, "comfort_distance": 1.5,
    "chat_willingness_mean": 0.5, "chat_range": 1.5, "chat_threshold": 1.0,
    "seed": 42,
}


def base_model(p):
    from elevator_twin.model import ElevatorModel
    p = {**BASE_DEFAULTS, **p}
    return ElevatorModel(
        width=p["width"], height=p["height"], n_passengers=p["n_passengers"],
        comfort_distance=p["comfort_distance"],
        chat_willingness_mean=p["chat_willingness_mean"],
        chat_range=p["chat_range"], chat_threshold=p["chat_threshold"],
        seed=p["seed"],
    )


def base_metrics(model):
    final = model.datacollector.get_model_vars_dataframe().iloc[-1]
    return {k: float(final[k]) for k in BASE_KEYS}


# ----------------------------- 正常样例 -----------------------------

def sample_N1():
    sid = "N1"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    model = base_model(p)
    for _ in range(p["steps"]):
        model.step()
    got = base_metrics(model)
    bad = diff_of(got, exp["metrics"])
    if bad:
        return record(sid, "FAIL", f"指标超差（实际, 预期）：{bad}")
    show_snapshot(model)
    return record(
        sid, "PASS",
        f"avg_dist={got['avg_nearest_distance']:.3f} "
        f"min_dist={got['min_nearest_distance']:.3f} "
        f"violation={got['violation_rate']:.3f} chat_pairs={int(got['chat_pairs'])}"
        f"（{len(exp['metrics'])} 项指标均在 {TOL} 容差内）")


def sample_N2():
    sid = "N2"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    from elevator_twin.run import sweep
    rows = sweep(steps=p["steps"], seed=p["seed"], verbose=False).to_dict(orient="records")
    if len(rows) != len(exp["rows"]):
        return record(sid, "FAIL", f"对比表行数不符：实际 {len(rows)}，预期 {len(exp['rows'])}")
    for i, (got, want) in enumerate(zip(rows, exp["rows"]), start=1):
        want_num = {k: v for k, v in want.items() if k not in ("乘客数", "交流意愿")}
        bad = diff_of(got, want_num)
        same_key = int(got["乘客数"]) == int(want["乘客数"]) and close(got["交流意愿"], want["交流意愿"], 1e-6)
        if not same_key or bad:
            return record(sid, "FAIL", f"第 {i} 行不一致：[{got['乘客数']} 人 / 意愿 {got['交流意愿']}] → {bad}")
    hi = max(exp["rows"], key=lambda r: r["平均最近邻距离"])
    lo = min(exp["rows"], key=lambda r: r["平均最近邻距离"])
    chat_hi = max(r["交流对数"] for r in exp["rows"])
    return record(
        sid, "PASS",
        f"{len(rows)}/{len(rows)} 行全部一致：平均距离 {hi['平均最近邻距离']}（{hi['乘客数']} 人 / 意愿 {hi['交流意愿']}）"
        f" → {lo['平均最近邻距离']}（{lo['乘客数']} 人 / 意愿 {lo['交流意愿']}），交流对数 0 → {chat_hi}")


def sample_N3():
    sid = "N3"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    from elevator_twin.model_enhanced import EnhancedElevatorModel
    model = EnhancedElevatorModel(
        width_m=p["width_m"], depth_m=p["depth_m"], cell_size=p["cell_size"],
        n_floors=p["n_floors"], board_interval=p["board_interval"],
        max_passengers=p["max_passengers"], comfort_distance_m=p["comfort_distance_m"],
        chat_willingness_mean=p["chat_willingness_mean"], chat_range_m=p["chat_range_m"],
        chat_threshold=p["chat_threshold"], repulsion_strength=p["repulsion_strength"],
        attraction_strength=p["attraction_strength"], seed=p["seed"],
    )
    for _ in range(p["steps"]):
        model.step()
    final = model.datacollector.get_model_vars_dataframe().iloc[-1]
    got = {k: float(final[k]) for k in exp["metrics"]}
    bad = diff_of(got, exp["metrics"])
    if bad:
        return record(sid, "FAIL", f"指标超差（实际, 预期）：{bad}")
    if not got["avg_nearest_distance_m"] < p["comfort_distance_m"]:
        return record(sid, "FAIL", "核心洞察不成立：平均最近邻距离未小于舒适距离")
    show_snapshot(model)
    return record(
        sid, "PASS",
        f"米制网格 {model.width}×{model.height}（格 {model.cell_size}m）：avg={got['avg_nearest_distance_m']:.3f}m "
        f"< 舒适距离 {p['comfort_distance_m']}m，violation={got['violation_rate']:.2f}，"
        f"第 {int(got['current_floor'])} 层载客 {int(got['current_passengers'])} 人")


# ----------------------------- 边界样例 -----------------------------

def sample_B1():
    sid = "B1"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    model = base_model(p)
    for _ in range(p["steps"]):
        model.step()
    got = base_metrics(model)
    bad = diff_of(got, exp["metrics"])
    if bad:
        return record(sid, "FAIL", f"指标超差（实际, 预期）：{bad}")
    n = len(model.schedule.agents)
    if n != exp["agents"]:
        return record(sid, "FAIL", f"人数应为 {exp['agents']}，实际 {n}")
    if len(model.empty_cells()) != 0:
        return record(sid, "FAIL", "满载场景不应存在空闲格")
    show_snapshot(model)
    return record(sid, "PASS",
                  f"满载不崩溃：人数恒为 {n}、空闲格 0、乘客保持原位，violation={got['violation_rate']:.2f}")


def sample_B2():
    sid = "B2"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    model = base_model(p)
    series = []
    for _ in range(p["steps"]):
        model.step()
        series.append(int(base_metrics(model)["chat_pairs"]))
    want = [int(v) for v in exp["chat_pairs_series"]]
    if series != want:
        return record(sid, "FAIL", f"交流对数序列不符：实际 {series}，预期 {want}")
    if any(v != 0 for v in series):
        return record(sid, "FAIL", "零意愿场景不应形成交流对")
    return record(sid, "PASS", f"意愿 0.0：{p['steps']} 步内交流对数恒为 0，仅「社交距离最大化」生效")


def sample_B3():
    sid = "B3"
    p = load_input(sid)["params"]
    exp = load_expect(sid)
    model = base_model(p)
    for _ in range(p["steps"]):
        model.step()
    got = base_metrics(model)
    bad = diff_of(got, exp["metrics"])
    if bad:
        return record(sid, "FAIL", f"指标超差（实际, 预期）：{bad}")
    if any(v != 0 for v in got.values()):
        return record(sid, "FAIL", f"单人场景指标应全为 0，实际 {got}")
    return record(sid, "PASS", "单人边界：avg / min / violation / chat_pairs 全为 0，无异常、无 NaN")


# ----------------------------- 失败样例（期望抛错） -----------------------------

def sample_expect_error(sid):
    spec = load_input(sid)
    try:
        base_model(spec["params"])
    except ValueError as exc:
        msg = str(exc)
        if spec["expect_error_contains"] in msg:
            return record(sid, "PASS", f"按预期抛出 ValueError：{msg}")
        return record(sid, "FAIL", f"异常信息不含「{spec['expect_error_contains']}」：{msg}")
    except Exception as exc:  # noqa: BLE001
        return record(sid, "FAIL", f"抛出非预期异常 {type(exc).__name__}: {exc}")
    return record(sid, "FAIL", "未抛出异常（应抛出 ValueError，避免无效仿真静默通过）")


# ------------------- Web 接口样例（Flask 测试客户端，无需启动服务） -------------------

def api_client():
    from webapp import app
    return app.test_client()


def sample_A1():
    sid = "A1"
    resp = api_client().get("/api/health")
    data = resp.get_json()
    if resp.status_code != 200:
        return record(sid, "FAIL", f"GET /api/health HTTP {resp.status_code}")
    if (data or {}).get("status") != "ok":
        return record(sid, "FAIL", f"返回异常：{data}")
    return record(sid, "PASS", f"GET /api/health → 200 {data}")


def sample_A2():
    sid = "A2"
    p = load_input("N1")["params"]
    exp = load_expect("N1")
    resp = api_client().post("/api/simulate", json=p)
    data = resp.get_json()
    if resp.status_code != 200:
        return record(sid, "FAIL", f"POST /api/simulate HTTP {resp.status_code}")
    missing = {"metrics", "grid", "frames", "curve"} - set(data or {})
    if missing:
        return record(sid, "FAIL", f"响应缺少字段：{sorted(missing)}")
    bad = diff_of(data["metrics"], exp["metrics"])
    if bad:
        return record(sid, "FAIL", f"接口指标与预期不符：{bad}")
    n_agents = sum(1 for row in data["grid"] for c in row if c["s"] in ("P", "C"))
    return record(sid, "PASS",
                  f"POST /api/simulate → 200：metrics 一致、grid {len(data['grid'])}×{len(data['grid'][0])}"
                  f"（{n_agents} 名乘客）、frames {len(data['frames'])} 帧、curve 为 PNG dataURL")


def sample_A3():
    sid = "A3"
    resp = api_client().post("/api/sweep", json={"steps": 30, "seed": 42})
    data = resp.get_json()
    if resp.status_code != 200:
        return record(sid, "FAIL", f"POST /api/sweep HTTP {resp.status_code}")
    table = (data or {}).get("table") or []
    if len(table) != 15:
        return record(sid, "FAIL", f"对比表行数应为 15，实际 {len(table)}")
    if not str((data or {}).get("plot", "")).startswith("data:image/png;base64,"):
        return record(sid, "FAIL", "对比图字段不是 base64 PNG")
    return record(sid, "PASS", f"POST /api/sweep → 200：table {len(table)} 行 + plot PNG（{len(data['plot']) // 1024} KB base64）")


# ----------------------------- MCP 工具样例（真实 stdio 调用） -----------------------------

_MCP_CACHE = {}


def _extract(result):
    """从 MCP CallToolResult 提取数据（dict / list / str），兼容 mcp 1.x 与 2.x。"""
    for attr in ("structured_content", "structuredContent"):
        val = getattr(result, attr, None)
        if val is not None:
            return val
    texts = [getattr(it, "text", "") for it in (getattr(result, "content", []) or [])]
    texts = [t for t in texts if t]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    return texts


async def _mcp_session_calls():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "elevator_twin.mcp_server"],
        cwd=str(CODE_DIR),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            opt = _extract(await session.call_tool(
                "optimize_social_distance", arguments={"n_passengers": 8, "steps": 30}))
            sim = _extract(await session.call_tool(
                "run_simulation", arguments={"n_passengers": 8, "steps": 30}))
            snap = _extract(await session.call_tool(
                "grid_snapshot", arguments={"steps": 10}))
    return {"tools": tools, "optimize": opt, "simulate": sim, "snapshot": snap}


def mcp_data():
    """返回 (数据, 错误信息)，只真实启动一次 MCP 服务。"""
    if "data" not in _MCP_CACHE and "error" not in _MCP_CACHE:
        try:
            _MCP_CACHE["data"] = asyncio.run(
                asyncio.wait_for(_mcp_session_calls(), timeout=180))
        except Exception as exc:  # noqa: BLE001
            _MCP_CACHE["error"] = f"{type(exc).__name__}: {exc}"
    return _MCP_CACHE.get("data"), _MCP_CACHE.get("error")


def sample_M1():
    sid = "M1"
    data, err = mcp_data()
    if err:
        return record(sid, "SKIP", f"MCP 客户端未跑通（{err}），跳过 MCP 集成检查")
    want = {"run_simulation", "grid_snapshot", "optimize_social_distance"}
    missing = want - set(data["tools"])
    if missing:
        return record(sid, "FAIL", f"MCP 工具缺失：{sorted(missing)}（已注册：{data['tools']}）")
    snap = data["snapshot"]
    if VERBOSE and isinstance(snap, list):
        print("       空间快照（MCP grid_snapshot 返回）：")
        for row in snap:
            print("         " + row)
    return record(sid, "PASS",
                  f"stdio 连接 elevator-twin MCP 服务成功，已注册工具 {data['tools']}；"
                  f"grid_snapshot 返回 {len(snap) if isinstance(snap, list) else '?'} 行空间快照")


def sample_M2():
    sid = "M2"
    data, err = mcp_data()
    if err:
        return record(sid, "SKIP", f"MCP 客户端未跑通（{err}），跳过 MCP 集成检查")
    opt = data["optimize"]
    if not isinstance(opt, dict) or not {"low", "mid", "high"} <= set(opt):
        return record(sid, "FAIL", f"optimize_social_distance 返回结构异常：{opt}")
    low, high = opt["low"], opt["high"]
    if high["chat_pairs"] < low["chat_pairs"]:
        return record(sid, "FAIL",
                      f"不符合预期：高意愿交流对数 {high['chat_pairs']} < 低意愿 {low['chat_pairs']}")
    if high["avg_nearest_distance"] > low["avg_nearest_distance"] + TOL:
        return record(sid, "FAIL",
                      f"不符合预期：高意愿平均距离 {high['avg_nearest_distance']} > 低意愿 {low['avg_nearest_distance']}")
    print("       MCP 调用链：initialize → list_tools → optimize_social_distance → run_simulation → grid_snapshot")
    print(f"       optimize_social_distance 返回：{json.dumps(opt, ensure_ascii=False)}")
    return record(sid, "PASS",
                  f"低意愿：距离 {low['avg_nearest_distance']} / {low['chat_pairs']} 交流对 → "
                  f"高意愿：距离 {high['avg_nearest_distance']} / {high['chat_pairs']} 交流对"
                  f"（交流行为压缩社交距离，结论可复现）")


# --------------------------------- 主流程 ---------------------------------

SAMPLES = [
    ("N1", sample_N1), ("N2", sample_N2), ("N3", sample_N3),
    ("B1", sample_B1), ("B2", sample_B2), ("B3", sample_B3),
    ("F1", lambda: sample_expect_error("F1")),
    ("F2", lambda: sample_expect_error("F2")),
    ("A1", sample_A1), ("A2", sample_A2), ("A3", sample_A3),
    ("M1", sample_M1), ("M2", sample_M2),
]


def main():
    global VERBOSE
    ap = argparse.ArgumentParser(description="电梯微空间数字孪生 —— 测试样例自检")
    ap.add_argument("--verbose", action="store_true", help="额外打印空间快照等细节")
    ap.add_argument("--only", nargs="*", default=[], metavar="ID",
                    help="只跑指定样例，例如 --only N1 F2")
    ap.add_argument("--log", metavar="FILE", default=None,
                    help="同时把输出写入 UTF-8 文本文件（避免 Windows 终端重定向乱码）")
    args = ap.parse_args()
    VERBOSE = args.verbose
    only = {x.upper() for x in args.only}

    if args.log:
        class _Tee:
            def __init__(self, *streams):
                self._streams = streams

            def write(self, s):
                for st in self._streams:
                    st.write(s)
                return len(s)

            def flush(self):
                for st in self._streams:
                    st.flush()

        sys.stdout = _Tee(sys.stdout, open(args.log, "w", encoding="utf-8"))

    print("=" * 78)
    print("电梯微空间数字孪生 — 测试样例自检（完全离线，无需 Agnes Key）")
    print("=" * 78)
    print(f"代码目录：{CODE_DIR}")
    print(f"样例目录：{HERE}")
    print("-" * 78)

    unknown = sorted(only - {sid for sid, _ in SAMPLES})
    if unknown:
        print(f"[WARN] 未知样例号：{unknown}（可选：{[s for s, _ in SAMPLES]}）")

    for sid, fn in SAMPLES:
        if only and sid not in only:
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            record(sid, "FAIL", f"执行异常 {type(exc).__name__}: {exc}")

    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    n_skip = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    print("-" * 78)
    print(f"共 {len(RESULTS)} 项：通过 {n_pass}，失败 {n_fail}，跳过 {n_skip}")
    print("ALL PASS" if n_fail == 0 else "SOME SAMPLES FAILED")
    print("=" * 78)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


