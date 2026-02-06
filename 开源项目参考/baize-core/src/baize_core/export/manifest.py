"""证据包清单生成。

- 清单格式定义
- SHA256 校验
- trace_id 关联
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ManifestEntry:
    """清单条目。"""

    path: str  # 文件相对路径
    sha256: str  # SHA256 哈希
    size_bytes: int  # 文件大小
    content_type: str = ""  # 内容类型


@dataclass
class Manifest:
    """证据包清单。"""

    version: str = "1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    task_id: str = ""
    trace_id: str = ""
    exporter_version: str = "baize-core/1.0"

    # 统计信息
    artifact_count: int = 0
    chunk_count: int = 0
    evidence_count: int = 0
    report_count: int = 0

    # 文件列表
    entries: list[ManifestEntry] = field(default_factory=list)

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "exporter_version": self.exporter_version,
            "statistics": {
                "artifact_count": self.artifact_count,
                "chunk_count": self.chunk_count,
                "evidence_count": self.evidence_count,
                "report_count": self.report_count,
            },
            "entries": [
                {
                    "path": e.path,
                    "sha256": e.sha256,
                    "size_bytes": e.size_bytes,
                    "content_type": e.content_type,
                }
                for e in self.entries
            ],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """从字典创建。"""
        stats = data.get("statistics", {})
        entries = [
            ManifestEntry(
                path=e["path"],
                sha256=e["sha256"],
                size_bytes=e["size_bytes"],
                content_type=e.get("content_type", ""),
            )
            for e in data.get("entries", [])
        ]
        return cls(
            version=data.get("version", "1.0"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(UTC),
            task_id=data.get("task_id", ""),
            trace_id=data.get("trace_id", ""),
            exporter_version=data.get("exporter_version", ""),
            artifact_count=stats.get("artifact_count", 0),
            chunk_count=stats.get("chunk_count", 0),
            evidence_count=stats.get("evidence_count", 0),
            report_count=stats.get("report_count", 0),
            entries=entries,
            metadata=data.get("metadata", {}),
        )

    def add_entry(
        self,
        path: str,
        content: bytes,
        content_type: str = "",
    ) -> ManifestEntry:
        """添加条目。"""
        sha256 = compute_sha256(content)
        entry = ManifestEntry(
            path=path,
            sha256=sha256,
            size_bytes=len(content),
            content_type=content_type,
        )
        self.entries.append(entry)
        return entry

    def verify_entry(self, path: str, content: bytes) -> bool:
        """验证条目。"""
        for entry in self.entries:
            if entry.path == path:
                return compute_sha256(content) == entry.sha256
        return False

    def get_total_size(self) -> int:
        """获取总大小。"""
        return sum(e.size_bytes for e in self.entries)


def compute_sha256(content: bytes) -> str:
    """计算 SHA256 哈希。"""
    return hashlib.sha256(content).hexdigest()


def create_manifest(
    task_id: str,
    trace_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> Manifest:
    """创建新清单。

    Args:
        task_id: 任务 ID
        trace_id: 追踪 ID
        metadata: 额外元数据

    Returns:
        Manifest 实例
    """
    return Manifest(
        task_id=task_id,
        trace_id=trace_id,
        metadata=metadata or {},
    )
