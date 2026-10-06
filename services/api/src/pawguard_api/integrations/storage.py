"""Private object storage (Supabase Storage REST API) with a server-side key.

Only the API and worker call this; browsers receive single-object signed URLs. Storage enforces only the
*declared* Content-Type and size — contents are validated from bytes by the worker before any record may use
them (ADR 0004).
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from pawguard_api.errors import ServiceUnavailable
from pawguard_api.settings import get_settings

SIGNED_UPLOAD_TTL_SECONDS = 7200  # fixed by Supabase Storage for signed upload URLs
DOWNLOAD_TTL_SECONDS = 120


@dataclass
class ObjectInfo:
    size: int
    content_type: str | None


class StorageBackend(Protocol):
    bucket: str

    def signed_upload_url(self, key: str) -> str: ...
    def info(self, key: str) -> ObjectInfo | None: ...
    def signed_download_urls(self, keys: list[str], ttl: int = DOWNLOAD_TTL_SECONDS) -> dict[str, str]: ...
    def download(self, key: str, max_bytes: int) -> bytes: ...
    def upload(self, key: str, data: bytes, content_type: str) -> None: ...
    def remove(self, keys: list[str]) -> None: ...


class SupabaseStorage:
    def __init__(self, base_url: str, public_url: str, secret_key: str, bucket: str) -> None:
        self._base = base_url.rstrip("/") + "/storage/v1"
        self._public = public_url.rstrip("/") + "/storage/v1"
        self._headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
        self.bucket = bucket
        self._client = httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))

    def _req(self, method: str, path: str, **kw) -> httpx.Response:  # type: ignore[no-untyped-def]
        try:
            return self._client.request(method, self._base + path, headers={**self._headers, **kw.pop("headers", {})},
                                        **kw)
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("File storage is unavailable.", code="storage_unavailable") from exc

    def signed_upload_url(self, key: str) -> str:
        r = self._req("POST", f"/object/upload/sign/{self.bucket}/{key}")
        if r.status_code != 200:
            raise ServiceUnavailable("Could not prepare the upload.", code="storage_unavailable")
        return self._public + r.json()["url"]

    def info(self, key: str) -> ObjectInfo | None:
        r = self._req("GET", f"/object/info/{self.bucket}/{key}")
        if r.status_code in (400, 404):
            return None
        if r.status_code != 200:
            raise ServiceUnavailable("Could not check the upload.", code="storage_unavailable")
        body = r.json()
        return ObjectInfo(size=int(body.get("size") or 0), content_type=body.get("content_type"))

    def signed_download_urls(self, keys: list[str], ttl: int = DOWNLOAD_TTL_SECONDS) -> dict[str, str]:
        if not keys:
            return {}
        r = self._req("POST", f"/object/sign/{self.bucket}", json={"expiresIn": ttl, "paths": keys})
        if r.status_code != 200:
            raise ServiceUnavailable("Could not prepare file links.", code="storage_unavailable")
        out: dict[str, str] = {}
        for item in r.json():
            if item.get("signedURL") and not item.get("error"):
                out[item["path"]] = self._public + item["signedURL"]
        return out

    def download(self, key: str, max_bytes: int) -> bytes:
        with self._client.stream("GET", f"{self._base}/object/{self.bucket}/{key}", headers=self._headers) as r:
            if r.status_code != 200:
                raise FileNotFoundError(key)
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ValueError("object exceeds the allowed size")
            return bytes(buf)

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        r = self._req("POST", f"/object/{self.bucket}/{key}", content=data,
                      headers={"Content-Type": content_type, "x-upsert": "true", "Cache-Control": "private, max-age=0"})
        if r.status_code not in (200, 201):
            raise ServiceUnavailable("Could not store a derived file.", code="storage_unavailable")

    def remove(self, keys: list[str]) -> None:
        if keys:
            self._req("DELETE", f"/object/{self.bucket}", json={"prefixes": keys})


@lru_cache
def get_storage() -> StorageBackend:
    s = get_settings()
    if s.supabase_secret_key is None:
        raise ServiceUnavailable("File storage is not configured.", code="storage_not_configured")
    public = "" if s.storage_same_origin else (s.supabase_public_url or s.supabase_url)
    return SupabaseStorage(s.supabase_url, public, s.supabase_secret_key.get_secret_value(), s.storage_bucket)


def quarantine_key(org_id: object, media_id: object) -> str:
    return f"quarantine/{org_id}/{media_id}/original"


def derived_key(org_id: object, media_id: object, variant: str) -> str:
    return f"derived/{org_id}/{media_id}/{variant}"
