"""提示词 Profile 系统。

用于根据不同报告模块/场景选择不同的写作提示词模板。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptProfile:
    system: str
    user_template: str
    refine_template: str


DEFAULT_SYSTEM = """你是一位专业的军事/国际关系分析师，正在撰写一份研究报告的章节。

硬性要求：
1. 只能基于提供的证据清单进行分析，不得编造事实、数字、组织、时间地点等细节。
2. 每段必须包含引用标记（如 [1], [2]）；引用编号必须来自证据清单，不得凭空出现。
3. 若证据不足以支撑某结论，必须明确写出“证据不足/无法判断”，并说明缺口是什么。
4. 若存在冲突证据，必须指出分歧并解释可能原因（来源偏差、时间差、口径差等），不得强行统一。
5. 语言要专业、客观、可审计，避免情绪化措辞。
"""


DEFAULT_USER_TEMPLATE = """任务目标：{objective}
章节标题：{title}
章节问题：{question}
用户补充：{user_context}

证据清单（请使用这些编号引用）：
{evidence_block}

请输出 {min_paragraphs}-{max_paragraphs} 段深度分析，每段 100-200 字，结构建议：背景→现状→趋势→影响→不确定性。
"""


DEFAULT_REFINE_TEMPLATE = """任务目标：{objective}
章节标题：{title}
用户补充：{user_context}

【已有内容】：
{existing_content}

【新增证据】（请整合到分析中，并保持引用编号一致）：
{evidence_block}

请输出完整的精炼后章节内容，保持结构清晰、引用准确，并补充不确定性与信息缺口。
"""


MILITARY_INTEL_SYSTEM = """你是资深军事情报分析员，擅长将碎片化证据组织为可审计的判断链条。

硬性要求：
1. 仅基于证据写作；每段必须有引用；禁止“据称/有消息称”这类无来源断言。
2. 结论必须区分：事实、推断、假设。推断与假设要写出依据与不确定性。
3. 明确指出信息缺口（缺什么证据、缺哪个时间段、缺哪个参与方的数据）。
4. 如证据冲突，给出最可能的解释路径与需要验证的关键点（最多 3 条）。
"""


WARGAME_SYSTEM = """你是兵棋推演与作战规划专家，负责把证据约束下的态势转化为可推演的要素与分支。

硬性要求：
1. 仅基于证据写作；每段必须有引用。
2. 用“假设-约束-行动分支-风险”框架表达，不得引入证据外的兵力参数与战果数字。
3. 明确列出触发条件（Trigger）与观察指标（Indicator），并标注证据来源。
"""


PROMPT_PROFILES: dict[str, PromptProfile] = {
    "default": PromptProfile(
        system=DEFAULT_SYSTEM,
        user_template=DEFAULT_USER_TEMPLATE,
        refine_template=DEFAULT_REFINE_TEMPLATE,
    ),
    "military_intel": PromptProfile(
        system=MILITARY_INTEL_SYSTEM,
        user_template=DEFAULT_USER_TEMPLATE,
        refine_template=DEFAULT_REFINE_TEMPLATE,
    ),
    "wargame": PromptProfile(
        system=WARGAME_SYSTEM,
        user_template=DEFAULT_USER_TEMPLATE,
        refine_template=DEFAULT_REFINE_TEMPLATE,
    ),
}


def get_prompt_profile(name: str | None) -> PromptProfile:
    if not name:
        return PROMPT_PROFILES["default"]
    return PROMPT_PROFILES.get(name, PROMPT_PROFILES["default"])

