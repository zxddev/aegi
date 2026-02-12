"""persona_generator 和多视角 API 测试。"""

import pytest
from unittest.mock import AsyncMock

from aegi_core.services.persona_generator import (
    _default_personas,
    generate_hypotheses_multi_perspective,
)


def test_default_personas():
    """_default_personas 返回 3 个 Persona 对象。"""
    personas = _default_personas()
    assert len(personas) == 3
    for p in personas:
        assert p.name
        assert p.perspective
        assert p.bias_tendency


@pytest.mark.asyncio
async def test_multi_perspective_skip_no_assertions():
    """没有 assertions → 返回空假设列表（生成了 persona 但没证据可分析）。"""
    llm = AsyncMock()
    llm.invoke = AsyncMock(return_value={"text": "[]"})
    result = await generate_hypotheses_multi_perspective(
        [],
        [],
        case_uid="case_1",
        llm=llm,
        persona_count=3,
    )
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_multi_perspective_api(tmp_path):
    """POST /cases/{uid}/analysis/multi_perspective 返回假设列表。"""
    from unittest.mock import patch
    from httpx import AsyncClient, ASGITransport
    from aegi_core.api.main import create_app

    app = create_app()

    mock_hypotheses = [
        {"hypothesis_text": "H1 test", "persona": "分析师A", "perspective": "视角A"},
        {"hypothesis_text": "H2 test", "persona": "分析师B", "perspective": "视角B"},
    ]

    with patch(
        "aegi_core.api.routes.persona.generate_hypotheses_multi_perspective",
        new_callable=AsyncMock,
        return_value=mock_hypotheses,
    ):
        # mock DB session
        mock_session = AsyncMock()
        mock_case = type("Case", (), {"uid": "case_1", "title": "test"})()
        mock_session.get = AsyncMock(return_value=mock_case)

        # mock scalars，用于 assertions 和 source_claims 查询
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all = lambda: []
        mock_result.scalars = lambda: mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        from aegi_core.api.deps import get_db_session, get_llm_client

        app.dependency_overrides[get_db_session] = lambda: mock_session
        app.dependency_overrides[get_llm_client] = lambda: AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/cases/case_1/analysis/multi_perspective",
                json={"persona_count": 2},
            )

        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "hypotheses" in data
    assert len(data["hypotheses"]) == 2
    assert "personas_used" in data
