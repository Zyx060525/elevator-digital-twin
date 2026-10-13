"""运行入口：单次仿真演示 + 批量对比实验 + 空间快照。"""
import pandas as pd

from elevator_twin.model import ElevatorModel


def run_once(
    width=4,
    height=4,
    n_passengers=8,
    steps=20,
    comfort_distance=1.5,
    chat_willingness_mean=0.5,
    chat_range=1.5,
    chat_threshold=1.0,
    seed=42,
    verbose=True,
):
    model = ElevatorModel(
        width=width,
        height=height,
        n_passengers=n_passengers,
        comfort_distance=comfort_distance,
        chat_willingness_mean=chat_willingness_mean,
        chat_range=chat_range,
        chat_threshold=chat_threshold,
        seed=seed,
    )
    if verbose:
        print("初始空间快照（P=乘客, C=交流中, .=空位）：")
        for row in model.grid_snapshot():
            print("  " + row)
    for i in range(1, steps + 1):
        model.step()
        if verbose:
            r = model.datacollector.get_model_vars_dataframe().iloc[-1]
            print(
                f"step={i:2d}  avg_dist={r['avg_nearest_distance']:.3f}  "
                f"min_dist={r['min_nearest_distance']:.3f}  "
                f"violation={r['violation_rate']:.3f}  chat_pairs={int(r['chat_pairs'])}"
            )
    if verbose:
        print("结束空间快照：")
        for row in model.grid_snapshot():
            print("  " + row)
    df = model.datacollector.get_model_vars_dataframe()
    return model, df


def sweep(steps=30, seed=42, verbose=True):
    """批量实验：交流意愿 × 乘客数，观察交流行为对社交距离的调制。"""
    rows = []
    for n in (4, 6, 8, 10, 12):
        for w in (0.2, 0.5, 0.8):
            _, df = run_once(
                n_passengers=n, chat_willingness_mean=w,
                steps=steps, seed=seed, verbose=False,
            )
            r = df.iloc[-1]
            rows.append({
                "乘客数": n,
                "交流意愿": w,
                "平均最近邻距离": round(r["avg_nearest_distance"], 3),
                "社交距离违规率": round(r["violation_rate"], 3),
                "交流对数": int(r["chat_pairs"]),
            })
    table = pd.DataFrame(rows)
    if verbose:
        print(table.to_string(index=False))
    return table


if __name__ == "__main__":
    print("=" * 60)
    print("单次仿真演示")
    print("=" * 60)
    run_once()

    print()
    print("=" * 60)
    print("批量对比实验（交流意愿 × 乘客数）")
    print("=" * 60)
    sweep()
