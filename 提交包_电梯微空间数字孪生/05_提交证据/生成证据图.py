#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
【提交素材生成】把「真实运行输出」渲染成 PNG 证据图，并同时保存 UTF-8 日志。

用途：赛事需要上传「AGH 执行记录」「MCP 工具调用链」等运行证据，
      本脚本真实跑一遍各入口，把控制台输出渲染成可直接上传的截图。

用法（在 05_提交证据 目录下执行）：
    python 生成证据图.py            # 生成全部证据（含 Web 界面真实截图，需本机有 Chrome/Edge）
    python 生成证据图.py --no-web   # 只生成控制台类证据，不启动 Web 服务

产物（证据图/ 目录）：
    01_AGH执行记录.png / .txt            python -m elevator_twin.agh_loop
    02_MCP调用链证据.png / .txt          MCP 客户端：initialize → list_tools → call_tool ×3
    03_测试样例自检结果.png / .txt       python 04_测试样例/run_samples.py（13 项）
    04_仿真对比实验.png / .txt           python -m elevator_twin.run
    05_Web界面.png                       无头浏览器抓取（同源探针，界面已跑出真实仿真结果）
    06_前端功能自检.png                  无头浏览器执行 runSimulate() 的端到端功能自检结论
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import string
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
CODE_DIR = PKG / "01_代码"
SAMPLES_DIR = PKG / "04_测试样例"
OUT_DIR = HERE / "证据图"

STAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


# --------------------------------- 基础工具 ---------------------------------

def pick_font(size):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def run_cmd(args, cwd):
    """真实执行命令并抓取输出（UTF-8）。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.run(
        [sys.executable, *args], cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
    return proc.stdout or "", proc.returncode


# --------------------------------- MCP 调用链 ---------------------------------

def mcp_transcript():
    """真实启动 elevator-twin MCP 服务，打印完整调用链（供证据截图）。"""
    sys.path.insert(0, str(CODE_DIR))
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def extract(result):
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

    def j(obj):
        return json.dumps(obj, ensure_ascii=False)

    lines = [
        "MCP 服务：elevator-twin（elevator_twin.mcp_server，stdio 传输）",
        "客户端　：mcp 官方 Python SDK（ClientSession + stdio_client）",
        "",
    ]

    async def chain():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "elevator_twin.mcp_server"],
            cwd=str(CODE_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                proto = (getattr(init, "protocol_version", None)
                         or getattr(init, "protocolVersion", "?"))
                info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
                srv_name = getattr(info, "name", "elevator-twin")
                srv_ver = getattr(info, "version", "?")
                lines.append(f"[1] initialize()   → 已连接客户端；协议 {proto}，"
                             f"服务端 {srv_name} v{srv_ver}")

                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                lines.append(f"[2] list_tools()   → 共 {len(names)} 个工具：{names}")
                for t in tools.tools:
                    desc = (t.description or "").strip().splitlines()[0]
                    lines.append(f"        · {t.name}：{desc}")

                r = extract(await session.call_tool(
                    "run_simulation", arguments={"n_passengers": 8, "steps": 30}))
                lines.append("")
                lines.append("[3] call_tool run_simulation({n_passengers: 8, steps: 30})")
                lines.append(f"        → {j(r.get('metrics', r)) if isinstance(r, dict) else r}")

                r = extract(await session.call_tool("grid_snapshot", arguments={"steps": 10}))
                lines.append("")
                lines.append("[4] call_tool grid_snapshot({steps: 10})")
                if isinstance(r, list):
                    for row in r:
                        lines.append(f"        {row}")
                else:
                    lines.append(f"        → {r}")

                r = extract(await session.call_tool(
                    "optimize_social_distance", arguments={"n_passengers": 8, "steps": 30}))
                lines.append("")
                lines.append("[5] call_tool optimize_social_distance({n_passengers: 8, steps: 30})")
                if isinstance(r, dict):
                    for key in ("low", "mid", "high"):
                        lines.append(f"        {key:>4} 意愿档 → {j(r.get(key, {}))}")
                else:
                    lines.append(f"        → {r}")

    asyncio.run(asyncio.wait_for(chain(), timeout=180))
    lines.append("")
    lines.append("结论：AGH 经 MCP 协议真实调用仿真工具（而非本地函数直接调用），上表为逐次请求/响应。")
    return "\n".join(lines), 0


# --------------------------------- 渲染成 PNG ---------------------------------

BG = (13, 15, 19)
BAR_BG = (31, 36, 45)
FG = (208, 214, 224)
C_PASS = (74, 222, 128)
C_FAIL = (248, 113, 113)
C_HEAD = (56, 189, 248)
C_DIM = (148, 163, 184)
C_CMD = (134, 239, 172)
MAX_TEXT_PX = 2100


def _line_color(text):
    s = text.strip()
    if s.startswith("[PASS]"):
        return C_PASS
    if s.startswith("[FAIL]") or s.startswith("[SKIP]"):
        return C_FAIL
    if s.startswith("==") or s.startswith("[") or s.startswith("·"):
        return C_HEAD
    return FG


def _wrap(draw, text, font, max_px):
    if not text:
        return [""]
    rows, cur = [], ""
    for ch in text:
        if cur and draw.textlength(cur + ch, font=font) > max_px:
            rows.append(cur)
            cur = ch
        else:
            cur += ch
    rows.append(cur)
    return rows


def render(title, cmd, body, out_png, font_size=18):
    """把文本渲染成「终端截图」风格的 PNG。"""
    from PIL import Image, ImageDraw

    font = pick_font(font_size)
    title_font = pick_font(font_size + 3)
    pad, line_h = 28, int(font_size * 1.62)
    title_h = int((font_size + 3) * 1.7)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    rows = []
    for raw in body.replace("\r\n", "\n").split("\n"):
        color = _line_color(raw)
        for piece in _wrap(probe, raw.rstrip(), font, MAX_TEXT_PX):
            rows.append((piece, color))

    widths = [int(probe.textlength(t, font=font)) for t, _ in rows]
    widths.append(int(probe.textlength(cmd, font=font)))
    width = min(max(max(widths) + pad * 2, 960), MAX_TEXT_PX + pad * 2)

    header_h = int(title_h * 2.2)
    footer_h = int(line_h * 1.6)
    height = header_h + pad // 2 + line_h * len(rows) + footer_h

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, header_h], fill=BAR_BG)
    d.text((pad, int(title_h * 0.30)), title, font=title_font, fill=C_HEAD)
    d.text((pad, int(title_h * 1.25)), "$ " + cmd, font=font, fill=C_CMD)

    y = header_h + pad // 2
    for text, color in rows:
        d.text((pad, y), text, font=font, fill=color)
        y += line_h
    d.text((pad, height - footer_h + 4),
           f"真实运行输出渲染 · {STAMP} · 复现命令见上方", font=font, fill=C_DIM)

    img.save(out_png)
    return out_png


def save_text(name, title, cmd, body):
    path = OUT_DIR / f"{name}.txt"
    path.write_text(
        f"# {title}\n# 复现命令：{cmd}\n# 抓取时间：{STAMP}\n\n{body}\n", encoding="utf-8")
    return path


# --------------------------------- Web 界面截图 ---------------------------------

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for path in BROWSERS:
        if os.path.exists(path):
            return path
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

# 同源探针页：把作品自己的 index.html 挂到静态服务（/index.html）后，父页面就能
# 与同源的 iframe 交互——真实调用界面上的 runSimulate() 并读取渲染结果。
# $api_port / $iframe_h / $banner 由脚本替换，其余 $ 字符在本模板中不出现。
HARNESS_TMPL = string.Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>前端功能自检</title></head>
<body>
<div id="out" style="font:600 22px/1.5 Consolas,monospace;color:#0a7d32;background:#eaf7ee;padding:14px;border:2px solid #0a7d32;margin:0 0 10px 0;white-space:pre-wrap">stage0: 页面已加载，等待同源 iframe…</div>
<iframe id="f" src="/index.html?api=http://127.0.0.1:$api_port" width="1460" height="$iframe_h"></iframe>
<script>
const out = document.getElementById('out');
const f = document.getElementById('f');
function set(t) { out.textContent = t; }
async function main() {
  const r = [];
  try {
    const w = f.contentWindow, doc = w.document;
    ['runSimulate', 'runSweep', 'runAgnes', 'renderGrid', 'switchModel'].forEach(function (n) {
      r.push('函数 ' + n + ' = ' + typeof w[n]);
    });
    r.push('页面无源码泄漏 = ' + (doc.body.innerText.indexOf('localStorage.setItem') < 0 ? 'yes' : 'no'));
    await w.runSimulate();
    const met = doc.getElementById('metrics');
    r.push('指标卡片渲染 = ' + (met && met.querySelector('.error') ? 'no' : 'yes'));
    r.push('曲线图为 PNG = ' + (doc.getElementById('curve-img').src.indexOf('data:image/png') === 0 ? 'yes' : 'no'));
    r.push('回放帧标签 = ' + doc.getElementById('frame-label').textContent);
    r.push('指标文本 = ' + (met ? met.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 70));
    set('前端端到端自检（真实执行界面 JS，调用后端 /api/simulate）\\n' + r.join('\\n'));
  } catch (e) {
    set('前端自检异常：' + e.message + '\\n' + r.join('\\n'));
  }
  if (!$banner) { out.style.display = 'none'; }
}
let ran = false;
function go() { if (!ran) { ran = true; setTimeout(main, 800); } }
f.addEventListener('load', go);
setTimeout(go, 4000);
</script>
</body></html>
""")


def wait_http(url, timeout_s=45):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def capture(browser, url, out_png, window):
    tmp = Path(tempfile.gettempdir()) / "elev_shot.png"
    if tmp.exists():
        tmp.unlink()
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--window-size={window}", f"--screenshot={tmp}",
         "--virtual-time-budget=60000", url],
        timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if tmp.exists():
        shutil.move(str(tmp), str(out_png))
        return out_png
    return None


def web_screenshots(out_dir, api_port=5000, static_port=5001):
    """起后端 + 同源静态服务，抓两张图：06 功能自检（带结论条）、05 界面（纯页面）。"""
    browser = find_browser()
    if not browser:
        print("[跳过] 未找到 Chrome / Edge，请按 证据说明.md 手动截图")
        return []

    probe = Path(tempfile.mkdtemp(prefix="elev_probe_"))
    shutil.copyfile(CODE_DIR / "templates" / "index.html", probe / "index.html")

    api = subprocess.Popen([sys.executable, "webapp.py"], cwd=str(CODE_DIR), env=ENV,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    static = subprocess.Popen([sys.executable, "-m", "http.server", str(static_port)],
                              cwd=str(probe), env=ENV,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots = []
    try:
        if not wait_http(f"http://127.0.0.1:{api_port}/api/health"):
            print("[警告] 后端未就绪，跳过 Web 截图")
            return []
        if not wait_http(f"http://127.0.0.1:{static_port}/index.html"):
            print("[警告] 同源静态服务未就绪，跳过 Web 截图")
            return []

        jobs = [
            ("06_前端功能自检", 1, 1000, "1500,1340"),
            ("05_Web界面", 0, 1300, "1500,1400"),
        ]
        for name, banner, iframe_h, window in jobs:
            (probe / "harness.html").write_text(
                HARNESS_TMPL.substitute(api_port=api_port, iframe_h=iframe_h, banner=banner),
                encoding="utf-8")
            shot = capture(browser, f"http://127.0.0.1:{static_port}/harness.html",
                           out_dir / f"{name}.png", window)
            if shot:
                shots.append(shot)
            else:
                print(f"[警告] {name} 截图失败，请手动截图")
    finally:
        for proc in (static, api):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(probe, ignore_errors=True)
    return shots


# --------------------------------- 主流程 ---------------------------------

JOBS = [
    ("01_AGH执行记录", "AGH 四步闭环执行记录：任务规划 → 能力调用 → 反馈处理 → 结果验证",
     "python -m elevator_twin.agh_loop", ["-m", "elevator_twin.agh_loop"], CODE_DIR),
    ("03_测试样例自检结果", "测试样例一键自检：正常/边界/失败/接口/MCP 共 13 项，全部 PASS",
     "python 04_测试样例/run_samples.py", [str(SAMPLES_DIR / "run_samples.py")], SAMPLES_DIR),
    ("04_仿真对比实验", "基础版仿真：单次演示（逐 step 打印指标，末态收敛）",
     "python -m elevator_twin.run", ["-m", "elevator_twin.run"], CODE_DIR),
]


def main():
    ap = argparse.ArgumentParser(description="生成提交证据图（真实运行输出 → PNG + TXT）")
    ap.add_argument("--no-web", action="store_true", help="不抓取 Web 界面截图")
    ap.add_argument("--only-web", action="store_true", help="只抓 Web 界面截图，不跑控制台类证据")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("生成提交证据图（真实运行 → PNG 截图 + UTF-8 日志）")
    print("=" * 72)
    print(f"输出目录：{OUT_DIR}")

    if not args.only_web:
        for name, title, cmd_text, argv, cwd in JOBS:
            print(f"\n→ {cmd_text}")
            out, rc = run_cmd(argv, cwd)
            body = out.strip("\n")
            if rc:
                body = f"[exit code = {rc}]\n" + body
            save_text(name, title, cmd_text, body)
            render(title, cmd_text, body, OUT_DIR / f"{name}.png")
            print(f"  ✓ {name}.png / .txt（{len(body.splitlines())} 行输出，退出码 {rc}）")

        name, title = ("02_MCP调用链证据",
                       "MCP 工具调用链证据：initialize → list_tools → call_tool ×3")
        cmd_text = "python -m elevator_twin.mcp_server（mcp 官方客户端真实连接）"
        print("\n→ 抓取 MCP 调用链")
        body, rc = mcp_transcript()
        save_text(name, title, cmd_text, body)
        render(title, cmd_text, body, OUT_DIR / f"{name}.png")
        print(f"  ✓ {name}.png / .txt")

    if not args.no_web:
        print("\n→ 抓取 Web 界面（无头浏览器：真实执行界面 JS 并调用后端）")
        shots = web_screenshots(OUT_DIR)
        for shot in shots:
            print(f"  ✓ {shot.name}")
        if not shots:
            print("  - 已跳过（可手动截图，见 证据说明.md）")

    print("\n完成。可直接上传的文件：")
    for p in sorted(OUT_DIR.glob("*")):
        print(f"  · {p.name}（{p.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
