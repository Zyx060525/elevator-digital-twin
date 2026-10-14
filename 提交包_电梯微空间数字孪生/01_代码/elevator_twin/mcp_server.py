"""
MCP 服务器：把电梯数字孪生仿真封装为 MCP 工具，
供 Agnes Harness（AGH）中的 Agnes 模型通过 MCP 协议调用。

对应 AGH 闭环的"能力调用"环节：
    AGH 任务规划 -> MCP 调用本服务器工具 -> 反馈处理 -> 结果验证

启动方式（stdio 传输）：
    python -m elevator_twin.mcp_server
"""
try:
    from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
except Exception:  # mcp 2.x 将 FastMCP 更名为 MCPServer
    from mcp.server.mcpserver import MCPServer as _Server

from elevator_twin.model import ElevatorModel

mcp = _Server("elevator-twin")


@mcp.tool()
def run_simulation(
    width: int = 4,
    height: int = 4,
    n_passengers: int = 8,
    steps: int = 30,
    comfort_distance: float = 1.5,
    chat_willingness_mean: float = 0.5,
    seed: int = 42,
) -> dict:
    """运行一次电梯社交距离多智能体仿真，返回关键指标（正常场景）。"""
    model = ElevatorModel(
        width=width, height=height, n_passengers=n_passengers,
        comfort_distance=comfort_distance,
        chat_willingness_mean=chat_willingness_mean, seed=seed,
    )
    for _ in range(steps):
        model.step()
    final = model.datacollector.get_model_vars_dataframe().iloc[-1].to_dict()
    return {
        "steps": steps,
        "avg_nearest_distance": round(final["avg_nearest_distance"], 4),
        "min_nearest_distance": round(final["min_nearest_distance"], 4),
        "violation_rate": round(final["violation_rate"], 4),
        "chat_pairs": int(final["chat_pairs"]),
        "chat_pair_distance": round(final["chat_pair_distance"], 4),
    }


@mcp.tool()
def grid_snapshot(
    width: int = 4, height: int = 4, n_passengers: int = 8,
    steps: int = 10, seed: int = 42,
) -> list:
    """返回仿真结束时的空间快照（P=普通乘客, C=交流中乘客, .=空位），用于人工核查。"""
    model = ElevatorModel(width=width, height=height, n_passengers=n_passengers, seed=seed)
    for _ in range(steps):
        model.step()
    return model.grid_snapshot()


@mcp.tool()
def optimize_social_distance(
    n_passengers: int = 8,
    steps: int = 30,
    seed: int = 42,
) -> dict:
    """对比低/中/高三档交流意愿下的社交距离指标，供 AGH 反馈处理与结果验证。"""
    out = {}
    for label, w in [("low", 0.2), ("mid", 0.5), ("high", 0.8)]:
        model = ElevatorModel(
            width=4, height=4, n_passengers=n_passengers,
            chat_willingness_mean=w, seed=seed,
        )
        for _ in range(steps):
            model.step()
        final = model.datacollector.get_model_vars_dataframe().iloc[-1].to_dict()
        out[label] = {
            "avg_nearest_distance": round(final["avg_nearest_distance"], 4),
            "violation_rate": round(final["violation_rate"], 4),
            "chat_pairs": int(final["chat_pairs"]),
        }
    return out


if __name__ == "__main__":
    mcp.run()
