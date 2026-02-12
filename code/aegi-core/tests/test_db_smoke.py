# Author: msq
import sqlalchemy as sa

from aegi_core.db.session import ENGINE
from conftest import requires_postgres

pytestmark = requires_postgres


async def test_db_select_1() -> None:
    async with ENGINE.connect() as conn:
        result = await conn.execute(sa.text("select 1"))
        assert result.scalar_one() == 1
