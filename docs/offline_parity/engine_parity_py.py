"""用 Flask 测试客户端跑出 Python 后端的标准答案，供前后端数值一致性对比。

用法（在仓库根目录）：
    python docs/offline_parity/engine_parity_py.py                      # 默认跑 engine_cases.json（27 组固定用例）
    set CASE_FILE=engine_cases_rand.json && python docs/offline_parity/engine_parity_py.py   # 跑随机用例
再执行 node docs/offline_parity/engine_parity_js.js 做逐字段比对（CASE_FILE 需一致）。
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # docs/offline_parity/
ROOT = str(HERE.parents[1])                     # 仓库根目录
TMP = str(HERE)
CASES = os.environ.get("CASE_FILE", "engine_cases.json")
OUT = CASES.replace("cases", "py_out")

sys.path.insert(0, ROOT)
os.chdir(ROOT)

from webapp import app  # noqa: E402

cases = json.load(open(os.path.join(TMP, CASES), encoding="utf-8"))["cases"]
client = app.test_client()

out = []
for c in cases:
    url = "/api/simulate_enhanced" if c["kind"] == "enhanced" else "/api/simulate"
    resp = client.post(url, json=c["params"])
    d = resp.get_json()
    if d is None:
        out.append({"error": f"HTTP {resp.status_code}: {resp.get_data(as_text=True)[:200]}"})
        continue
    d.pop("curve", None)   # 曲线是图，不参与数值比对
    d["_kind"] = c["kind"]
    out.append(d)

with open(os.path.join(TMP, OUT), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False)
print(f"Python 侧完成 {len(out)} 组，已写入 {OUT}")
