#!/usr/bin/env bash
# 电梯微空间数字孪生 - 测试样例自检（Linux）
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE="$HERE/../01_代码"

echo "============================================================"
echo "  电梯微空间数字孪生 - 测试样例自检"
echo "============================================================"
echo

PY=""
for c in python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "[错误] 未找到 python3。"; exit 1; fi

cd "$CODE"
if ! "$PY" -c "import mesa, flask, matplotlib, pandas, mcp" 2>/dev/null; then
  echo "[提示] 依赖未安装完整，请先运行  02_安装包/一键安装_Linux.sh"
  exit 1
fi

"$PY" "$HERE/run_samples.py" "$@"
echo
echo "[结果] 全部样例通过。"
