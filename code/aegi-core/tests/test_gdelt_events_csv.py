# Author: msq
"""GDELT Events CSV 客户端测试。"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock

import httpx
import pytest

from aegi_core.infra.gdelt_client import GDELTClient


@pytest.fixture
def gdelt_client() -> GDELTClient:
    return GDELTClient(proxy=None)


def _make_test_csv_row(**overrides) -> str:
    """构造一行 GDELT Events CSV（58 列 tab 分隔）。"""
    defaults = [""] * 58
    defaults[0] = overrides.get("global_event_id", "123456789")
    defaults[5] = overrides.get("actor1_code", "USA")
    defaults[6] = overrides.get("actor1_name", "UNITED STATES")
    defaults[7] = overrides.get("actor1_country", "US")
    defaults[15] = overrides.get("actor2_code", "IRN")
    defaults[16] = overrides.get("actor2_name", "IRAN")
    defaults[17] = overrides.get("actor2_country", "IR")
    defaults[26] = overrides.get("event_code", "0211")
    defaults[27] = overrides.get("event_base_code", "021")
    defaults[28] = overrides.get("event_root_code", "02")
    defaults[30] = str(overrides.get("goldstein_scale", 3.0))
    defaults[33] = str(overrides.get("avg_tone", -1.5))
    defaults[39] = str(overrides.get("geo_lat", 35.0))
    defaults[40] = str(overrides.get("geo_lon", 51.0))
    defaults[53] = overrides.get("source_url", "https://example.com/news")
    defaults[57] = overrides.get("date_added", "20260212120000")
    return "\t".join(defaults)


def _zip_csv(content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("events.csv", content)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_fetch_latest_events_success(gdelt_client: GDELTClient) -> None:
    csv_text = "\n".join(
        [
            _make_test_csv_row(
                global_event_id="1", event_root_code="02", goldstein_scale=2.3
            ),
            _make_test_csv_row(
                global_event_id="2", event_root_code="14", goldstein_scale=-8.2
            ),
        ]
    )
    csv_zip = _zip_csv(csv_text)

    update_resp = httpx.Response(
        200,
        text="http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip\n",
    )
    csv_resp = httpx.Response(200, content=csv_zip)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[update_resp, csv_resp])
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    events = await gdelt_client.fetch_latest_events(max_events=10)

    assert len(events) == 2
    assert events[0].global_event_id == "1"
    assert events[1].event_root_code == "14"
    assert events[1].goldstein_scale == -8.2


@pytest.mark.asyncio
async def test_fetch_latest_events_with_filters(gdelt_client: GDELTClient) -> None:
    csv_text = "\n".join(
        [
            _make_test_csv_row(
                global_event_id="1",
                actor1_country="US",
                actor2_country="US",
                event_root_code="02",
            ),
            _make_test_csv_row(
                global_event_id="2",
                actor1_country="CN",
                actor2_country="CN",
                event_root_code="14",
            ),
            _make_test_csv_row(
                global_event_id="3",
                actor1_country="IR",
                actor2_country="IR",
                event_root_code="14",
            ),
        ]
    )
    csv_zip = _zip_csv(csv_text)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.Response(
                200,
                text="http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip\n",
            ),
            httpx.Response(200, content=csv_zip),
        ]
    )
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    events = await gdelt_client.fetch_latest_events(
        country_filter={"IR"},
        cameo_root_filter={"14"},
    )

    assert len(events) == 1
    assert events[0].global_event_id == "3"


@pytest.mark.asyncio
async def test_fetch_latest_events_empty(gdelt_client: GDELTClient) -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.Response(
                200,
                text="http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip\n",
            ),
            httpx.Response(200, content=_zip_csv("")),
        ]
    )
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    events = await gdelt_client.fetch_latest_events()
    assert events == []


@pytest.mark.asyncio
async def test_fetch_latest_events_malformed(gdelt_client: GDELTClient) -> None:
    malformed = "\t\t\n1,2,3,4,5\n"
    valid = _make_test_csv_row(global_event_id="1001")
    csv_zip = _zip_csv(f"{malformed}{valid}\n")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.Response(
                200,
                text="http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip\n",
            ),
            httpx.Response(200, content=csv_zip),
        ]
    )
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    events = await gdelt_client.fetch_latest_events(max_events=10)

    assert len(events) == 1
    assert events[0].global_event_id == "1001"


@pytest.mark.asyncio
async def test_csv_tab_separated(gdelt_client: GDELTClient) -> None:
    comma_line = _make_test_csv_row(global_event_id="bad").replace("\t", ",")
    tab_line = _make_test_csv_row(global_event_id="ok")
    csv_zip = _zip_csv(f"{comma_line}\n{tab_line}\n")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.Response(
                200,
                text="http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip\n",
            ),
            httpx.Response(200, content=csv_zip),
        ]
    )
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    events = await gdelt_client.fetch_latest_events(max_events=10)

    assert len(events) == 1
    assert events[0].global_event_id == "ok"
