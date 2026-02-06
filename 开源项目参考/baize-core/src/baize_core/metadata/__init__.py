"""元数据管理模块。

提供 OpenMetadata 集成能力：
- 数据源注册
- 血缘追踪
- 标签管理
"""

from baize_core.metadata.openmetadata_client import (
    OpenMetadataClient,
    OpenMetadataConfig,
)

__all__ = [
    "OpenMetadataClient",
    "OpenMetadataConfig",
]
