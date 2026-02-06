# Author: msq
"""MinIO artifact store for AEGI."""

from __future__ import annotations

import io
from dataclasses import dataclass
from uuid import uuid4

import anyio
from minio import Minio


@dataclass
class MinioStore:
    """MinIO object storage."""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool = False
    _client: Minio | None = None

    async def connect(self) -> None:
        self._client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )
        exists = await anyio.to_thread.run_sync(self._client.bucket_exists, self.bucket)
        if not exists:
            await anyio.to_thread.run_sync(self._client.make_bucket, self.bucket)

    async def close(self) -> None:
        self._client = None

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        assert self._client is not None

        def _upload() -> None:
            with io.BytesIO(data) as buf:
                self._client.put_object(
                    self.bucket, object_name, buf, len(data), content_type=content_type
                )  # type: ignore[union-attr]

        await anyio.to_thread.run_sync(_upload)
        return f"minio://{self.bucket}/{object_name}"

    async def get_bytes(self, object_name: str) -> bytes:
        assert self._client is not None

        def _download() -> bytes:
            resp = self._client.get_object(self.bucket, object_name)  # type: ignore[union-attr]
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        return await anyio.to_thread.run_sync(_download)

    async def delete(self, object_name: str) -> None:
        assert self._client is not None
        await anyio.to_thread.run_sync(self._client.remove_object, self.bucket, object_name)

    async def exists(self, object_name: str) -> bool:
        assert self._client is not None

        def _stat() -> bool:
            try:
                self._client.stat_object(self.bucket, object_name)  # type: ignore[union-attr]
                return True
            except Exception:
                return False

        return await anyio.to_thread.run_sync(_stat)

    async def upload_artifact(
        self, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Upload with auto-generated name, return storage_ref."""
        name = uuid4().hex
        return await self.put_bytes(name, data, content_type)
