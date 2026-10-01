#!/usr/bin/env python3
"""Write deploy/.env with fresh random secrets. Refuses to overwrite an existing file."""
import base64
import secrets
from pathlib import Path

target = Path(__file__).with_name(".env")
if target.exists():
    raise SystemExit(f"{target} already exists; delete it first to rotate every secret")
token = lambda: secrets.token_urlsafe(24)  # noqa: E731
values = {
    "IB_DEMO_MODE": "1",
    "IB_SECRET_KEY": token(), "IB_WEBHOOK_SECRET": token(),
    "IB_WEBHOOK_SECRET_CONFLUENCE": token(), "IB_WEBHOOK_SECRET_JIRA": token(), "IB_WEBHOOK_SECRET_GDRIVE": token(),
    "IB_AUDIT_PSEUDONYM_KEY": token(),
    "IB_AUDIT_CONTENT_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    "MINIO_ROOT_USER": "storage-admin", "MINIO_ROOT_PASSWORD": token(),
    "CHECKPOINT_BUCKET": "audit-checkpoints", "CHECKPOINT_RETENTION_DAYS": "30",
    "CHECKPOINT_WRITER_KEY": "brain-checkpoint-writer", "CHECKPOINT_WRITER_SECRET": token(),
    "CHECKPOINT_READER_KEY": "audit-verifier", "CHECKPOINT_READER_SECRET": token(),
}
target.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
target.chmod(0o600)
print(f"wrote {target}")
