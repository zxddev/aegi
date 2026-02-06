"""工具输出净化层（ToolOutputSanitizer）。

目标：外部工具输出进入模型上下文前，先做确定性净化：
- 字段白名单过滤（按工具）
- 字段级长度截断（防止上下文爆炸）
- 危险模式检测（提示注入/越权指令文本）
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:  # Prometheus 指标（可选）
    from prometheus_client import Counter as _PrometheusCounter

    _PROMETHEUS_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _PrometheusCounter = None
    _PROMETHEUS_AVAILABLE = False

_SANITIZER_INTERCEPTS_TOTAL = (
    _PrometheusCounter(
        "baize_core_tool_output_sanitizer_intercepts_total",
        "工具输出净化拦截次数（发生字段丢弃/截断/危险模式）",
        ["tool_name"],
    )
    if _PROMETHEUS_AVAILABLE
    else None
)
_SANITIZER_DANGEROUS_TOTAL = (
    _PrometheusCounter(
        "baize_core_tool_output_sanitizer_dangerous_total",
        "工具输出危险模式检测次数",
        ["tool_name"],
    )
    if _PROMETHEUS_AVAILABLE
    else None
)

TRUNCATED_MARK = " [TRUNCATED]"
INJECTION_MARK = "[POTENTIAL_PROMPT_INJECTION]"


DEFAULT_DANGEROUS_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?(the\s+)?above",
    r"you\s+are\s+now\s+",
    r"new\s+instructions\s*:",
    r"system\s+prompt",
    r"developer\s+message",
    r"BEGIN\s+SYSTEM\s+PROMPT",
    r"jailbreak",
)


@dataclass(frozen=True)
class SanitizationReport:
    """净化报告（用于审计与指标）。"""

    tool_name: str
    dropped_fields: tuple[str, ...] = ()
    truncated_fields: tuple[str, ...] = ()
    dangerous_fields: tuple[str, ...] = ()

    @property
    def has_issues(self) -> bool:
        return bool(
            self.dropped_fields or self.truncated_fields or self.dangerous_fields
        )

    @property
    def has_dangerous(self) -> bool:
        return bool(self.dangerous_fields)


class ToolOutputSanitizer:
    """工具输出净化器。"""

    def __init__(
        self,
        *,
        whitelist_path: Path | None = None,
        dangerous_patterns: Iterable[str] = DEFAULT_DANGEROUS_PATTERNS,
    ) -> None:
        self._rules = _load_whitelist_rules(whitelist_path)
        self._dangerous_patterns = [
            re.compile(pattern, flags=re.IGNORECASE) for pattern in dangerous_patterns
        ]

    def sanitize(
        self,
        *,
        tool_name: str,
        payload: dict[str, object],
    ) -> tuple[dict[str, object], SanitizationReport]:
        """净化工具输出。

        Args:
            tool_name: 工具名
            payload: 原始输出（dict）

        Returns:
            (sanitized_payload, report)
        """

        rule = self._rules.get(tool_name)
        dropped: list[str] = []
        truncated: list[str] = []
        dangerous: list[str] = []

        sanitized = self._sanitize_dict(
            payload,
            rule=rule if isinstance(rule, dict) else None,
            path_prefix="",
            dropped=dropped,
            truncated=truncated,
            dangerous=dangerous,
        )
        report = SanitizationReport(
            tool_name=tool_name,
            dropped_fields=tuple(sorted(set(dropped))),
            truncated_fields=tuple(sorted(set(truncated))),
            dangerous_fields=tuple(sorted(set(dangerous))),
        )

        if _SANITIZER_INTERCEPTS_TOTAL is not None and report.has_issues:
            _SANITIZER_INTERCEPTS_TOTAL.labels(tool_name=tool_name).inc()
        if _SANITIZER_DANGEROUS_TOTAL is not None and report.has_dangerous:
            _SANITIZER_DANGEROUS_TOTAL.labels(tool_name=tool_name).inc()

        if report.dropped_fields:
            logger.warning(
                "ToolOutputSanitizer 丢弃未白名单字段: tool=%s fields=%s",
                tool_name,
                report.dropped_fields,
            )
        if report.has_dangerous:
            logger.warning(
                "ToolOutputSanitizer 检测到疑似提示注入模式: tool=%s fields=%s",
                tool_name,
                report.dangerous_fields,
            )
        return sanitized, report

    def _sanitize_dict(
        self,
        data: dict[str, object],
        *,
        rule: dict[str, Any] | None,
        path_prefix: str,
        dropped: list[str],
        truncated: list[str],
        dangerous: list[str],
    ) -> dict[str, object]:
        allowed_fields = _as_str_list(rule.get("fields")) if rule else None
        max_length = _as_int_map(rule.get("max_length")) if rule else {}
        nested = rule.get("nested") if rule else None
        nested_rules: dict[str, dict[str, Any]] = (
            nested if isinstance(nested, dict) else {}
        )

        result: dict[str, object] = {}
        for key, value in data.items():
            field_path = f"{path_prefix}.{key}" if path_prefix else key
            if allowed_fields is not None and key not in allowed_fields:
                dropped.append(field_path)
                continue

            subrule = nested_rules.get(key)
            if isinstance(value, dict):
                if subrule and isinstance(subrule, dict):
                    result[key] = self._sanitize_dict(
                        value,
                        rule=subrule,
                        path_prefix=field_path,
                        dropped=dropped,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                else:
                    # 未配置子规则：保留原样（不做字段过滤），仅做危险模式与长度控制
                    result[key] = self._sanitize_dict(
                        value,
                        rule=None,
                        path_prefix=field_path,
                        dropped=dropped,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                continue

            if isinstance(value, list):
                if subrule and isinstance(subrule, dict):
                    result[key] = self._sanitize_list(
                        value,
                        rule=subrule,
                        path_prefix=field_path,
                        dropped=dropped,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                else:
                    result[key] = self._sanitize_list(
                        value,
                        rule=None,
                        path_prefix=field_path,
                        dropped=dropped,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                continue

            # 标量字段
            if isinstance(value, str):
                result[key] = self._sanitize_text(
                    value,
                    max_len=max_length.get(key),
                    field_path=field_path,
                    truncated=truncated,
                    dangerous=dangerous,
                )
            else:
                result[key] = value
        return result

    def _sanitize_list(
        self,
        items: list[object],
        *,
        rule: dict[str, Any] | None,
        path_prefix: str,
        dropped: list[str],
        truncated: list[str],
        dangerous: list[str],
    ) -> list[object]:
        # 若配置了 item_fields，则认为 list item 是 dict 且需要字段过滤
        item_fields = _as_str_list(rule.get("item_fields")) if rule else None
        item_max_length = _as_int_map(rule.get("max_length")) if rule else {}
        item_nested = rule.get("nested") if rule else None
        item_nested_rules: dict[str, dict[str, Any]] = (
            item_nested if isinstance(item_nested, dict) else {}
        )

        sanitized_list: list[object] = []
        for idx, item in enumerate(items):
            item_prefix = f"{path_prefix}[{idx}]"
            if isinstance(item, dict):
                # 把 item_fields/max_length/nested 映射成 dict rule
                item_rule: dict[str, Any] | None = None
                if item_fields is not None or item_max_length or item_nested_rules:
                    item_rule = {
                        "fields": item_fields,
                        "max_length": item_max_length,
                        "nested": item_nested_rules,
                    }
                sanitized_list.append(
                    self._sanitize_dict(
                        item,
                        rule=item_rule,
                        path_prefix=item_prefix,
                        dropped=dropped,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                )
            elif isinstance(item, str):
                sanitized_list.append(
                    self._sanitize_text(
                        item,
                        max_len=None,
                        field_path=item_prefix,
                        truncated=truncated,
                        dangerous=dangerous,
                    )
                )
            else:
                sanitized_list.append(item)
        return sanitized_list

    def _sanitize_text(
        self,
        text: str,
        *,
        max_len: int | None,
        field_path: str,
        truncated: list[str],
        dangerous: list[str],
    ) -> str:
        value = text
        if max_len is not None and max_len > 0 and len(value) > max_len:
            value = value[:max_len] + TRUNCATED_MARK
            truncated.append(field_path)

        if self._contains_dangerous_pattern(value):
            dangerous.append(field_path)
            # 标记但不删除（保持可复核）
            value = f"{INJECTION_MARK}\n{value}"
        return value

    def _contains_dangerous_pattern(self, text: str) -> bool:
        for pattern in self._dangerous_patterns:
            if pattern.search(text):
                return True
        return False


def _default_whitelist_path() -> Path:
    # baize_core/llm/sanitizer.py -> baize_core/config/tool_output_whitelist.yaml
    base_dir = Path(__file__).resolve().parent.parent
    return base_dir / "config" / "tool_output_whitelist.yaml"


def _load_whitelist_rules(whitelist_path: Path | None) -> dict[str, object]:
    path = whitelist_path or _default_whitelist_path()
    if not path.exists():
        raise FileNotFoundError(f"工具输出白名单配置不存在: {path}")
    suffix = path.suffix.lower()
    if suffix not in {".yaml", ".yml"}:
        raise ValueError(f"工具输出白名单配置必须为 YAML: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("加载 tool_output_whitelist.yaml 需要安装 pyyaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("tool_output_whitelist.yaml 内容必须是字典")
    rules = data.get("tool_output_whitelist")
    if not isinstance(rules, dict):
        raise ValueError("tool_output_whitelist.yaml 缺少 tool_output_whitelist 字段")
    return rules


def _as_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError("字段白名单必须是字符串列表")


def _as_int_map(value: object) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("max_length 必须是字典")
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(raw, int) and raw > 0:
            result[key] = raw
    return result
