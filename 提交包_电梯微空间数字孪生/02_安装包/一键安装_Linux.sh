#!/usr/bin/env bash
# 电梯微空间数字孪生 - 离线依赖安装（Linux / Python 3.11）
# 用法：bash 一键安装_Linux.sh
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELS="$HERE/wheels_linux_py311"
CODE="$HERE/../01_代码"

echo "============================================================"
echo "  电梯微空间数字孪生 - 离线依赖安装（Linux / Python 3.11）"
echo "============================================================"
echo

PY=""
for c in python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[错误] 未找到 python3，请先安装 Python 3.11。"
  exit 1
fi
echo "使用解释器：$("$PY" --version 2>&1)"
echo "离线包目录：$WHEELS"
echo

echo "[1/3] 从离线 wheel 安装依赖（--no-index，全程不联网）..."
"$PY" -m pip install --no-index --find-links "$WHEELS" -r "$HERE/requirements-lock-linux.txt"

echo
echo "[2/3] 校验依赖导入..."
cd "$CODE"
"$PY" -c "import mesa, numpy, pandas, matplotlib, flask, requests, mcp; print('[OK] 依赖校验通过：mesa', mesa.__version__)"

echo
echo "[3/3] 安装完成。"
echo "      下一步：bash 04_测试样例/一键自检_Linux.sh"
echo "      启动网页：cd 01_代码 && $PY webapp.py   （浏览器打开 http://127.0.0.1:5000）"
