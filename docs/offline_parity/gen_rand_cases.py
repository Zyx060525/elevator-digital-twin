"""生成随机参数用例（含越界值与极端组合），用于前后端一致性交叉校验。

用法：python docs/offline_parity/gen_rand_cases.py
      再以 CASE_FILE=engine_cases_rand.json 跑 engine_parity_py.py / engine_parity_js.js。
"""
import json
import os
import random
from pathlib import Path

TMP = str(Path(__file__).resolve().parent)
rnd = random.Random(20251014)


def cells_of(w_m, d_m, cs):
    return max(1, int(w_m / cs)) * max(1, int(d_m / cs))


cases = []
for _ in range(30):
    w = rnd.choice([2, 3, 4, 5, 8, 12, 20])          # 20 会被夹到 12，用于校验夹取口径
    h = rnd.choice([2, 3, 4, 6, 12])
    cap = max(2, min(12, w)) * max(2, min(12, h))
    cases.append({"kind": "basic", "params": {
        "width": w,
        "height": h,
        "n_passengers": min(cap, rnd.choice([1, 3, 8, 15, 36, 144, 200])),
        "steps": rnd.choice([1, 5, 12, 30, 60, 150, 400]),
        "seed": rnd.choice([0, 1, 7, 42, 999, 123456, 10 ** 9]),
        "chat_willingness_mean": rnd.choice([0.0, 0.15, 0.5, 0.83, 1.0, 1.5, -0.4]),
        "comfort_distance": rnd.choice([0.2, 0.5, 1.5, 2.75, 5.0, 9.0]),
        "chat_range": rnd.choice([0.5, 0.9, 1.5, 3.3, 6.0, 12.0]),
        "chat_threshold": rnd.choice([0.0, 0.4, 1.0, 1.7, 2.0, 4.0]),
    }})
for _ in range(30):
    w_m = rnd.choice([0.5, 0.8, 1.6, 2.0, 3.4, 5.0, 9.0])
    d_m = rnd.choice([0.8, 1.4, 2.0, 3.0, 5.0])
    cs = rnd.choice([0.1, 0.25, 0.4, 0.5, 0.75, 1.0, 2.0])
    cap = cells_of(max(0.8, min(5.0, w_m)), max(0.8, min(5.0, d_m)), max(0.1, min(1.0, cs)))
    cases.append({"kind": "enhanced", "params": {
        "width_m": w_m,
        "depth_m": d_m,
        "cell_size": cs,
        "n_floors": rnd.choice([2, 4, 6, 10, 25, 60]),
        "board_interval": rnd.choice([1, 2, 3, 5, 11, 50, 90]),
        "max_passengers": min(cap, rnd.choice([1, 2, 4, 6, 12, 25, 60])),
        "comfort_distance_m": rnd.choice([0.2, 0.3, 1.0, 1.6, 2.0, 4.0]),
        "chat_willingness_mean": rnd.choice([0.0, 0.3, 0.5, 0.9, 1.0]),
        "chat_range_m": rnd.choice([0.2, 0.3, 0.8, 1.5, 2.0, 5.0]),
        "chat_threshold": rnd.choice([0.0, 0.5, 1.0, 1.8, 2.0]),
        "repulsion_strength": rnd.choice([0.0, 0.3, 1.0, 2.5, 5.0, 9.0]),
        "attraction_strength": rnd.choice([0.0, 0.5, 1.0, 3.0, 5.0]),
        "steps": rnd.choice([1, 6, 14, 30, 45, 80, 150, 400]),
        "seed": rnd.choice([0, 3, 42, 77, 2024, 10 ** 9]),
    }})

with open(os.path.join(TMP, "engine_cases_rand.json"), "w", encoding="utf-8") as fh:
    json.dump({"cases": cases}, fh, ensure_ascii=False, indent=1)
print("随机用例生成完毕：", len(cases), "组")
