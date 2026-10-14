# -*- coding: utf-8 -*-
"""真实浏览器端到端验证（Playwright + Chromium）。

三个场景，页面完全相同（templates/index.html）：
  A. 纯静态托管（等同 Netlify）：python -m http.server 起静态站点，/api/* 返回 404 HTML
     → 页面必须自动降级到浏览器内置引擎，点「运行仿真 / 批量实验」都要出图出表。
  B. 同域 Flask（等同 Render 一体化）：页面必须识别到 Python 后端引擎。
  C. 跨域（Netlify 前端 + Render 后端）：静态页 + ?api=Flask 地址，走 CORS。

判定口径：
  1) 三种场景下 DOM 里显示的关键指标文本、批量实验表格必须**逐字相同**；
  2) DOM 里的数值必须与 Python 后端（Flask 测试客户端）返回的数值逐位一致；
  3) 页面无 JS 报错、无未捕获异常。

截图默认**关闭**（不往仓库里写自动生成的图片）；确需留图时显式加 --shot：
    python docs/offline_parity/e2e_page.py --shot
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOT = "--shot" in sys.argv          # 只有显式加 --shot 才截图
HERE = Path(__file__).resolve().parent     # docs/offline_parity/
ROOT = HERE.parents[1]                      # 仓库根目录
sys.path.insert(0, str(ROOT))

STATIC_PORT = 8765
FLASK_PORT = 5051
STATIC_URL = f"http://127.0.0.1:{STATIC_PORT}/templates/index.html"
FLASK_URL = f"http://127.0.0.1:{FLASK_PORT}/"

BASIC = dict(width=4, height=4, n_passengers=8, chat_willingness_mean=0.5,
             comfort_distance=1.5, chat_range=1.5, chat_threshold=1.0, steps=30, seed=42)
ENH = dict(width_m=1.6, depth_m=1.4, cell_size=0.4, n_floors=6, board_interval=5,
           max_passengers=6, comfort_distance_m=1.0, chat_willingness_mean=0.5,
           chat_range_m=0.8, chat_threshold=1.0, repulsion_strength=1.0,
           attraction_strength=0.5, steps=30, seed=42)
SWEEP = dict(steps=30, seed=42)

BASIC_UI = {"width": "#width", "height": "#height", "n_passengers": "#n_passengers",
            "chat_willingness_mean": "#willingness", "comfort_distance": "#comfort_distance",
            "chat_range": "#chat_range", "chat_threshold": "#chat_threshold",
            "steps": "#steps", "seed": "#seed"}
ENH_UI = {"width_m": "#width_m", "depth_m": "#depth_m", "cell_size": "#cell_size",
          "n_floors": "#n_floors", "board_interval": "#board_interval",
          "max_passengers": "#max_passengers", "comfort_distance_m": "#comfort_distance_m",
          "chat_willingness_mean": "#willingness2", "chat_range_m": "#chat_range_m",
          "chat_threshold": "#chat_threshold2", "repulsion_strength": "#repulsion_strength",
          "attraction_strength": "#attraction_strength", "steps": "#steps", "seed": "#seed"}

results: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    results.append((bool(ok), msg))
    print(("  [PASS] " if ok else "  [FAIL] ") + msg)


# ---------------------------------------------------------------- Python 基准
def python_baseline() -> dict:
    from webapp import app  # 本地 Flask 应用（测试客户端，无需起服务）

    c = app.test_client()
    return {
        "basic": c.post("/api/simulate", json=BASIC).get_json(),
        "enhanced": c.post("/api/simulate_enhanced", json=ENH).get_json(),
        "sweep": c.post("/api/sweep", json=SWEEP).get_json(),
    }


# ---------------------------------------------------------------- 页面操作
# ---------------------------------------------------------------- 比较工具
# 表格里 3 与 3.0 只是 Python/JS 的数字转字符串差异（数值等价），按数值比较。
def cells_same(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if str(x).strip() == str(y).strip():
            continue
        try:
            if float(x) == float(y):
                continue
        except ValueError:
            pass
        return False
    return True


def rows_same(a: list, b: list) -> bool:
    return len(a) == len(b) and all(cells_same(x, y) for x, y in zip(a, b))


def set_inputs(page, mapping: dict, params: dict) -> None:
    page.evaluate(
        """(items) => {
            for(const [sel, val] of items){
                const el = document.querySelector(sel);
                el.value = String(val);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""",
        [[sel, params[k]] for k, sel in mapping.items()],
    )


def dom_metrics(page) -> str:
    page.wait_for_function("() => document.querySelectorAll('#metrics .metric').length > 0", timeout=60000)
    return page.inner_text("#metrics").replace("\n", " ").strip()


def dom_sweep_rows(page) -> list:
    page.wait_for_function("() => document.querySelectorAll('#sweep-table table tr').length > 1", timeout=240000)
    return page.eval_on_selector_all(
        "#sweep-table table tr",
        "rows => rows.map(r => Array.from(r.querySelectorAll('th,td')).map(c => c.innerText.trim()))",
    )


def run_scenario(pw, url: str, tag: str, py: dict) -> dict:
    """跑一个页面的完整交互，返回它显示出来的东西。"""
    print(f"\n=== 场景 {tag}：{url} ===")
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 1200})
    page = ctx.new_page()
    js_errors: list = []
    net_notes: list = []
    page.on("pageerror", lambda e: js_errors.append("pageerror: " + str(e)))

    def _on_console(m):
        if m.type != "error":
            return
        if "Failed to load resource" in m.text:      # 静态托管下探测 /api/* 必然 404，属预期
            net_notes.append(m.text)
        else:
            js_errors.append("console.error: " + m.text)

    page.on("console", _on_console)

    page.goto(url, wait_until="load")
    page.wait_for_function("() => !!document.getElementById('engine-badge').textContent", timeout=30000)
    badge = page.inner_text("#engine-badge").strip()
    note = page.inner_text("#engine-note").strip()
    print(f"  引擎徽章：{badge}\n  说明：{note}")
    bound = page.evaluate("() => typeof document.getElementById('btn-run').onclick")
    print(f"  「运行仿真」按钮已绑定事件：{bound}")

    # --- 基础版 ---
    set_inputs(page, BASIC_UI, BASIC)
    got = page.evaluate("() => JSON.stringify(jsBasicParams(readParams()))")
    check(json.loads(got) == BASIC, f"{tag} 基础版 UI 参数原样传入引擎：{got}")
    page.click("#btn-run")
    basic_dom = dom_metrics(page)
    check("error" not in basic_dom.lower(), f"{tag} 基础版运行无错误：{basic_dom}")
    check(page.inner_text("#frame-label").strip().endswith("30 步"),
          f"{tag} 基础版帧数正确：{page.inner_text('#frame-label').strip()}")
    check((page.get_attribute("#curve-img", "src") or "").startswith("data:image/png"),
          f"{tag} 基础版曲线图为 PNG dataURL")
    grid_info = page.evaluate("""() => {
        const cells = Array.from(document.querySelectorAll('#grid .cell'));
        return {total: cells.length,
                people: cells.filter(c => c.textContent === 'P' || c.textContent === 'C').length,
                colors: new Set(cells.map(c => c.style.background)).size};
    }""")
    check(grid_info["total"] == 16 and grid_info["people"] == 8 and grid_info["colors"] >= 2,
          f"{tag} 基础版网格已绘制：{grid_info}（4×4 格 / 8 人 / 多档热度色）")
    js_basic = page.evaluate("() => JSON.stringify(jsLocalSimulate(%s).metrics)" % json.dumps(BASIC))
    check(json.loads(js_basic) == py["basic"]["metrics"],
          f"{tag} 内置引擎基础版指标 == Python 后端：{js_basic}")

    # --- 增强版 ---
    page.click("#tab-enhanced")
    page.wait_for_selector("#params-enhanced:not(.hidden)", timeout=10000)
    set_inputs(page, ENH_UI, ENH)
    got_enh = page.evaluate("() => JSON.stringify(jsEnhancedParams(readParams()))")
    check(json.loads(got_enh) == ENH, f"{tag} 增强版 UI 参数原样传入引擎：{got_enh}")
    page.click("#btn-run")
    enh_dom = dom_metrics(page)
    check("error" not in enh_dom.lower(), f"{tag} 增强版运行无错误：{enh_dom}")
    check("层" in page.inner_text("#floor-info"), f"{tag} 增强版楼层信息：{page.inner_text('#floor-info').strip()}")
    grid_info_e = page.evaluate("""() => {
        const cells = Array.from(document.querySelectorAll('#grid .cell'));
        return {total: cells.length,
                people: cells.filter(c => c.textContent === 'P' || c.textContent === 'C').length};
    }""")
    check(grid_info_e["total"] == 12 and grid_info_e["people"] == 6,
          f"{tag} 增强版网格已绘制：{grid_info_e}（4×3 格 / 6 人）")
    js_enh = page.evaluate("() => JSON.stringify(jsLocalSimulateEnhanced(%s).metrics)" % json.dumps(ENH))
    check(json.loads(js_enh) == py["enhanced"]["metrics"],
          f"{tag} 内置引擎增强版指标 == Python 后端：{js_enh}")

    # --- 批量实验 ---
    page.click("#tab-basic")
    set_inputs(page, {"steps": "#steps", "seed": "#seed"}, SWEEP)
    page.click("#btn-sweep")
    rows = dom_sweep_rows(page)
    py_rows = [["乘客数", "交流意愿", "平均最近邻距离", "社交距离违规率", "交流对数"]] + [
        [str(r["乘客数"]), str(r["交流意愿"]), str(r["平均最近邻距离"]),
         str(r["社交距离违规率"]), str(r["交流对数"])] for r in py["sweep"]["table"]
    ]
    check(rows_same(rows, py_rows), f"{tag} 批量实验表 == Python 后端（{len(rows) - 1} 行）")
    if not rows_same(rows, py_rows):
        for x, y in zip(rows, py_rows):
            if not cells_same(x, y):
                print(f"     浏览器 {x}\n     后端   {y}")
    check((page.get_attribute("#sweep-plot", "src") or "").startswith("data:image/png"),
          f"{tag} 批量实验对比图为 PNG dataURL")
    js_sweep = page.evaluate("() => JSON.stringify(jsLocalSweep(%s).table)" % json.dumps(SWEEP))
    check(json.loads(js_sweep) == py["sweep"]["table"],
          f"{tag} 内置引擎批量表 == Python 后端（15 行逐字段）")

    # --- 引擎状态面板 ---
    page.click("#btn-api-check")
    page.wait_for_timeout(1500)
    check(len(page.inner_text("#engine-note").strip()) > 0,
          f"{tag} 「检测后端」按钮可用，提示：{page.inner_text('#engine-note').strip()[:50]}…")
    check(not js_errors, f"{tag} 无 JS 报错（{len(js_errors)} 条）" + ("" if not js_errors else f"：{js_errors[:3]}"))
    print(f"  （探测后端产生的网络 404 共 {len(net_notes)} 条，属静态托管下的预期行为）")

    # 截图：默认不出图（避免往仓库里塞自动生成的图片），需要时显式加 --shot
    if SHOT:
        shot = HERE / f"_e2e_{tag}.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"  截图：{shot}")
    else:
        print("  （未截图；如需出图请加 --shot）")
    browser.close()
    return {"badge": badge, "basic_dom": basic_dom, "enh_dom": enh_dom, "rows": rows, "net_notes": net_notes}


def wait_ok(url: str, timeout=90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status == 200
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    print("== 先取 Python 后端基准（Flask 测试客户端，无需起服务）==")
    py = python_baseline()
    print("  基础版指标:", py["basic"]["metrics"])
    print("  增强版指标:", py["enhanced"]["metrics"])
    print("  批量表行数:", len(py["sweep"]["table"]))

    static = subprocess.Popen([sys.executable, "-m", "http.server", str(STATIC_PORT),
                               "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    flask = subprocess.Popen([sys.executable, "webapp.py"], cwd=str(ROOT),
                             env={**os.environ, "PORT": str(FLASK_PORT)},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        check(wait_ok(f"http://127.0.0.1:{STATIC_PORT}/templates/index.html"), "静态站点已启动（等同 Netlify）")
        check(wait_ok(f"http://127.0.0.1:{FLASK_PORT}/api/health"), "Flask 后端已启动（等同 Render）")

        with sync_playwright() as pw:
            a = run_scenario(pw, STATIC_URL, "static-netlify", py)
            check(a["badge"] == "浏览器内置引擎（离线）", f"纯静态托管自动降级到内置引擎：{a['badge']}")
            b = run_scenario(pw, FLASK_URL, "flask-render", py)
            check(b["badge"] == "Python 后端引擎", f"同域 Flask 识别到后端引擎：{b['badge']}")
            c = run_scenario(pw, f"{STATIC_URL}?api=http://127.0.0.1:{FLASK_PORT}", "cross-origin", py)
            check(c["badge"] == "Python 后端引擎", f"跨域 ?api= 直连后端引擎：{c['badge']}")

        print("\n== 三场景显示文本互相比对 ==")
        check(a["basic_dom"] == b["basic_dom"] == c["basic_dom"], "基础版指标文本三场景完全一致")
        print(f"      {a['basic_dom']}")
        check(a["enh_dom"] == b["enh_dom"] == c["enh_dom"], "增强版指标文本三场景完全一致")
        print(f"      {a['enh_dom']}")
        check(a["rows"] == b["rows"] == c["rows"], "批量实验表三场景完全一致（逐字）")
        check(len(a["net_notes"]) <= 2, f"静态托管下探测后端的 404 只有 {len(a['net_notes'])} 条（有限次探测）")
    finally:
        for p in (flask, static):
            p.terminate()
            try:
                p.wait(timeout=10)
            except Exception:
                p.kill()

    bad = [m for ok, m in results if not ok]
    print(f"\n===== 端到端验证：{len(results) - len(bad)}/{len(results)} 项通过 =====")
    for m in bad:
        print("  未通过：" + m)
    print("全部通过 ✅" if not bad else "存在未通过项 ❌")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
