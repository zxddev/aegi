# Author: msq
"""init – 无表创建，仅占位。

Revision ID: bc5052692a40
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "bc5052692a40"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # 初始占位，表在后续迁移中创建


def downgrade() -> None:
    pass
