# Author: msq
"""GDELT 异常检测测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegi_core.services.gdelt_monitor import GDELTMonitor


def _make_event(**overrides) -> SimpleNamespace:
    defaults = {
        "uid": "ge_1",
        "gdelt_id": "gid_1",
        "case_uid": None,
        "title": "Event",
        "url": "https://example.com/event",
        "source_domain": "example.com",
        "language": "",
        "cameo_code": "0211",
        "cameo_root": "02",
        "goldstein_scale": 1.0,
        "actor1": "A",
        "actor2": "B",
        "actor1_country": "US",
        "actor2_country": "IR",
        "geo_country": None,
        "geo_name": None,
        "tone": -1.0,
        "status": "new",
        "matched_subscription_uids": ["sub_1"],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_detect_extreme_goldstein() -> None:
    event = _make_event(goldstein_scale=-8.0, cameo_root="02")
    session = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=AsyncMock(), db_session=session)
        anomalies = await monitor.detect_anomalies([event])

    assert len(anomalies) == 1
    assert anomalies[0].status == "anomaly"
    session.commit.assert_called_once()
    emitted_event = mock_bus.emit.call_args[0][0]
    assert emitted_event.event_type == "gdelt.anomaly_detected"
    assert emitted_event.payload["anomaly_type"] == "extreme_conflict"


@pytest.mark.asyncio
async def test_detect_event_surge() -> None:
    event = _make_event(goldstein_scale=-1.0, geo_country="US")

    recent_result = MagicMock()
    recent_result.scalar.return_value = 30
    history_result = MagicMock()
    history_result.scalar.return_value = 14

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[recent_result, history_result])

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=AsyncMock(), db_session=session)
        anomalies = await monitor.detect_anomalies([event])

    assert len(anomalies) == 1
    assert anomalies[0].status == "anomaly"
    emitted_event = mock_bus.emit.call_args[0][0]
    assert emitted_event.payload["anomaly_type"] == "event_surge"


@pytest.mark.asyncio
async def test_detect_high_conflict_cameo() -> None:
    event = _make_event(goldstein_scale=-6.0, cameo_root="14")
    session = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=AsyncMock(), db_session=session)
        anomalies = await monitor.detect_anomalies([event])

    assert len(anomalies) == 1
    emitted_event = mock_bus.emit.call_args[0][0]
    assert emitted_event.payload["anomaly_type"] == "high_conflict_cameo"


@pytest.mark.asyncio
async def test_no_anomaly_normal_events() -> None:
    event = _make_event(goldstein_scale=1.5, cameo_root="02")
    session = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=AsyncMock(), db_session=session)
        anomalies = await monitor.detect_anomalies([event])

    assert anomalies == []
    mock_bus.emit.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_anomaly_emits_event() -> None:
    event = _make_event(goldstein_scale=-8.5, cameo_root="14")
    session = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=AsyncMock(), db_session=session)
        anomalies = await monitor.detect_anomalies([event])

    assert len(anomalies) == 1
    assert mock_bus.emit.await_count >= 1
    for call in mock_bus.emit.call_args_list:
        emitted = call.args[0]
        assert emitted.event_type == "gdelt.anomaly_detected"
