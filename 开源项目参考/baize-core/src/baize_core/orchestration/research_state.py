"""研究状态封装。

将去重集合和结果集合封装为统一的状态对象，
消除函数参数过多和嵌套过深的问题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from baize_core.schemas.evidence import Artifact, Chunk, Evidence


@dataclass
class ResearchState:
    """研究状态（封装去重和结果集合）。

    职责：
    1. 管理证据链结果（artifact/chunk/evidence）
    2. 管理去重集合（URL/域名/内容哈希）
    3. 提供批量添加和去重判断方法
    """

    # 结果集合
    evidence_map: dict[str, Evidence] = field(default_factory=dict)
    chunk_map: dict[str, Chunk] = field(default_factory=dict)
    artifact_map: dict[str, Artifact] = field(default_factory=dict)

    # 去重集合
    seen_urls: set[str] = field(default_factory=set)
    seen_domains: set[str] = field(default_factory=set)
    seen_hashes: set[str] = field(default_factory=set)

    def add_artifact(self, artifact: Artifact) -> None:
        """添加 Artifact 并更新去重集合。

        Args:
            artifact: 要添加的 Artifact
        """
        self.artifact_map[artifact.artifact_uid] = artifact
        self.seen_hashes.add(artifact.content_sha256.removeprefix("sha256:"))

    def add_chunk(self, chunk: Chunk) -> None:
        """添加 Chunk。

        Args:
            chunk: 要添加的 Chunk
        """
        self.chunk_map[chunk.chunk_uid] = chunk

    def add_evidence(self, evidence: Evidence, dedupe_by_domain: bool = False) -> None:
        """添加 Evidence 并更新去重集合。

        Args:
            evidence: 要添加的 Evidence
            dedupe_by_domain: 是否按域名去重
        """
        self.evidence_map[evidence.evidence_uid] = evidence
        if evidence.uri:
            self.seen_urls.add(evidence.uri)
            if dedupe_by_domain:
                domain = urlparse(evidence.uri).netloc
                if domain:
                    self.seen_domains.add(domain)

    def merge_batch(
        self,
        artifacts: list[Artifact],
        chunks: list[Chunk],
        evidence_items: list[Evidence],
        dedupe_by_domain: bool = False,
    ) -> None:
        """批量添加证据链数据。

        Args:
            artifacts: Artifact 列表
            chunks: Chunk 列表
            evidence_items: Evidence 列表
            dedupe_by_domain: 是否按域名去重
        """
        for artifact in artifacts:
            self.add_artifact(artifact)
        for chunk in chunks:
            self.add_chunk(chunk)
        for evidence in evidence_items:
            self.add_evidence(evidence, dedupe_by_domain)

    def is_url_seen(self, url: str | None) -> bool:
        """检查 URL 是否已见。

        Args:
            url: 要检查的 URL

        Returns:
            是否已见
        """
        if not url:
            return False
        return url in self.seen_urls

    def is_domain_seen(self, url: str | None) -> bool:
        """检查域名是否已见。

        Args:
            url: 要检查的 URL

        Returns:
            域名是否已见
        """
        if not url:
            return False
        domain = urlparse(url).netloc
        if not domain:
            return False
        return domain in self.seen_domains

    def is_hash_seen(self, content_sha256: str) -> bool:
        """检查内容哈希是否已见。

        Args:
            content_sha256: 内容哈希

        Returns:
            是否已见
        """
        normalized = content_sha256.removeprefix("sha256:")
        return normalized in self.seen_hashes

    @property
    def evidence_count(self) -> int:
        """获取证据数量。"""
        return len(self.evidence_map)

    @property
    def evidence_list(self) -> list[Evidence]:
        """获取证据列表。"""
        return list(self.evidence_map.values())

    @property
    def chunk_list(self) -> list[Chunk]:
        """获取 Chunk 列表。"""
        return list(self.chunk_map.values())

    @property
    def artifact_list(self) -> list[Artifact]:
        """获取 Artifact 列表。"""
        return list(self.artifact_map.values())
