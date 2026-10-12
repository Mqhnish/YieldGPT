"""Audit checkpoint storage: the trust boundary for the hash chain. Owner: Member 3.

A checkpoint is (row_id, head_hash) of the audit chain. The verifier trusts the
checkpoint store, not the audit database, so the store must sit outside the
application's write authority:

  S3ObjectLockStore   Production. An S3-compatible bucket with Object Lock in
                      COMPLIANCE mode (MinIO locally, Tencent COS / AWS S3 in cloud).
                      The app's credential may only PutObject; it cannot delete,
                      shorten retention or change the lock configuration, and every
                      committed object version is retained. The verifier uses a
                      separate read-only credential. Keys are content-addressed
                      ("<prefix><row_id:012d>-<hash>") so listing alone yields every
                      checkpoint, including versions hidden behind delete markers.
  LocalCheckpointStore Tests/dev only: a JSONL file the app itself can rewrite. The
                      verifier always labels it assurance="local_only".

Selected by IB_CHECKPOINT_S3_ENDPOINT. SigV4 is implemented here with the stdlib
over the existing httpx dependency (path-style URLs).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

import httpx

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
# One pooled, thread-safe client: a new TCP connection per checkpoint exhausts ports under load.
_HTTP = httpx.Client(limits=httpx.Limits(max_connections=64, max_keepalive_connections=32))


def _xml(content: bytes) -> ET.Element:
    """Parse S3 XML ignoring namespaces (AWS/COS send one, MinIO omits it on some calls)."""
    root = ET.fromstring(content)
    for el in root.iter():
        el.tag = el.tag.rpartition("}")[2]
    return root


class CheckpointError(Exception):
    """The checkpoint store refused or could not be reached. Never contains credentials."""


# ---------------------------------------------------------------- local (tests/dev only)
class LocalCheckpointStore:
    kind = "local_file"

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, row_id: int, head_hash: str) -> None:
        with open(self.path, "a") as f:  # ponytail: O_APPEND line writes; fine for one host
            f.write(json.dumps({"row_id": row_id, "hash": head_hash, "committed_at": time.time()}) + "\n")

    def checkpoints(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def assurance(self) -> str:
        return "local_only"


# ---------------------------------------------------------------- S3 Object Lock
def sigv4_headers(method: str, url: str, headers: dict, payload_sha256: str, access_key: str,
                  secret_key: str, region: str, now: datetime | None = None) -> dict:
    """AWS Signature V4 for S3. Returns headers including Authorization."""
    now = now or datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    parts = urlsplit(url)
    out = {**headers, "host": parts.netloc, "x-amz-date": amz_date, "x-amz-content-sha256": payload_sha256}
    canon = sorted((k.lower(), " ".join(str(v).split())) for k, v in out.items())
    signed = ";".join(k for k, _ in canon)
    query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
                     for k, v in sorted(parse_qsl(parts.query, keep_blank_values=True)))
    request = "\n".join([method, quote(parts.path or "/", safe="/-_.~"), query,
                         "".join(f"{k}:{v}\n" for k, v in canon), signed, payload_sha256])
    scope = f"{amz_date[:8]}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(request.encode()).hexdigest()])
    key = ("AWS4" + secret_key).encode()
    for part in (amz_date[:8], region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"
    return out


class S3ObjectLockStore:
    kind = "s3_object_lock"

    def __init__(self, endpoint: str, bucket: str, prefix: str, region: str,
                 writer: tuple[str, str], reader: tuple[str, str], timeout: float = 5.0):
        self.endpoint, self.bucket, self.prefix, self.region = endpoint.rstrip("/"), bucket, prefix, region
        self.writer, self.reader, self.timeout = writer, reader, timeout

    def _request(self, method: str, path_query: str, creds: tuple[str, str], body: bytes = b"",
                 headers: dict | None = None) -> httpx.Response:
        url = f"{self.endpoint}/{self.bucket}{path_query}"
        signed = sigv4_headers(method, url, headers or {}, hashlib.sha256(body).hexdigest(), *creds, self.region)
        try:
            return _HTTP.request(method, url, content=body, headers=signed, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise CheckpointError(f"checkpoint store unreachable ({type(e).__name__})") from None

    def append(self, row_id: int, head_hash: str) -> None:
        body = json.dumps({"row_id": row_id, "hash": head_hash, "committed_at": time.time()}).encode()
        md5 = base64.b64encode(hashlib.md5(body).digest()).decode()  # required with Object Lock
        r = self._request("PUT", f"/{self.prefix}{row_id:012d}-{head_hash}", self.writer, body,
                          {"content-md5": md5, "content-type": "application/json"})
        if r.status_code != 200:
            raise CheckpointError(f"checkpoint store refused write (HTTP {r.status_code})")

    def checkpoints(self) -> list[dict]:
        out, marker = [], ""
        while True:
            r = self._request("GET", f"?versions&prefix={quote(self.prefix, safe='')}{marker}", self.reader)
            if r.status_code != 200:
                raise CheckpointError(f"checkpoint listing failed (HTTP {r.status_code})")
            root = _xml(r.content)
            for v in root.findall("Version"):  # delete markers hide nothing: versions are listed
                name = v.findtext("Key", "")[len(self.prefix):]
                row, _, digest = name.partition("-")
                if row.isdigit() and len(digest) == 64:
                    out.append({"row_id": int(row), "hash": digest,
                                "committed_at": v.findtext("LastModified", "")})
            if root.findtext("IsTruncated", "false") != "true":
                return out
            marker = (f"&key-marker={quote(root.findtext('NextKeyMarker', ''), safe='')}"
                      f"&version-id-marker={quote(root.findtext('NextVersionIdMarker', ''), safe='')}")

    def assurance(self) -> str:
        """independent_worm only if the bucket enforces COMPLIANCE-mode Object Lock."""
        r = self._request("GET", "?object-lock", self.reader)
        if r.status_code == 404:
            return "unprotected_bucket"
        if r.status_code != 200:
            raise CheckpointError(f"object lock configuration unreadable (HTTP {r.status_code})")
        root = _xml(r.content)
        enabled = root.findtext("ObjectLockEnabled", "") == "Enabled"
        mode = root.findtext("Rule/DefaultRetention/Mode", "")
        return "independent_worm" if enabled and mode == "COMPLIANCE" else "unprotected_bucket"


def s3_configured() -> bool:
    return bool(os.getenv("IB_CHECKPOINT_S3_ENDPOINT"))


def from_env(local_path: Path):
    if not s3_configured():
        return LocalCheckpointStore(local_path)
    env = os.getenv
    return S3ObjectLockStore(env("IB_CHECKPOINT_S3_ENDPOINT"), env("IB_CHECKPOINT_S3_BUCKET", "audit-checkpoints"),
                             env("IB_CHECKPOINT_S3_PREFIX", "checkpoints/"), env("IB_CHECKPOINT_S3_REGION", "us-east-1"),
                             (env("IB_CHECKPOINT_WRITER_KEY", ""), env("IB_CHECKPOINT_WRITER_SECRET", "")),
                             (env("IB_CHECKPOINT_READER_KEY", ""), env("IB_CHECKPOINT_READER_SECRET", "")))
