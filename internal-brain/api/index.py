"""Vercel entrypoint for the public, synthetic-data demo."""
import os

# Vercel Functions have a read-only deployment filesystem and ephemeral /tmp.
# Keep the hosted demo self-contained and avoid background worker threads.
os.environ.setdefault("IB_DATA_DIR", "/tmp/yieldgpt")
os.environ.setdefault("IB_DEMO_MODE", "1")
os.environ.setdefault("IB_ATLASSIAN_MODE", "fixture")
os.environ.setdefault("IB_LLM_PROVIDER", "stub")
os.environ.setdefault("IB_SERVERLESS", "1")

from app.server import app  # noqa: E402,F401
