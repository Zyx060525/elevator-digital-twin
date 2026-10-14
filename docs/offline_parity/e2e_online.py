# -*- coding: utf-8 -*-
"""线上真实页面端到端冒烟：Netlify 纯静态站点（无后端）能否点得动、跑得出图。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://elevator-digital-twin.netlify.app/"
BASIC_TXT = "📏 1.104格 平均最近邻距离 📐 1格 最小最近邻距离 ⚠️ 100.0% 社交距离违规率 💬 3 交流对数 ↔️ 1格 交流对平均距离"
ENH_TXT = "📏 0.533m 平均最近邻距离 📐 0.4m 最小最近邻距离 ⚠️ 100.0% 社交距离违规率 💬 2 交流对数 👥 6人 当前乘客数 🏢 6层 当前楼层"
results = []


def check(ok, msg):
    results.append((bool(ok), msg))
    print(("  [PASS] " if ok else "  [FAIL] ") + msg)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_context(viewport={"width": 1600, "height": 1200}).new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    page.goto(URL, wait_until="load")
    page.wait_for_function("() => document.getElementById('engine-badge').textContent.length > 0", timeout=40000)
    page.wait_for_function("() => document.getElementById('engine-badge').textContent.indexOf('检测中') < 0", timeout=30000)
    badge = page.inner_text("#engine-badge").strip()
    check(badge == "浏览器内置引擎（离线）", f"线上页面引擎徽章：{badge}")
    check(page.evaluate("() => typeof document.getElementById('btn-run').onclick") == "function",
          "线上页面「运行仿真」按钮已绑定事件")

    page.click("#btn-run")
    page.wait_for_function("() => document.querySelectorAll('#metrics .metric').length > 0", timeout=60000)
    txt = page.inner_text("#metrics").replace("\n", " ").strip()
    check(txt == BASIC_TXT, f"基础版点一下就出结果：{txt}")
    info = page.evaluate("""() => {
        const c = Array.from(document.querySelectorAll('#grid .cell'));
        return {total: c.length, people: c.filter(x => x.textContent === 'P' || x.textContent === 'C').length};
    }""")
    check(info["total"] == 16 and info["people"] == 8, f"基础版网格已绘制：{info}")
    check((page.get_attribute("#curve-img", "src") or "").startswith("data:image/png"), "基础版曲线图已出图")
    check((page.get_attribute("#frame-label", "text") or page.inner_text("#frame-label")).strip() == "第 30 步",
          "基础版帧数标签：第 30 步")

    page.click("#tab-enhanced")
    page.click("#btn-run")
    page.wait_for_function("() => document.querySelectorAll('#metrics .metric').length === 6", timeout=60000)
    txt2 = page.inner_text("#metrics").replace("\n", " ").strip()
    check(txt2 == ENH_TXT, f"增强版点一下就出结果：{txt2}")

    page.click("#tab-basic")
    page.click("#btn-sweep")
    page.wait_for_function("() => document.querySelectorAll('#sweep-table table tr').length > 1", timeout=240000)
    rows = page.eval_on_selector_all("#sweep-table table tr", "r => r.length")
    check(rows == 16, f"批量实验表已出（{rows - 1} 行数据）")
    check(not errs, f"线上页面无 JS 报错（{len(errs)} 条）")

    page.screenshot(path=str(Path(__file__).resolve().parent / "live_netlify.png"), full_page=True)
    browser.close()

bad = [m for ok, m in results if not ok]
print(f"\n===== 线上站点冒烟：{len(results) - len(bad)}/{len(results)} 项通过 =====")
print("全部通过 ✅" if not bad else "未通过：" + str(bad))
