"""API 工具函数。"""

from __future__ import annotations

from typing import cast

from baize_core.schemas.entity_event import GeoBBox


def build_bbox(
    min_lon: float | None,
    min_lat: float | None,
    max_lon: float | None,
    max_lat: float | None,
) -> GeoBBox | None:
    """构建地理范围。"""
    values = [min_lon, min_lat, max_lon, max_lat]
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("bbox 参数必须成对提供")
    return GeoBBox(
        min_lon=cast(float, min_lon),
        min_lat=cast(float, min_lat),
        max_lon=cast(float, max_lon),
        max_lat=cast(float, max_lat),
    )
