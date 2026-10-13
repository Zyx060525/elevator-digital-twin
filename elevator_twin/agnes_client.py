"""Agnes 模型 HTTP 客户端（OpenAI 兼容 Chat Completions）。

把官方 Agnes Key 接入 AGH 闭环：任务规划 / 反馈处理 / 结果验证等环节
均由本模块真实调用 Agnes 模型（agnes-3.0-flash），全程仅调用 Agnes 模型。

Key 存放约定（避免泄露）：
  1. 环境变量 AGNES_API_KEY；
  2. 或同目录本地文件 .agnes_key（已在 .gitignore 中忽略，严禁提交）。
  二者皆无时 available() 返回 False，调用方自动降级为确定性文本而不报错。

运行：python -m elevator_twin.agnes_client   （做一次连通性自检）
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BASE_URL = "https://api.agnes-ai.cn/v1"
MODEL = "agnes-3.0-flash"
_TIMEOUT = 120

_KEY_FILE = Path(__file__).with_name(".agnes_key")


def _load_key() -> str:
    key = os.environ.get("AGNES_API_KEY", "").strip()
    if key:
        return key
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def available() -> bool:
    """是否已配置可用的 Agnes Key。"""
    return bool(_load_key())


def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """调用 Agnes 模型完成一轮对话，返回助手文本。

    Key 缺失或请求失败时返回空字符串，由调用方自行降级。
    """
    key = _load_key()
    if not key:
        return ""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"[agnes] 请求异常：{exc}")
        return ""

    if resp.status_code != 200:
        print(f"[agnes] HTTP {resp.status_code}: {resp.text[:500]}")
        return ""

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"[agnes] 响应解析失败：{exc}")
        return ""


if __name__ == "__main__":
    if not available():
        print("未检测到 Agnes Key：请设置环境变量 AGNES_API_KEY 或创建 elevator_twin/.agnes_key")
        raise SystemExit(1)

    print(f"模型：{MODEL}")
    print("连通性自检：", end="", flush=True)
    text = chat("你是一个简洁的助手。", "请回复「连通正常」四个字。").strip()
    print(text or "（无响应）")
