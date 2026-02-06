"""MinIO Artifact 存储。

实现完整的对象存储功能：上传、下载、删除、列表、元数据查询。
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import anyio
from minio import Minio
from pydantic import BaseModel, Field


class ObjectInfo(BaseModel):
    """对象信息。"""

    object_name: str = Field(description="对象名称")
    size: int = Field(description="对象大小（字节）")
    content_type: str | None = Field(default=None, description="内容类型")
    last_modified: datetime | None = Field(default=None, description="最后修改时间")
    etag: str | None = Field(default=None, description="ETag")
    metadata: dict[str, str] = Field(default_factory=dict, description="元数据")


class ObjectListResult(BaseModel):
    """对象列表结果。"""

    objects: list[ObjectInfo] = Field(default_factory=list)
    prefix: str | None = None
    is_truncated: bool = False
    next_marker: str | None = None


@dataclass
class MinioArtifactStore:
    """MinIO Artifact 存储。

    实现完整的对象存储功能。
    """

    client: Minio
    bucket: str

    # ==================== 桶管理 ====================

    async def ensure_bucket(self) -> None:
        """确保桶存在。"""
        exists = await anyio.to_thread.run_sync(self.client.bucket_exists, self.bucket)
        if not exists:
            raise ValueError(f"MinIO 桶不存在: {self.bucket}")

    async def create_bucket_if_not_exists(self) -> bool:
        """创建桶（如果不存在）。

        Returns:
            True 表示创建了新桶，False 表示桶已存在
        """
        exists = await anyio.to_thread.run_sync(self.client.bucket_exists, self.bucket)
        if exists:
            return False
        await anyio.to_thread.run_sync(self.client.make_bucket, self.bucket)
        return True

    # ==================== 上传 ====================

    async def put_base64(
        self, *, object_name: str, payload_base64: str, content_type: str
    ) -> None:
        """上传 Base64 内容。"""
        raw = base64.b64decode(payload_base64, validate=True)
        await self.put_bytes(
            object_name=object_name, payload=raw, content_type=content_type
        )

    async def put_bytes(
        self,
        *,
        object_name: str,
        payload: bytes,
        content_type: str,
        metadata: dict[str, str | list[str] | tuple[str]] | None = None,
    ) -> None:
        """上传二进制内容。"""

        def _upload() -> None:
            with io.BytesIO(payload) as handle:
                self.client.put_object(
                    self.bucket,
                    object_name,
                    handle,
                    length=len(payload),
                    content_type=content_type,
                    metadata=metadata,
                )

        await anyio.to_thread.run_sync(_upload)

    async def put_text(
        self,
        *,
        object_name: str,
        text: str,
        content_type: str = "text/plain",
        metadata: dict[str, str | list[str] | tuple[str]] | None = None,
    ) -> None:
        """上传文本内容。"""
        await self.put_bytes(
            object_name=object_name,
            payload=text.encode("utf-8"),
            content_type=content_type,
            metadata=metadata,
        )

    # ==================== 下载 ====================

    async def get_bytes(self, object_name: str) -> bytes:
        """下载对象为字节。

        Args:
            object_name: 对象名称

        Returns:
            对象内容

        Raises:
            ValueError: 对象不存在
        """

        def _download() -> bytes:
            response = self.client.get_object(self.bucket, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await anyio.to_thread.run_sync(_download)

    async def get_text(self, object_name: str, encoding: str = "utf-8") -> str:
        """下载对象为文本。

        Args:
            object_name: 对象名称
            encoding: 文本编码

        Returns:
            对象内容
        """
        data = await self.get_bytes(object_name)
        return data.decode(encoding)

    async def get_base64(self, object_name: str) -> str:
        """下载对象为 Base64 字符串。

        Args:
            object_name: 对象名称

        Returns:
            Base64 编码的对象内容
        """
        data = await self.get_bytes(object_name)
        return base64.b64encode(data).decode("ascii")

    async def download_to_file(self, object_name: str, file_path: str) -> None:
        """下载对象到文件。

        Args:
            object_name: 对象名称
            file_path: 本地文件路径
        """

        def _download() -> None:
            self.client.fget_object(self.bucket, object_name, file_path)

        await anyio.to_thread.run_sync(_download)

    # ==================== 删除 ====================

    async def delete(self, object_name: str) -> bool:
        """删除对象。

        Args:
            object_name: 对象名称

        Returns:
            True 表示删除成功
        """

        def _delete() -> bool:
            self.client.remove_object(self.bucket, object_name)
            return True

        return await anyio.to_thread.run_sync(_delete)

    async def delete_many(self, object_names: list[str]) -> int:
        """批量删除对象。

        Args:
            object_names: 对象名称列表

        Returns:
            删除的对象数量
        """
        from minio.deleteobjects import DeleteObject

        def _delete_many() -> int:
            delete_list = [DeleteObject(name) for name in object_names]
            errors = list(self.client.remove_objects(self.bucket, delete_list))
            return len(object_names) - len(errors)

        return await anyio.to_thread.run_sync(_delete_many)

    async def delete_prefix(self, prefix: str) -> int:
        """删除指定前缀的所有对象。

        Args:
            prefix: 对象前缀

        Returns:
            删除的对象数量
        """
        objects = await self.list_objects(prefix=prefix, recursive=True)
        object_names = [obj.object_name for obj in objects.objects]
        if not object_names:
            return 0
        return await self.delete_many(object_names)

    # ==================== 列表 ====================

    async def list_objects(
        self,
        *,
        prefix: str | None = None,
        recursive: bool = False,
        max_keys: int = 1000,
    ) -> ObjectListResult:
        """列出对象。

        Args:
            prefix: 对象前缀
            recursive: 是否递归列出
            max_keys: 最大返回数量

        Returns:
            对象列表结果
        """

        def _list() -> ObjectListResult:
            objects_iter = self.client.list_objects(
                self.bucket,
                prefix=prefix,
                recursive=recursive,
            )
            objects: list[ObjectInfo] = []
            count = 0
            for obj in objects_iter:
                if count >= max_keys:
                    return ObjectListResult(
                        objects=objects,
                        prefix=prefix,
                        is_truncated=True,
                        next_marker=obj.object_name,
                    )
                objects.append(
                    ObjectInfo(
                        object_name=obj.object_name or "",
                        size=obj.size or 0,
                        content_type=obj.content_type,
                        last_modified=obj.last_modified,
                        etag=obj.etag,
                    )
                )
                count += 1
            return ObjectListResult(objects=objects, prefix=prefix)

        return await anyio.to_thread.run_sync(_list)

    async def list_all_objects(
        self,
        *,
        prefix: str | None = None,
        recursive: bool = True,
    ) -> list[ObjectInfo]:
        """列出所有对象（无分页限制）。

        Args:
            prefix: 对象前缀
            recursive: 是否递归列出

        Returns:
            对象信息列表
        """

        def _list_all() -> list[ObjectInfo]:
            objects_iter = self.client.list_objects(
                self.bucket,
                prefix=prefix,
                recursive=recursive,
            )
            return [
                ObjectInfo(
                    object_name=obj.object_name or "",
                    size=obj.size or 0,
                    content_type=obj.content_type,
                    last_modified=obj.last_modified,
                    etag=obj.etag,
                )
                for obj in objects_iter
            ]

        return await anyio.to_thread.run_sync(_list_all)

    # ==================== 元数据 ====================

    async def stat_object(self, object_name: str) -> ObjectInfo | None:
        """获取对象元数据。

        Args:
            object_name: 对象名称

        Returns:
            对象信息，不存在则返回 None
        """

        def _stat() -> ObjectInfo | None:
            try:
                stat = self.client.stat_object(self.bucket, object_name)
                return ObjectInfo(
                    object_name=stat.object_name or object_name,
                    size=stat.size or 0,
                    content_type=stat.content_type,
                    last_modified=stat.last_modified,
                    etag=stat.etag,
                    metadata=dict(stat.metadata) if stat.metadata else {},
                )
            except Exception:
                return None

        return await anyio.to_thread.run_sync(_stat)

    async def exists(self, object_name: str) -> bool:
        """检查对象是否存在。

        Args:
            object_name: 对象名称

        Returns:
            是否存在
        """
        stat = await self.stat_object(object_name)
        return stat is not None

    # ==================== 工具方法 ====================

    async def copy_object(
        self,
        source_object: str,
        dest_object: str,
        dest_bucket: str | None = None,
    ) -> None:
        """复制对象。

        Args:
            source_object: 源对象名称
            dest_object: 目标对象名称
            dest_bucket: 目标桶（默认同桶）
        """
        from minio.commonconfig import CopySource

        def _copy() -> None:
            source = CopySource(self.bucket, source_object)
            target_bucket = dest_bucket or self.bucket
            self.client.copy_object(target_bucket, dest_object, source)

        await anyio.to_thread.run_sync(_copy)

    async def get_presigned_url(
        self,
        object_name: str,
        expires_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """获取预签名 URL。

        Args:
            object_name: 对象名称
            expires_seconds: 过期时间（秒）
            method: HTTP 方法（GET/PUT）

        Returns:
            预签名 URL
        """
        from datetime import timedelta

        def _get_url() -> str:
            if method.upper() == "PUT":
                return self.client.presigned_put_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(seconds=expires_seconds),
                )
            return self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(seconds=expires_seconds),
            )

        return await anyio.to_thread.run_sync(_get_url)

    async def get_storage_ref(self, object_name: str) -> str:
        """获取存储引用 URI。

        Args:
            object_name: 对象名称

        Returns:
            存储引用 URI（minio://bucket/object）
        """
        return f"minio://{self.bucket}/{object_name}"


@dataclass
class MinIOStore:
    """MinIO 存储兼容封装。"""

    endpoint: str
    access_key: str
    secret_key: str
    secure: bool = True
    _client: Minio | None = None

    async def connect(self) -> None:
        """初始化 MinIO 客户端。"""
        self._client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    async def close(self) -> None:
        """关闭客户端连接。"""
        self._client = None

    async def upload_content(
        self,
        *,
        bucket: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str | list[str] | tuple[str]] | None = None,
    ) -> str:
        """上传内容并返回存储引用。"""
        if self._client is None:
            raise RuntimeError("MinIO 客户端未初始化")
        object_name = uuid4().hex
        store = MinioArtifactStore(client=self._client, bucket=bucket)
        await store.put_bytes(
            object_name=object_name,
            payload=content,
            content_type=content_type,
            metadata=metadata,
        )
        return await store.get_storage_ref(object_name)

    async def download_content(self, storage_ref: str) -> bytes:
        """下载存储引用对应的内容。"""
        if self._client is None:
            raise RuntimeError("MinIO 客户端未初始化")
        if not storage_ref.startswith("minio://"):
            raise ValueError("存储引用格式无效")
        path = storage_ref.removeprefix("minio://")
        bucket, _, object_name = path.partition("/")
        if not bucket or not object_name:
            raise ValueError("存储引用格式无效")
        store = MinioArtifactStore(client=self._client, bucket=bucket)
        return await store.get_bytes(object_name)
