"""Deep Agents 适配层。"""

from __future__ import annotations

from collections.abc import Callable


def create_deep_agent_runner(
    *, system_prompt: str, tools: list[Callable[..., object]] | None = None
) -> object:
    """创建 Deep Agents 运行器。"""

    try:
        from deepagents import create_deep_agent
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 deepagents") from exc

    return create_deep_agent(
        tools=tools or [],
        system_prompt=system_prompt,
    )


def invoke_deep_agent(agent: object, *, content: str) -> object:
    """调用 Deep Agents。"""

    if not hasattr(agent, "invoke"):
        raise RuntimeError("Deep Agent 不支持 invoke")
    return agent.invoke({"messages": [{"role": "user", "content": content}]})
