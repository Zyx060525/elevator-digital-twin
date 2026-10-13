"""
可视化：指标曲线 + 空间热力图 + 批量实验对比图（用于演示视频 / PPT）。

运行：python -m elevator_twin.visualize
输出：elevator_twin/figs/ 目录下的 PNG 图片。
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from elevator_twin.model import ElevatorModel
from elevator_twin.run import run_once, sweep

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FIG_DIR = os.path.join(os.path.dirname(__file__), "figs")
os.makedirs(FIG_DIR, exist_ok=True)


def plot_metrics_curve(steps=30, seed=42, save=True):
    """指标随仿真步的变化曲线（展示模型收敛）。"""
    _, df = run_once(n_passengers=8, steps=steps, seed=seed, verbose=False)
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    df["avg_nearest_distance"].plot(ax=axes[0], marker="o", title="Avg nearest-neighbor distance")
    df["violation_rate"].plot(ax=axes[1], marker="o", title="Social-distance violation rate")
    df["chat_pairs"].plot(ax=axes[2], marker="o", title="Active chat pairs")
    for ax in axes:
        ax.set_xlabel("step")
        ax.grid(True, alpha=0.3)
    fig.suptitle("Metrics over simulation steps", fontsize=13)
    fig.tight_layout()
    path = os.path.join(FIG_DIR, "metrics_curve.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("saved:", path)
    return path


def distance_heatmap(width=4, height=4, n_passengers=8, steps=20,
                     chat_willingness_mean=0.5, seed=42, save=True):
    """空间热力图：每格颜色 = 该乘客最近邻距离；红=拥挤(近)，绿=宽松(远)，灰=空位。"""
    model = ElevatorModel(
        width=width, height=height, n_passengers=n_passengers,
        chat_willingness_mean=chat_willingness_mean, seed=seed,
    )
    for _ in range(steps):
        model.step()

    mat = np.full((height, width), np.nan)
    for a in model.schedule.agents:
        x, y = a.pos
        d = model.nearest_neighbor_distance(a)
        mat[y, x] = d if d is not None else 0.0

    cmap = plt.cm.RdYlGn_r.copy()
    cmap.set_bad("lightgray")
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(mat, cmap=cmap, vmin=1.0, vmax=3.0)
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_title(f"Distance heatmap (chat willingness = {chat_willingness_mean})")
    fig.colorbar(im, ax=ax, label="nearest-neighbor distance (cells)")
    for a in model.schedule.agents:
        x, y = a.pos
        ax.text(x, y, "C" if a.in_chat else "P", ha="center", va="center",
                color="white", fontweight="bold")
    path = os.path.join(FIG_DIR, f"heatmap_w{chat_willingness_mean}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("saved:", path)
    return path


def plot_sweep(steps=30, seed=42, save=True):
    """批量实验对比图：交流意愿 × 乘客数 对三项指标的影响（核心结论可视化）。"""
    table = sweep(steps=steps, seed=seed, verbose=False)
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    for w, grp in table.groupby("交流意愿"):
        axes[0].plot(grp["乘客数"], grp["平均最近邻距离"], marker="o", label=f"willingness={w}")
        axes[1].plot(grp["乘客数"], grp["社交距离违规率"], marker="o", label=f"willingness={w}")
        axes[2].plot(grp["乘客数"], grp["交流对数"], marker="o", label=f"willingness={w}")
    axes[0].set_title("Avg nearest-neighbor distance")
    axes[1].set_title("Social-distance violation rate")
    axes[2].set_title("Active chat pairs")
    for ax in axes:
        ax.set_xlabel("n_passengers")
        ax.grid(True, alpha=0.3)
        ax.legend()
    fig.suptitle("Chat willingness x passenger count (sweep)", fontsize=13)
    fig.tight_layout()
    path = os.path.join(FIG_DIR, "sweep.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("saved:", path)
    return path


def main():
    print("== 生成指标曲线 ==")
    plot_metrics_curve()
    print("== 生成空间热力图（低意愿 vs 高意愿）==")
    distance_heatmap(chat_willingness_mean=0.2)
    distance_heatmap(chat_willingness_mean=0.8)
    print("== 生成批量实验对比图 ==")
    plot_sweep()


if __name__ == "__main__":
    main()
