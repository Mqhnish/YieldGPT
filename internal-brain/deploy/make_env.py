#!/usr/bin/env python3
"""Write deploy/.env with fresh random secrets. Never overwrites a value: on an existing file it
only appends keys that are missing (e.g. the second checkpoint anchor added later)."""
import base64
import secrets
from pathlib import Path

target = Path(__file__).with_name(".env")
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
    "MINIO_B_ROOT_USER": "anchor-b-admin", "MINIO_B_ROOT_PASSWORD": token(),
    "CHECKPOINT_B_WRITER_KEY": "brain-checkpoint-writer", "CHECKPOINT_B_WRITER_SECRET": token(),
    "CHECKPOINT_B_READER_KEY": "audit-verifier", "CHECKPOINT_B_READER_SECRET": token(),
}
existing = {line.split("=", 1)[0] for line in target.read_text().splitlines()} if target.exists() else set()
missing = {k: v for k, v in values.items() if k not in existing}
with open(target, "a") as f:
    f.write("".join(f"{k}={v}\n" for k, v in missing.items()))
target.chmod(0o600)
print(f"{target}: added {len(missing)} keys, kept {len(existing)} existing")
