"""审计落地。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class AuditSink(Protocol):
    """审计落地协议。"""

    async def write(self, record: BaseModel) -> None:
        """写入审计记录。"""


class JsonlAuditSink:
    """JSONL 审计落地。"""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def write(self, record: BaseModel) -> None:
        """追加写入一行 JSON。"""

        payload = record.model_dump(mode="json")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")
