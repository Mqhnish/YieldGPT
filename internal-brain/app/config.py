"""Central config. Everything comes from env vars so nothing secret lives in the repo."""
import os
from pathlib import Path
from .env import load_env

load_env()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('IB_DATA_DIR', ROOT / 'data')).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)

AUDIT_DB = Path(os.getenv("IB_AUDIT_DB", DATA_DIR / "audit.db"))
# External anchor file for the audit hash chain. In production this goes to
# write-once storage (e.g. object storage with retention lock) the app can't rewrite.
ANCHOR_PATH = Path(os.getenv("IB_ANCHOR_PATH", DATA_DIR / "audit_anchors.jsonl"))
ANCHOR_EVERY = int(os.getenv("IB_ANCHOR_EVERY", "20"))

SECRET_KEY = os.getenv("IB_SECRET_KEY", "dev-only-change-me")
WEBHOOK_SECRET = os.getenv("IB_WEBHOOK_SECRET", "dev-webhook-secret")
# One secret per platform so a leaked Jira secret can't forge Drive changes. Falls back to the
# shared secret for the demo; reliability.config_problems warns when that happens.
WEBHOOK_SECRETS = {p: os.getenv(f"IB_WEBHOOK_SECRET_{p.upper()}") or WEBHOOK_SECRET
                   for p in ("confluence", "jira", "gdrive")}
# Separate key for audit pseudonyms. Never reuse the token-signing key for another purpose.
AUDIT_PSEUDONYM_KEY = os.getenv("IB_AUDIT_PSEUDONYM_KEY", "dev-pseudonym-key-change-me")

# Connector safety limits
CHECK_TIMEOUT_S = float(os.getenv("IB_CHECK_TIMEOUT_S", "3"))     # slow permission check = UNAVAILABLE
MAX_PAGES_PER_POLL = int(os.getenv("IB_MAX_PAGES_PER_POLL", "50"))  # bound one poll's work
MAX_BACKOFF_S = 900  # never back off longer than 15 min, so the 1 h freshness bound still holds

# Freshness: webhooks push changes instantly, polling is the backstop.
POLL_INTERVAL_S = int(os.getenv("IB_POLL_INTERVAL_S", "300"))  # 5 min, well inside the ~1h SLA
FRESHNESS_SLA_S = 3600

# LLM. Tencent Hunyuan exposes an OpenAI-compatible chat endpoint.
LLM_PROVIDER = os.getenv("IB_LLM_PROVIDER", "stub")  # "stub" | "openai_compatible"
LLM_BASE_URL = os.getenv("IB_LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("IB_LLM_API_KEY", "")
LLM_MODEL = os.getenv("IB_LLM_MODEL", "")

PER_PLATFORM_K = int(os.getenv("IB_PER_PLATFORM_K", "4"))
CONTEXT_BUDGET_CHARS = int(os.getenv("IB_CONTEXT_BUDGET", "7000"))
PROBE_ALERT_THRESHOLD = 5  # denials within 10 min that trigger a probing alert

# Demo controls (/api/sim) mutate the simulated platforms, including permissions.
# Must be OFF in any deployment connected to real sources.
DEMO_MODE = os.getenv("IB_DEMO_MODE", "1") == "1"

# ---- Atlassian (Confluence + Jira) --------------------------------------------------
#   sim      in-process simulator, no HTTP (fastest, used by older tests)
#   fixture  REAL HTTP connectors talking to a fake Atlassian site (default: offline demo)
#   live     REAL HTTP connectors talking to a real Atlassian Cloud site
ATLASSIAN_MODE = os.getenv("IB_ATLASSIAN_MODE", "fixture")
ATLASSIAN_SITE = os.getenv("IB_ATLASSIAN_SITE", "")          # e.g. https://yourteam.atlassian.net
ATLASSIAN_EMAIL = os.getenv("IB_ATLASSIAN_EMAIL", "")        # integration account email
ATLASSIAN_API_TOKEN = os.getenv("IB_ATLASSIAN_API_TOKEN", "")  # id.atlassian.com API token, never commit
# How often polling does a full id listing to detect deletions (0 = every poll).
RECONCILE_EVERY_S = int(os.getenv("IB_RECONCILE_EVERY_S", "600"))
# Reconciliation refuses to delete >20% of an estate in one go unless this is set (see cloud_polling.py).
ALLOW_MASS_DELETE = os.getenv("IB_ALLOW_MASS_DELETE", "0") == "1"
