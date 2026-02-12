# Author: msq
"""CAMEO 事件编码映射。"""

from __future__ import annotations

CAMEO_ROOT_LABELS: dict[str, str] = {
    "01": "公开声明",
    "02": "呼吁",
    "03": "表达合作意向",
    "04": "咨询",
    "05": "外交合作",
    "06": "物质合作",
    "07": "提供援助",
    "08": "让步",
    "09": "调查",
    "10": "要求",
    "11": "拒绝",
    "12": "威胁",
    "13": "抗议",
    "14": "暴力行为",
    "15": "使用武力",
    "17": "军事行动",
    "18": "胁迫",
    "19": "大规模暴力",
    "20": "大规模杀伤",
}

CAMEO_CATEGORY: dict[str, str] = {
    "01": "neutral",
    "02": "cooperation",
    "03": "cooperation",
    "04": "cooperation",
    "05": "cooperation",
    "06": "cooperation",
    "07": "cooperation",
    "08": "cooperation",
    "09": "neutral",
    "10": "neutral",
    "11": "conflict",
    "12": "conflict",
    "13": "conflict",
    "14": "conflict",
    "15": "conflict",
    "17": "conflict",
    "18": "conflict",
    "19": "conflict",
    "20": "conflict",
}


def cameo_root_label(root_code: str) -> str:
    """返回 CAMEO 根编码的中文描述。"""
    return CAMEO_ROOT_LABELS.get(root_code, f"未知({root_code})")


def cameo_category(root_code: str) -> str:
    """返回 CAMEO 根编码分类。"""
    return CAMEO_CATEGORY.get(root_code, "unknown")


def is_high_conflict(root_code: str) -> bool:
    """是否为高冲突事件（14-20）。"""
    try:
        return int(root_code) >= 14
    except (TypeError, ValueError):
        return False
