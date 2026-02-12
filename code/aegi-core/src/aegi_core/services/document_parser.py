"""文档解析服务。

从 PDF、DOCX、HTML、Markdown 文件中提取纯文本。
供 /parse_document API 使用，将上传文件转为文本后送入证据摄入流水线。
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 支持的 MIME 类型 → 解析器映射
SUPPORTED_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/html": "html",
    "text/markdown": "markdown",
    "text/plain": "plain",
}


def detect_format(filename: str, content_type: str = "") -> str:
    """根据文件名或 MIME 类型检测文档格式。"""
    if content_type in SUPPORTED_TYPES:
        return SUPPORTED_TYPES[content_type]
    ext = Path(filename).suffix.lower()
    return {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",
        ".html": "html",
        ".htm": "html",
        ".md": "markdown",
        ".txt": "plain",
    }.get(ext, "plain")


def parse_pdf(data: bytes) -> str:
    """从 PDF 字节中提取文本。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(data: bytes) -> str:
    """从 DOCX 字节中提取文本。"""
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_html(data: bytes) -> str:
    """从 HTML 提取文本，用 markdownify 保留结构。"""
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(data, "html.parser")
    # 移除 script/style 等无关标签
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return md(str(soup), strip=["img", "a"])


def parse_markdown(data: bytes) -> str:
    """Markdown 本身就是文本，直接解码。"""
    return data.decode("utf-8", errors="replace")


def parse_plain(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


_PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "html": parse_html,
    "markdown": parse_markdown,
    "plain": parse_plain,
}


def parse_document(data: bytes, *, filename: str = "", content_type: str = "") -> str:
    """解析文档并返回提取的文本。

    Args:
        data: 原始文件字节。
        filename: 原始文件名（用于格式检测）。
        content_type: MIME 类型（用于格式检测）。

    Returns:
        提取的纯文本。
    """
    fmt = detect_format(filename, content_type)
    parser = _PARSERS.get(fmt, parse_plain)
    text = parser(data)
    return text.strip()


def chunk_text(text: str, *, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    """将文本切分为带重叠的块，用于证据摄入。"""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start = end - overlap
    return chunks
