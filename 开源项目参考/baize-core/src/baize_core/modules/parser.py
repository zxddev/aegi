"""用户自由输入解析器。

将用户自由文本输入解析为可研究的章节结构（StormSectionSpec 列表）。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from baize_core.llm.runner import LlmRunner
from baize_core.schemas.policy import StageType
from baize_core.schemas.storm import SectionType, StormSectionSpec


class _ParsedSection(BaseModel):
    """LLM 解析输出的单个章节。"""

    title: str = Field(min_length=1, description="章节标题（中文，精炼）")
    question: str = Field(
        min_length=1,
        description="章节研究问题（可检索、可验证，避免空泛）",
    )
    section_type: SectionType = SectionType.DEFAULT
    prompt_profile: str = Field(
        default="default", min_length=1, description="写作提示词 profile 名称"
    )


class _ParsedSections(BaseModel):
    """LLM 解析输出的章节集合。"""

    sections: list[_ParsedSection] = Field(
        min_length=1, max_length=8, description="章节列表（1-8 个）"
    )


@dataclass
class UserInputParser:
    """解析用户自由文字输入为章节结构。"""

    max_sections: int = 8

    async def parse_to_sections(
        self,
        user_input: str,
        llm_runner: LlmRunner,
        *,
        task_id: str,
        section_id: str | None = None,
    ) -> list[StormSectionSpec]:
        """用 LLM 解析用户输入生成章节。"""

        system = (
            "你是资深分析任务设计师，负责把用户的自由输入转成可执行的研究报告章节计划。\n\n"
            "要求：\n"
            "1. 输出 3-8 个章节（若用户输入很短也至少 1 个）。\n"
            "2. 每个章节必须给出明确的研究问题（question），可通过公开资料检索与证据验证。\n"
            "3. 标题要短、名词化；问题要具体，包含范围/对象/时间/地点等约束（若用户提供）。\n"
            "4. 避免空话套话：不要写“分析现状/影响/建议”这种无约束问题。\n"
            "5. 不要输出任何多余文本，严格按 schema 输出。\n"
        )
        user = (
            "请将下面用户输入解析为报告章节结构。\n\n"
            f"用户输入：\n{user_input}\n"
        )

        structured = await llm_runner.generate_structured(
            system=system,
            user=user,
            schema=_ParsedSections,
            stage=StageType.ORIENT,
            task_id=task_id,
            section_id=section_id,
            token_estimate=1200,
        )
        data = structured.data
        sections = []
        for item in data.sections[: self.max_sections]:
            sections.append(
                StormSectionSpec(
                    title=item.title.strip(),
                    question=item.question.strip(),
                    section_type=item.section_type,
                    prompt_profile=item.prompt_profile.strip() or "default",
                )
            )
        return sections

