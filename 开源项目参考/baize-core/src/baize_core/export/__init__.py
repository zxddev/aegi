"""证据包导出模块。

提供离线复核与共享能力：
- 导出格式：manifest.json + artifacts/ + chunks.json + evidence.json
- SHA256 校验
- trace_id 关联
- ZIP 打包
"""

from baize_core.export.evidence_pack import (
    EvidencePackExporter,
    ExportConfig,
    ExportResult,
)
from baize_core.export.manifest import (
    Manifest,
    ManifestEntry,
    create_manifest,
)

__all__ = [
    "EvidencePackExporter",
    "ExportConfig",
    "ExportResult",
    "Manifest",
    "ManifestEntry",
    "create_manifest",
]
