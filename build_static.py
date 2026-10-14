"""把 Flask 模板目录里的静态单页复制到 Netlify 的发布目录。

背景：Netlify 只托管静态前端，仿真 / Agnes 接口仍由 Render 上的 Flask 后端提供，
所以这里把 templates/index.html 原样复制到 public/index.html 作为站点入口。

运行：
    python build_static.py
Netlify 构建时会由 netlify.toml 里的 build.command 自动调用本脚本。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "templates" / "index.html"
OUT_DIR = ROOT / "public"
OUT = OUT_DIR / "index.html"


def main() -> int:
    if not SRC.is_file():
        print(f"[build_static] 找不到源文件：{SRC}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, OUT)
    print(f"[build_static] 已生成 {OUT.relative_to(ROOT)}（{OUT.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
