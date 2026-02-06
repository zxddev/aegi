"""Unstructured 文档解析适配器。

Unstructured 是一个开源的文档解析库，支持多种格式的文档解析。
此适配器提供与 Unstructured API 的集成。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any

import httpx

from baize_core.schemas.evidence import AnchorType, Chunk, ChunkAnchor

logger = logging.getLogger(__name__)


class PartitionStrategy(str, Enum):
    """解析策略。"""

    AUTO = "auto"  # 自动选择
    FAST = "fast"  # 快速解析（基于规则）
    HI_RES = "hi_res"  # 高精度解析（使用模型）
    OCR_ONLY = "ocr_only"  # 仅 OCR


class ChunkingStrategy(str, Enum):
    """分块策略。"""

    BASIC = "basic"  # 基本分块
    BY_TITLE = "by_title"  # 按标题分块
    BY_PAGE = "by_page"  # 按页面分块
    BY_SIMILARITY = "by_similarity"  # 按相似度分块


class ElementType(str, Enum):
    """元素类型。"""

    TITLE = "Title"
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    TABLE = "Table"
    IMAGE = "Image"
    FORMULA = "Formula"
    FOOTER = "Footer"
    HEADER = "Header"
    PAGE_NUMBER = "PageNumber"
    UNCATEGORIZED_TEXT = "UncategorizedText"
    FIGURE_CAPTION = "FigureCaption"
    TABLE_CAPTION = "TableCaption"
    ADDRESS = "Address"
    EMAIL_ADDRESS = "EmailAddress"


@dataclass(frozen=True)
class UnstructuredConfig:
    """Unstructured 配置。"""

    api_url: str  # Unstructured API 地址
    api_key: str | None = None  # API Key（如果需要）
    timeout_seconds: int = 60
    verify_ssl: bool = True
    # 默认解析策略
    default_strategy: PartitionStrategy = PartitionStrategy.AUTO
    # 默认分块策略
    default_chunking_strategy: ChunkingStrategy = ChunkingStrategy.BY_TITLE
    # 默认分块大小
    default_chunk_size: int = 500
    # 默认分块重叠
    default_chunk_overlap: int = 50


@dataclass
class DocumentElement:
    """文档元素。"""

    element_id: str
    element_type: ElementType
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # 定位信息
    page_number: int | None = None
    coordinates: dict[str, Any] | None = None
    # 父子关系
    parent_id: str | None = None


@dataclass
class ParseResult:
    """解析结果。"""

    elements: list[DocumentElement]
    total_pages: int | None = None
    total_elements: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkResult:
    """分块结果。"""

    chunks: list[Chunk]
    total_chunks: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class UnstructuredClient:
    """Unstructured 客户端。

    支持功能：
    - 多种文档格式解析（PDF、Office、HTML 等）
    - 多种解析策略
    - 文本分块
    - 表格提取
    """

    def __init__(self, config: UnstructuredConfig) -> None:
        """初始化客户端。

        Args:
            config: Unstructured 配置
        """
        self._config = config

    async def parse_file(
        self,
        file_content: bytes,
        filename: str,
        *,
        content_type: str | None = None,
        strategy: PartitionStrategy | None = None,
        languages: list[str] | None = None,
        extract_images: bool = False,
        extract_tables: bool = True,
        include_page_breaks: bool = True,
    ) -> ParseResult:
        """解析文件。

        Args:
            file_content: 文件内容
            filename: 文件名
            content_type: MIME 类型
            strategy: 解析策略
            languages: 语言列表（用于 OCR）
            extract_images: 是否提取图片
            extract_tables: 是否提取表格
            include_page_breaks: 是否包含分页符

        Returns:
            解析结果
        """
        effective_strategy = strategy or self._config.default_strategy

        # 构建请求
        files = {
            "files": (
                filename,
                file_content,
                content_type or "application/octet-stream",
            )
        }
        data: dict[str, Any] = {
            "strategy": effective_strategy.value,
            "include_page_breaks": str(include_page_breaks).lower(),
        }

        if languages:
            data["languages"] = ",".join(languages)
        if extract_images:
            data["extract_images_in_pdf"] = "true"
        if extract_tables:
            data["extract_tables_as_cells"] = "true"

        headers = self._build_headers()

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.post(
                self._config.api_url,
                files=files,
                data=data,
                headers=headers,
            )
            response.raise_for_status()
            elements_data = response.json()
            return self._parse_elements(elements_data)

    async def parse_and_chunk(
        self,
        file_content: bytes,
        filename: str,
        artifact_uid: str,
        *,
        content_type: str | None = None,
        strategy: PartitionStrategy | None = None,
        chunking_strategy: ChunkingStrategy | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> ChunkResult:
        """解析文件并分块。

        Args:
            file_content: 文件内容
            filename: 文件名
            artifact_uid: Artifact UID
            content_type: MIME 类型
            strategy: 解析策略
            chunking_strategy: 分块策略
            chunk_size: 分块大小
            chunk_overlap: 分块重叠

        Returns:
            分块结果
        """
        parse_result = await self.parse_file(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            strategy=strategy,
        )

        effective_chunking_strategy = (
            chunking_strategy or self._config.default_chunking_strategy
        )
        effective_chunk_size = chunk_size or self._config.default_chunk_size
        effective_chunk_overlap = chunk_overlap or self._config.default_chunk_overlap

        chunks = self._create_chunks(
            elements=parse_result.elements,
            artifact_uid=artifact_uid,
            strategy=effective_chunking_strategy,
            max_chunk_size=effective_chunk_size,
            overlap=effective_chunk_overlap,
        )

        return ChunkResult(
            chunks=chunks,
            total_chunks=len(chunks),
            metadata={
                "total_elements": parse_result.total_elements,
                "total_pages": parse_result.total_pages,
                "chunking_strategy": effective_chunking_strategy.value,
                "chunk_size": effective_chunk_size,
            },
        )

    async def parse_text(
        self,
        text: str,
        *,
        chunking_strategy: ChunkingStrategy | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        artifact_uid: str | None = None,
    ) -> ChunkResult:
        """解析纯文本并分块。

        Args:
            text: 文本内容
            chunking_strategy: 分块策略
            chunk_size: 分块大小
            chunk_overlap: 分块重叠
            artifact_uid: Artifact UID

        Returns:
            分块结果
        """
        effective_chunk_size = chunk_size or self._config.default_chunk_size
        effective_chunk_overlap = chunk_overlap or self._config.default_chunk_overlap
        effective_artifact_uid = (
            artifact_uid or f"art_{sha256(text.encode()).hexdigest()[:16]}"
        )

        # 简单分块逻辑
        chunks = self._chunk_text(
            text=text,
            artifact_uid=effective_artifact_uid,
            max_chunk_size=effective_chunk_size,
            overlap=effective_chunk_overlap,
        )

        return ChunkResult(
            chunks=chunks,
            total_chunks=len(chunks),
            metadata={
                "text_length": len(text),
                "chunk_size": effective_chunk_size,
            },
        )

    def _build_headers(self) -> dict[str, str]:
        """构建请求头。"""
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["unstructured-api-key"] = self._config.api_key
        return headers

    def _parse_elements(self, elements_data: list[dict[str, Any]]) -> ParseResult:
        """解析元素列表。"""
        elements: list[DocumentElement] = []
        max_page = 0

        for item in elements_data:
            element = self._parse_element(item)
            if element:
                elements.append(element)
                if element.page_number:
                    max_page = max(max_page, element.page_number)

        return ParseResult(
            elements=elements,
            total_pages=max_page if max_page > 0 else None,
            total_elements=len(elements),
        )

    def _parse_element(self, item: dict[str, Any]) -> DocumentElement | None:
        """解析单个元素。"""
        text = item.get("text", "")
        if not text.strip():
            return None

        element_type_str = item.get("type", "UncategorizedText")
        try:
            element_type = ElementType(element_type_str)
        except ValueError:
            element_type = ElementType.UNCATEGORIZED_TEXT

        element_id = item.get("element_id", "")
        metadata = item.get("metadata", {})

        # 定位信息
        page_number = metadata.get("page_number")
        coordinates = metadata.get("coordinates")
        parent_id = metadata.get("parent_id")

        return DocumentElement(
            element_id=element_id,
            element_type=element_type,
            text=text,
            metadata=metadata,
            page_number=page_number,
            coordinates=coordinates,
            parent_id=parent_id,
        )

    def _create_chunks(
        self,
        elements: list[DocumentElement],
        artifact_uid: str,
        strategy: ChunkingStrategy,
        max_chunk_size: int,
        overlap: int,
    ) -> list[Chunk]:
        """根据策略创建分块。"""
        if strategy == ChunkingStrategy.BY_TITLE:
            return self._chunk_by_title(elements, artifact_uid, max_chunk_size, overlap)
        elif strategy == ChunkingStrategy.BY_PAGE:
            return self._chunk_by_page(elements, artifact_uid, max_chunk_size, overlap)
        else:
            # 基本分块
            all_text = "\n".join(e.text for e in elements)
            return self._chunk_text(all_text, artifact_uid, max_chunk_size, overlap)

    def _chunk_by_title(
        self,
        elements: list[DocumentElement],
        artifact_uid: str,
        max_chunk_size: int,
        overlap: int,
    ) -> list[Chunk]:
        """按标题分块。"""
        chunks: list[Chunk] = []
        current_section: list[str] = []
        for element in elements:
            if element.element_type == ElementType.TITLE:
                # 保存当前节
                if current_section:
                    section_text = "\n".join(current_section)
                    section_chunks = self._chunk_text(
                        section_text, artifact_uid, max_chunk_size, overlap
                    )
                    chunks.extend(section_chunks)
                # 开始新节
                current_section = [element.text]
            else:
                current_section.append(element.text)

        # 保存最后一节
        if current_section:
            section_text = "\n".join(current_section)
            section_chunks = self._chunk_text(
                section_text, artifact_uid, max_chunk_size, overlap
            )
            chunks.extend(section_chunks)

        return chunks

    def _chunk_by_page(
        self,
        elements: list[DocumentElement],
        artifact_uid: str,
        max_chunk_size: int,
        overlap: int,
    ) -> list[Chunk]:
        """按页面分块。"""
        page_texts: dict[int, list[str]] = {}

        for element in elements:
            page = element.page_number or 1
            if page not in page_texts:
                page_texts[page] = []
            page_texts[page].append(element.text)

        chunks: list[Chunk] = []
        for _page, texts in sorted(page_texts.items()):
            page_text = "\n".join(texts)
            page_chunks = self._chunk_text(
                page_text, artifact_uid, max_chunk_size, overlap
            )
            chunks.extend(page_chunks)

        return chunks

    def _chunk_text(
        self,
        text: str,
        artifact_uid: str,
        max_chunk_size: int,
        overlap: int,
    ) -> list[Chunk]:
        """基本文本分块。"""
        if not text.strip():
            return []

        chunks: list[Chunk] = []
        start = 0
        length = len(text)

        while start < length:
            end = min(start + max_chunk_size, length)
            chunk_text = text[start:end]

            # 计算哈希
            text_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
            chunk_uid = (
                f"chk_{sha256(f'{artifact_uid}:{start}:{end}'.encode()).hexdigest()}"
            )

            chunk = Chunk(
                chunk_uid=chunk_uid,
                artifact_uid=artifact_uid,
                anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref=f"{start}-{end}"),
                text=chunk_text,
                text_sha256=text_hash,
            )
            chunks.append(chunk)

            if end == length:
                break
            start = end - overlap

        return chunks


def create_unstructured_client(
    api_url: str,
    api_key: str | None = None,
    timeout_seconds: int = 60,
) -> UnstructuredClient:
    """创建 Unstructured 客户端的便捷函数。

    Args:
        api_url: API 地址
        api_key: API Key
        timeout_seconds: 超时时间

    Returns:
        Unstructured 客户端实例
    """
    config = UnstructuredConfig(
        api_url=api_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    return UnstructuredClient(config)
