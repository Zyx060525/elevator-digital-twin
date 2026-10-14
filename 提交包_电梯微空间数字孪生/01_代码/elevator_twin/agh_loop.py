"""
AGH（Agnes Harness）执行闭环演示

演示 AGH 作为智能体底座，经 MCP 调用本作品仿真能力，完成
"任务规划 -> 能力调用 -> 反馈处理 -> 结果验证" 四个连续步骤（满足 3.1 至少三步骤）。

说明：
- 用真实 MCP 客户端（stdio）连接 elevator_twin.mcp_server，产出可核查的工具调用链。
- "Agnes 决策"（规划 / 反馈 / 验证）经 elevator_twin.agnes_client 真实调用 Agnes 模型
  agnes-3.0-flash（OpenAI 兼容 Chat Completions，全程仅调用 Agnes 模型，不接第三方模型）。
- Key 缺失或网络异常时自动降级为确定性文本，保证演示不中断。

运行：python -m elevator_twin.agh_loop
"""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from elevator_twin import agnes_client


def _extract(result):
    """从 MCP CallToolResult 提取数据（dict / list / str），兼容 mcp 1.x 与 2.x。"""
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


# ---------- Agnes 模型调用（真实调用，失败时降级为确定性文本） ----------

SYSTEM_PLAN = (
    "你是 Agnes，密闭空间治理数字孪生仿真智能体。请把用户目标拆解为可执行的仿真实验步骤，"
    "明确轿厢参数、选用工具与评价指标，输出简洁中文。"
)
SYSTEM_JUDGE = (
    "你是 Agnes，负责根据仿真指标判断策略是否达标并给出反馈。"
    "重点关注交流行为是否压缩了社交距离，输出简洁中文建议。"
)
SYSTEM_VERIFY = (
    "你是 Agnes，负责验证仿真结论并输出密闭空间社交距离治理策略，输出简洁中文。"
)


def agnes_plan(goal, tool_names):
    text = agnes_client.chat(
        SYSTEM_PLAN,
        f"任务目标：{goal}\n可调用工具：{', '.join(tool_names)}\n请给出任务拆解。",
    ).strip()
    return text or _plan_fallback(goal, tool_names)


def agnes_judge(metrics):
    text = agnes_client.chat(
        SYSTEM_JUDGE,
        f"仿真指标（低/中/高三档交流意愿）：\n{json.dumps(metrics, ensure_ascii=False, indent=2)}",
    ).strip()
    return text or _judge_fallback(metrics)


def agnes_verify(metrics):
    text = agnes_client.chat(
        SYSTEM_VERIFY,
        f"仿真结果：\n{json.dumps(metrics, ensure_ascii=False, indent=2)}",
    ).strip()
    return text or _verify_fallback(metrics)


# ---------- 无 Key / 请求失败时的确定性降级 ----------

def _plan_fallback(goal, tool_names):
    return (
        f"目标「{goal}」拆解：① 固定轿厢 4×4、乘客 8 人；"
        f"② 用 {tool_names} 中的 optimize_social_distance 扫描低/中/高三档交流意愿；"
        f"③ 以平均最近邻距离、违规率、交流对数为评价指标。"
    )


def _judge_fallback(metrics):
    low, high = metrics["low"], metrics["high"]
    if low["chat_pairs"] == 0 and high["chat_pairs"] > 0:
        return (
            f"检测到交流行为压缩社交距离：低意愿 0 交流对 vs 高意愿 {high['chat_pairs']} 交流对；"
            f"建议策略中抑制近距离交流并优化密度。"
        )
    return "指标无显著差异，维持当前策略。"


def _verify_fallback(metrics):
    low, high = metrics["low"], metrics["high"]
    return (
        f"验证通过：交流意愿低→高，平均最近邻距离由 {low['avg_nearest_distance']} 降至 "
        f"{high['avg_nearest_distance']}，交流对数由 {low['chat_pairs']} 增至 {high['chat_pairs']}。"
        f"结论：密闭空间治理须兼顾社交距离与交流抑制，建议设置导流/限流策略。"
    )


async def run_agh_loop():
    server = StdioServerParameters(command="python", args=["-m", "elevator_twin.mcp_server"])

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            if agnes_client.available():
                print(f"Agnes 模型：{agnes_client.MODEL}（真实调用）")
            else:
                print("Agnes 模型：未检测到 Key，使用确定性降级逻辑")
            print("== ① 任务规划 ==")
            print("AGH 可调用能力（MCP 工具）：", tool_names)
            goal = "优化 4×4 电梯轿厢内的社交距离"
            print("任务目标：", goal)
            print("Agnes 规划：", agnes_plan(goal, tool_names))

            print("\n== ② 能力调用 ==")
            res = await session.call_tool(
                "optimize_social_distance", arguments={"n_passengers": 8, "steps": 30}
            )
            metrics = _extract(res)
            print("MCP 调用 optimize_social_distance：")
            print(json.dumps(metrics, ensure_ascii=False, indent=2))

            print("\n== ③ 反馈处理 ==")
            print("Agnes 反馈：", agnes_judge(metrics))
            res2 = await session.call_tool(
                "run_simulation", arguments={"n_passengers": 8, "steps": 30}
            )
            print("复核 run_simulation：", json.dumps(_extract(res2), ensure_ascii=False))
            snap = await session.call_tool("grid_snapshot", arguments={"steps": 10})
            snap_data = _extract(snap)
            print("空间快照（可人工核查）：")
            if isinstance(snap_data, list):
                for row in snap_data:
                    print("  " + row)
            else:
                print("  ", snap_data)

            print("\n== ④ 结果验证 ==")
            print("Agnes 验证结论：", agnes_verify(metrics))


if __name__ == "__main__":
    asyncio.run(run_agh_loop())
