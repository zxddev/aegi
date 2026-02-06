"""时间线事件提取工具。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256

from baize_core.validation.constraints_types import TimelineEvent

# 支持多种日期格式：
# - ISO 格式：2024-01-15, 2024/01/15
# - 中文格式：2024年1月15日
_DATE_RE = re.compile(
    r"(20\d{2})(?:[-/年])(\d{1,2})(?:[-/月])(\d{1,2})日?"
    r"(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)


def extract_timeline_events_from_statements(
    *,
    statements: list[str],
    default_entities: list[str] | None = None,
) -> list[TimelineEvent]:
    """从自然语言陈述中提取可校验的时间线事件（确定性规则）。"""
    entities = default_entities or ["global"]
    events: list[TimelineEvent] = []
    for stmt in statements:
        text = stmt.strip()
        if not text:
            continue
        matches = list(_DATE_RE.finditer(text))
        if not matches:
            continue
        start = _parse_datetime_match(matches[0])
        end = _parse_datetime_match(matches[1]) if len(matches) > 1 else None
        event_id = f"evt_{sha256(text.encode('utf-8')).hexdigest()[:12]}"
        events.append(
            TimelineEvent(
                event_id=event_id,
                timestamp=start,
                time_end=end,
                description=text[:200],
                entities=list(entities),
                metadata={},
                event_type=_infer_event_type(text),
                state=_infer_state(text),
            )
        )
    return events


def _parse_datetime_match(match: re.Match[str]) -> datetime:
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    # 用 UTC aware，后续统一用 epoch seconds 计算
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def _infer_event_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("deployment", "deploy", "部署")):
        return "deployment"
    if any(k in t for k in ("mobilization", "mobilise", "动员")):
        return "mobilization"
    if any(k in t for k in ("procurement", "purchase", "采购")):
        return "procurement"
    if any(k in t for k in ("training", "exercise", "训练", "演训")):
        return "training"
    if any(k in t for k in ("combat", "attack", "作战", "袭击", "打击")):
        return "combat"
    return "unknown"


def _infer_state(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("destroyed", "摧毁", "被毁")):
        return "destroyed"
    if any(k in t for k in ("operational", "运行", "可用", "正常")):
        return "operational"
    if any(k in t for k in ("advancing", "推进", "前进")):
        return "advancing"
    if any(k in t for k in ("retreating", "撤退", "后撤")):
        return "retreating"
    if any(k in t for k in ("captured", "占领", "被俘", "夺取")):
        return "captured"
    return ""
