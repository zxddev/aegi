"""多视角 Persona 生成，用于假设分析。

灵感来自 STORM（Stanford）：生成多个分析师"角色"，
从不同视角审视同一组证据，产出多样化的竞争性假设，
符合 ACH 方法论。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_PERSONA_GEN_PROMPT = """\
你是一名情报分析方法论专家。根据以下情报断言（assertions），生成 {count} 个不同视角的分析师角色。
每个角色应代表一种独特的分析立场或专业背景，用于从不同角度审视同一组证据。

断言摘要：
{evidence}

返回严格 JSON 数组，每个元素包含：
- "name": 角色名称（如"地缘政治分析师"）
- "perspective": 该角色的分析视角描述（1-2句）
- "bias_tendency": 该角色可能的认知偏向（如"倾向于从国家利益角度解读"）

只返回 JSON，不要其他内容。"""

_PERSONA_HYPOTHESIS_PROMPT = """\
你是{persona_name}。{persona_perspective}

你的认知倾向：{persona_bias}

根据以下情报断言，从你的专业视角生成 2-3 个竞争性假设来解释这些证据。
每个假设应反映你的独特分析立场。

断言：
{evidence}

每行一个假设，以 "H:" 开头。"""


@dataclass
class Persona:
    name: str
    perspective: str
    bias_tendency: str


async def generate_personas(
    assertions: list,
    *,
    llm: Any,
    count: int = 3,
) -> list[Persona]:
    """根据证据内容生成分析师角色。"""
    evidence = "\n".join(
        f"- {getattr(a, 'value', str(a))[:100]}" for a in assertions[:15]
    )
    prompt = _PERSONA_GEN_PROMPT.format(count=count, evidence=evidence)

    result = await llm.invoke(prompt)
    text = result.get("text", "")

    # 从 LLM 输出中解析 JSON 数组
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("解析 persona JSON 失败，使用默认角色")
        return _default_personas()

    return [
        Persona(
            name=item.get("name", f"分析师{i + 1}"),
            perspective=item.get("perspective", ""),
            bias_tendency=item.get("bias_tendency", ""),
        )
        for i, item in enumerate(items[:count])
    ]


async def generate_hypotheses_multi_perspective(
    assertions: list,
    source_claims: list,
    *,
    case_uid: str,
    llm: Any,
    persona_count: int = 3,
) -> list[dict]:
    """从多个角色视角生成假设。

    返回 dict 列表：{"hypothesis_text", "persona", "perspective"}。
    """
    personas = await generate_personas(assertions, llm=llm, count=persona_count)

    evidence = "\n".join(
        f"- [{getattr(a, 'kind', '?')}] {getattr(a, 'value', str(a))[:120]}"
        for a in assertions[:20]
    )

    all_hypotheses: list[dict] = []
    for persona in personas:
        prompt = _PERSONA_HYPOTHESIS_PROMPT.format(
            persona_name=persona.name,
            persona_perspective=persona.perspective,
            persona_bias=persona.bias_tendency,
            evidence=evidence,
        )
        result = await llm.invoke(prompt)
        text = result.get("text", "")

        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("H:"):
                h_text = line[2:].strip()
            elif line and len(line) > 10:
                h_text = line.lstrip("0123456789.-) ").strip()
            else:
                continue
            if h_text:
                all_hypotheses.append(
                    {
                        "hypothesis_text": h_text,
                        "persona": persona.name,
                        "perspective": persona.perspective,
                    }
                )

    logger.info(
        "Multi-perspective: %d personas → %d hypotheses (case=%s)",
        len(personas),
        len(all_hypotheses),
        case_uid,
    )
    return all_hypotheses


def _default_personas() -> list[Persona]:
    """LLM 生成失败时的兜底角色。"""
    return [
        Persona(
            "地缘政治分析师",
            "从国际关系和地缘战略角度分析",
            "倾向于从国家利益和权力博弈角度解读",
        ),
        Persona(
            "经济情报分析师",
            "从经济利益和资金流向角度分析",
            "倾向于从经济动机和利益链条角度解读",
        ),
        Persona(
            "社会文化分析师",
            "从社会运动和文化因素角度分析",
            "倾向于从民间力量和意识形态角度解读",
        ),
    ]
