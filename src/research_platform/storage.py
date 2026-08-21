from __future__ import annotations

import asyncio
import io
from pathlib import Path

from minio import Minio

from .config import Settings


class ObjectStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.local_root = Path("data/artifacts")
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    async def ensure_bucket(self) -> None:
        if self.settings.testing:
            self.local_root.mkdir(parents=True, exist_ok=True)
            return
        exists = await asyncio.to_thread(self.client.bucket_exists, self.settings.minio_bucket)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, self.settings.minio_bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await self.ensure_bucket()
        if self.settings.testing:
            path = self.local_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return key
        await asyncio.to_thread(
            self.client.put_object, self.settings.minio_bucket, key, io.BytesIO(data), len(data),
            content_type=content_type,
        )
        return key

    async def get(self, key: str) -> bytes:
        if self.settings.testing:
            return (self.local_root / key).read_bytes()
        response = await asyncio.to_thread(self.client.get_object, self.settings.minio_bucket, key)
        try:
            return await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()

    async def list_keys(self, prefix: str) -> list[str]:
        """Every object under a prefix.

        Purging a run has to reach objects the database never names: source snapshots are
        keyed by content hash under ``<run_id>/sources/`` and only the run that wrote them
        knows they exist.
        """
        if self.settings.testing:
            root = self.local_root / prefix
            if not root.exists():
                return []
            return [
                str(path.relative_to(self.local_root)).replace("\\", "/")
                for path in root.rglob("*")
                if path.is_file()
            ]

        def _walk() -> list[str]:
            return [
                item.object_name
                for item in self.client.list_objects(
                    self.settings.minio_bucket, prefix=prefix, recursive=True
                )
            ]

        return await asyncio.to_thread(_walk)

    async def delete(self, key: str) -> None:
        if self.settings.testing:
            path = self.local_root / key
            if path.exists():
                path.unlink()
            return
        await asyncio.to_thread(
            self.client.remove_object,
            self.settings.minio_bucket,
            key,
        )
