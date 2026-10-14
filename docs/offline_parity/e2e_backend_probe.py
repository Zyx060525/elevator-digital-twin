# -*- coding: utf-8 -*-
"""后端探测 / 冷启动唤醒 / 地址校验 的端到端验证（Playwright + Chromium）。

背景：页面在「Netlify 静态前端 + Render 后端」这种部署下，后端首次访问可能正处在冷启动中
（Render 免费实例要 30~60 秒）。修复前的逻辑只在页面加载时探一次、超时 5 秒、失败就把
apiReady 置为 false，且 callEngine() 里 `apiReady === false` 会直接短路到内置引擎，
于是**再也不会重试** —— 表现为「明明部署了后端，页面却一直显示离线，只能手点重新检测」。

本脚本验证修复后的行为（四个场景，页面都是 templates/index.html）：

  S1 未配置后端（等同纯静态托管）：只探一次、徽章离线、文案说明是纯静态托管、点运行仍能出结果；
  S2 配置了不存在的后端地址：文案给出**具体原因**（无法连接 / 超时）、点「重新检测后端」仍能正确报错；
  S3 冷启动自愈：页面加载时后端还没启动，之后后端启动 → 页面**无需刷新、无需点任何按钮**
     自动切到 Python 后端引擎；随后点「运行仿真」确实打到了 /api/simulate（而不是走内置引擎）；
  S4 地址校验：非法地址与示例占位符都会被拦下并给出提示，不写进 localStorage、不触发刷新。

用法（默认不截图，与 e2e_page.py 保持一致）：
    python docs/offline_parity/e2e_backend_probe.py
    python docs/offline_parity/e2e_backend_probe.py --shot
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOT = "--shot" in sys.argv
HERE = Path(__file__).resolve().parent      # docs/offline_parity/
ROOT = HERE.parents[1]                       # 仓库根目录
sys.path.insert(0, str(ROOT))

STATIC_PORT = 8766
LATE_PORT = 5052                             # 冷启动场景：页面加载后才启动的 Flask
DEAD_PORT = 5099                             # 绝不存在的后端端口

STATIC_URL = f"http://127.0.0.1:{STATIC_PORT}/templates/index.html"
OFFLINE = "浏览器内置引擎（离线）"
PY_ENGINE = "Python 后端引擎"

results: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    results.append((bool(ok), msg))
    print(("  [PASS] " if ok else "  [FAIL] ") + msg)


def wait_ok(url: str, timeout: int = 90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status == 200
        except Exception:
            time.sleep(1)
    return False


class Page:
    """打开一个页面并记录 JS 报错 / 网络请求，供各场景断言。"""

    def __init__(self, pw, url: str, tag: str):
        self.tag = tag
        self.browser = pw.chromium.launch()
        self.ctx = self.browser.new_context(viewport={"width": 1500, "height": 1000})
        self.page = self.ctx.new_page()
        self.js_errors: list[str] = []
        self.health_calls: list[int] = []     # /api/health 的响应状态码
        self.api_calls: list[tuple[str, int]] = []
        self.health_attempts = 0              # 实际发出的 /api/health 次数（含连接被拒的失败请求）
        self.navigations = 0
        self.page.on("pageerror", lambda e: self.js_errors.append("pageerror: " + str(e)))
        self.page.on("console", self._on_console)
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("framenavigated", lambda f: setattr(self, "navigations", self.navigations + 1))
        print(f"\n=== 场景 {tag}：{url} ===")
        self.page.goto(url, wait_until="load")
        self.page.wait_for_function(
            "() => !!document.getElementById('engine-badge').textContent", timeout=30000)

    def _on_console(self, m):
        if m.type != "error":
            return
        if "Failed to load resource" in m.text:
            return                                     # 静态托管下探测 /api/* 必然 404，属预期
        self.js_errors.append("console.error: " + m.text)

    def _on_request(self, r):
        if "/api/health" in r.url:
            self.health_attempts += 1

    def _on_response(self, r):
        url = r.url
        if "/api/" not in url:
            return
        self.api_calls.append((url.split("127.0.0.1")[-1], r.status))
        if "/api/health" in url:
            self.health_calls.append(r.status)

    @property
    def badge(self) -> str:
        return self.page.inner_text("#engine-badge").strip()

    @property
    def note(self) -> str:
        return self.page.inner_text("#engine-note").strip()

    def wait_badge(self, want: str, timeout: int = 30000) -> str:
        try:
            self.page.wait_for_function(
                "() => document.getElementById('engine-badge').textContent.trim() === %s" % repr(want).replace("'", '"'),
                timeout=timeout)
        except Exception:
            pass
        return self.badge

    def run_sim(self) -> str:
        self.page.click("#btn-run")
        self.page.wait_for_function(
            "() => document.querySelectorAll('#metrics .metric').length > 0", timeout=60000)
        return self.page.inner_text("#metrics").replace("\n", " ").strip()

    def close(self, name: str | None = None):
        if SHOT and name:
            shot = HERE / f"_probe_{name}.png"
            self.page.screenshot(path=str(shot), full_page=True)
            print(f"  截图：{shot}")
        self.browser.close()


# ---------------------------------------------------------------- 场景
def scenario_static(pw) -> str:
    """S1：未配置后端（等同纯静态托管）。"""
    p = Page(pw, STATIC_URL, "S1 未配置后端（纯静态托管）")
    p.wait_badge(OFFLINE, 20000)
    check(p.badge == OFFLINE, f"S1 徽章为离线：{p.badge}")
    check("纯静态托管" in p.note, f"S1 文案说明是纯静态托管：{p.note[:70]}…")
    check(len(p.health_calls) == 1, f"S1 只探测 1 次 /api/health（不反复打 404）：{p.health_calls}")
    txt = p.run_sim()
    check("error" not in txt.lower() and len(txt) > 20, f"S1 点运行仍出结果：{txt[:70]}…")
    check((p.page.get_attribute("#curve-img", "src") or "").startswith("data:image/png"),
          "S1 曲线图为 PNG dataURL")
    check(not p.js_errors, f"S1 无 JS 报错（{len(p.js_errors)} 条）")
    p.close("static")
    return txt


def scenario_dead(pw, base_text: str) -> None:
    """S2：配置了一个不存在的后端地址。"""
    url = f"{STATIC_URL}?api=http://127.0.0.1:{DEAD_PORT}"
    p = Page(pw, url, f"S2 后端地址不存在（127.0.0.1:{DEAD_PORT}）")
    p.wait_badge(OFFLINE, 25000)
    check(p.badge == OFFLINE, f"S2 连不上后端时降级到内置引擎：{p.badge}")
    check(("无法连接" in p.note) or ("超时" in p.note), f"S2 文案给出具体原因：{p.note[:120]}…")
    check("纯静态托管" not in p.note, "S2 文案与「未配置后端」区分开")
    p.page.wait_for_timeout(4500)                  # 退避重试窗口：0s / 3s / 9s …
    check(p.health_attempts >= 2, f"S2 探测失败后会退避重试（已发出 {p.health_attempts} 次 /api/health）")
    check(p.badge == OFFLINE, f"S2 重试期间徽章保持离线：{p.badge}")
    txt = p.run_sim()
    check("error" not in txt.lower() and len(txt) > 20, f"S2 后端不可用时仍出结果：{txt[:70]}…")
    check(txt == base_text, "S2 的结果文本与 S1 完全一致（内置引擎口径一致）")
    p.page.click("#btn-api-check")
    p.page.wait_for_timeout(2500)
    check(p.badge == OFFLINE, f"S2 点「重新检测后端」后仍正确报离线：{p.badge}")
    check(("无法连接" in p.note) or ("超时" in p.note), f"S2 重新检测后仍带原因：{p.note[:120]}…")
    check(not p.js_errors, f"S2 无 JS 报错（{len(p.js_errors)} 条）")
    p.close("dead")


def scenario_coldstart(pw, base_text: str) -> None:
    """S3：冷启动自愈 —— 页面加载时后端还没起，之后后端启动，页面应自动切回后端引擎。"""
    url = f"{STATIC_URL}?api=http://127.0.0.1:{LATE_PORT}"
    p = Page(pw, url, f"S3 冷启动自愈（后端稍后才启动：127.0.0.1:{LATE_PORT}）")
    p.wait_badge(OFFLINE, 25000)
    check(p.badge == OFFLINE, f"S3 后端未启动时先是离线：{p.badge}")
    check(("无法连接" in p.note) or ("超时" in p.note), f"S3 文案给出原因：{p.note[:120]}…")

    print(f"  → 现在才启动 Flask 后端（端口 {LATE_PORT}），页面不动、不刷新，看它能否自动恢复")
    flask = subprocess.Popen([sys.executable, "webapp.py"], cwd=str(ROOT),
                             env={**os.environ, "PORT": str(LATE_PORT)},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        check(wait_ok(f"http://127.0.0.1:{LATE_PORT}/api/health", timeout=60),
              f"S3 Flask 后端已启动（端口 {LATE_PORT}）")
        badge = p.wait_badge(PY_ENGINE, 90000)          # 关键：不刷新、不点任何按钮
        check(badge == PY_ENGINE, f"S3 后端起来后页面自动切回 Python 引擎（未刷新、未点按钮）：{badge}")
        check("已连接 Python 后端" in p.note, f"S3 文案说明已连上后端：{p.note[:120]}…")
        txt = p.run_sim()
        used = any(u.endswith("/api/simulate") and s == 200 for u, s in p.api_calls)
        check(used, f"S3 随后的运行确实打到 /api/simulate（HTTP 200）：{p.api_calls[-2:]}")
        check(txt == base_text, "S3 走 Python 后端的结果文本与内置引擎完全一致")
        check(not p.js_errors, f"S3 无 JS 报错（{len(p.js_errors)} 条）")
    finally:
        flask.terminate()
        try:
            flask.wait(timeout=10)
        except Exception:
            flask.kill()
    p.close("coldstart")


def scenario_validate(pw) -> None:
    """S4：后端地址的校验与规范化。"""
    p = Page(pw, STATIC_URL, "S4 后端地址校验 / 规范化")
    p.wait_badge(OFFLINE, 20000)
    n0 = p.navigations

    p.page.fill("#api-input", "xxx.onrender.com")
    p.page.click("#btn-api-save")
    p.page.wait_for_timeout(1200)
    check("示例占位符" in p.note, f"S4 示例占位符被拦下：{p.note[:100]}…")
    check(p.page.evaluate("() => localStorage.getItem('apiBase')") is None,
          "S4 占位符没有写进 localStorage")
    check(p.navigations == n0, "S4 被拦下时不刷新页面（不会静默变离线）")

    p.page.fill("#api-input", "not a url!!")
    p.page.click("#btn-api-save")
    p.page.wait_for_timeout(1200)
    check("格式不对" in p.note, f"S4 非法地址被拦下：{p.note[:100]}…")
    check(p.page.evaluate("() => localStorage.getItem('apiBase')") is None,
          "S4 非法地址没有写进 localStorage")

    cases = [
        ("127.0.0.1:5000", "http://127.0.0.1:5000"),
        ("elevator-digital-twin.onrender.com/", "https://elevator-digital-twin.onrender.com"),
        ("https://a.onrender.com/api/?x=1#y", "https://a.onrender.com/api"),
        ("", ""),
        ("   ", ""),
        ("http://", ""),
    ]
    for raw, want in cases:
        got = p.page.evaluate("(v) => normalizeApiBase(v)", raw)
        check(got == want, f"S4 normalizeApiBase({raw!r}) = {got!r}（期望 {want!r}）")
    check(p.page.evaluate("(v) => apiLooksPlaceholder(v)", "https://xxx.onrender.com") is True,
          "S4 xxx.onrender.com 判定为示例占位符")
    check(p.page.evaluate("(v) => apiLooksPlaceholder(v)",
                          "https://elevator-digital-twin.onrender.com") is False,
          "S4 真实服务地址不会被误判为占位符")
    check(not p.js_errors, f"S4 无 JS 报错（{len(p.js_errors)} 条）")
    p.close("validate")


def main() -> int:
    print("== 起静态站点（等同 Netlify：/api/* 只会 404）==")
    static = subprocess.Popen([sys.executable, "-m", "http.server", str(STATIC_PORT),
                               "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        check(wait_ok(STATIC_URL), f"静态站点已启动：{STATIC_URL}")
        with sync_playwright() as pw:
            base_text = scenario_static(pw)
            scenario_dead(pw, base_text)
            scenario_coldstart(pw, base_text)
            scenario_validate(pw)
    finally:
        static.terminate()
        try:
            static.wait(timeout=10)
        except Exception:
            static.kill()

    bad = [m for ok, m in results if not ok]
    print(f"\n===== 后端探测验证：{len(results) - len(bad)}/{len(results)} 项通过 =====")
    for m in bad:
        print("  未通过：" + m)
    print("全部通过 ✅" if not bad else "存在未通过项 ❌")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())

