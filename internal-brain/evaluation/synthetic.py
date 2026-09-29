"""Deterministic retrieval load fixture, not a simulation of native SaaS ACLs.

The full size resembles the brief's estate. Hierarchies and varied ACL hints are
metadata for index workload realism only; connector contract tests establish
native permission behavior separately.
"""
from __future__ import annotations

import random

NOW = 1_800_000_000.0
FULL_COUNTS = {"confluence": 12500, "jira": 3200, "slack": 2200, "gdrive": 1800}
SMALL_COUNTS = {"confluence": 520, "jira": 320, "slack": 440, "gdrive": 180}
PRINCIPALS = {"user:jdoe", "group:eng", "group:all-employees", "domain", "anyone"}
ACL_SETS = [
    {"group:eng"}, {"group:all-employees"}, {"group:payments"},
    {"group:security"}, {"user:dana"}, {"anyone"}, {"user:jdoe"},
]
PLATFORMS = set(FULL_COUNTS)
SERVICES = ("checkout", "identity", "billing", "ledger", "payouts", "catalogue", "search",
            "notifications", "analytics", "settlement", "disputes", "fraud")
TOPICS = ("database migration", "certificate renewal", "connection pooling", "traffic failover",
          "queue backpressure", "schema compatibility", "access reviews", "incident response",
          "deployment rollback", "retention policy", "monitoring alerts", "load testing")

# Hand-written needles evaluate meaningful queries amid overlapping generic prose.
TARGETS = [
    ("confluence", 10, "Bluefin audit replay runbook",
     "Bluefin recovers missing audit events by replaying the immutable event journal. Operators first compare "
     "the last acknowledged sequence with the journal checkpoint, then replay only the missing range. "
     "Replaying an acknowledged event is safe because the consumer deduplicates by event identifier.",
     "How does Bluefin recover missing audit events?"),
    ("confluence", 11, "Juniper database read replica procedure",
     "Juniper routes analytical reads to a dedicated replica. When replica lag exceeds twelve seconds, "
     "the application temporarily pauses analytical jobs while transactional reads stay on the primary. "
     "The owner must verify recovery before restarting the analytical queue.",
     "What should happen when Juniper replica lag exceeds twelve seconds?"),
    ("jira", 10, "Orion settlement duplicate transfer remediation",
     "The Orion settlement worker retried an acknowledged transfer after a timeout. The fix persists "
     "the idempotency key before submitting the transfer and checks the receipt before retrying. "
     "The issue remains In Progress until reconciliation finds no duplicate settlements.",
     "How is Orion preventing duplicate settlement transfers?"),
    ("jira", 11, "Cedar rollback blocked by schema compatibility",
     "Cedar cannot roll back the billing release until the compatibility migration restores the old "
     "invoice status column. The database team owns the prerequisite migration. Deployment approval "
     "depends on a successful read from both schema versions in the staging environment.",
     "Why is the Cedar billing rollback blocked?"),
    ("slack", 10, "Harbor failover exercise discussion",
     "maria: The Harbor failover exercise is scheduled for Thursday afternoon.\n"
     "elliot: We must freeze background reconciliation before moving traffic.\n"
     "maria: Agreed; keep the previous region available until ledger reconciliation completes.",
     "What did the Harbor failover discussion say to freeze before moving traffic?"),
    ("slack", 11, "Willow message retention thread",
     "anika: Willow messages expire after ninety days under the approved retention policy.\n"
     "ben: Exporting messages does not extend their permitted retention.\n"
     "anika: Correct. The downstream search index must remove expired messages and their cached excerpts.",
     "What should the downstream index do when Willow messages expire?"),
    ("gdrive", 10, "Kestrel payout launch checklist",
     "The Kestrel payout launch requires completion of the sandbox reconciliation and the callback "
     "signature verification exercise. The launch owner then records approval in the release checklist. "
     "Testing a successful payout alone is insufficient because failure callbacks must also be verified.",
     "Which checks are required for the Kestrel payout launch?"),
    ("gdrive", 11, "Maple support access review evidence",
     "The Maple support access review records all approved time-limited grants. Each row includes the "
     "requesting employee, approving manager, grant expiry, and system owner. Expired grants are removed "
     "during the daily review, and removal evidence is linked from the original request.",
     "What information is recorded in Maple support access reviews?"),
]


def native_id(platform: str, number: int) -> str:
    if platform == "confluence":
        return f"CONF-{100000 + number}"
    if platform == "jira":
        return f"PRJ{number % 32:02}-{100000 + number}"
    if platform == "slack":
        return f"channel-{number % 220:03}/{100000 + number}"
    return f"DRV-{100000 + number}"


def make_corpus(size: str = "full", seed: int = 20260928):
    """Yield (SourceDoc, ACL-hint) tuples using a local seeded PRNG."""
    from app.sources.base import SourceDoc

    rng = random.Random(seed)
    counts = FULL_COUNTS if size == "full" else SMALL_COUNTS
    target_map = {(p, i): (title, text) for p, i, title, text, _ in TARGETS}
    for platform, count in counts.items():
        for number in range(count):
            service = SERVICES[number % len(SERVICES)]
            topic = TOPICS[(number // len(SERVICES)) % len(TOPICS)]
            nid = native_id(platform, number)
            title = f"{service.title()} {topic}: review {number // 144 + 1}"
            sentences = [
                f"The {service} team reviews {topic} before every scheduled release.",
                f"This record tracks the operational checklist for work item {nid} and assigns an accountable service owner.",
                "Before changing production, the operator confirms the current deployment version and checks the staging results.",
                "The team records observed latency, error rates, and any dependency failures in the incident timeline.",
                "Rollback requires a compatible database schema and an available previous release artifact.",
                "The reviewer compares the evidence with the acceptance criteria, records outstanding actions, and schedules the next review.",
                "A successful deployment is followed by a monitoring period so delayed reconciliation failures are investigated.",
                "Support staff receive the approved customer explanation after engineering verifies the timeline.",
            ]
            rng.shuffle(sentences)
            text = " ".join(sentences[:rng.randint(4, 8)])
            acl = set(ACL_SETS[(number + len(platform)) % len(ACL_SETS)])
            if (platform, number) in target_map:
                title, text = target_map[platform, number]
                acl = {"group:eng"}
            if platform == "confluence":
                container, tenant = f"space-{number % 52:02}", "companya.atlassian.net"
                parent = native_id(platform, number - 52) if number >= 52 else ""
            elif platform == "jira":
                container, tenant, parent = f"PRJ{number % 32:02}", "companya.atlassian.net", ""
            elif platform == "slack":
                channel = number % 220
                container, tenant, parent = f"channel-{channel:03}", f"workspace-{channel % 3}", nid
                text = f"owner-{number % 20}: {text}\nreviewer-{number % 17}: The action is tracked in the release review."
            else:
                folder = number % 150
                container = f"drive-{folder % 10}/team-{folder % 30}/folder-{folder:03}"
                tenant, parent = "companya.example", f"drive-{folder % 10}/team-{folder % 30}"
            yield SourceDoc(uid=f"{platform}:{nid}", platform=platform, tenant=tenant,
                            native_id=nid, container=container, title=title, text=text,
                            url=f"https://synthetic.companya.example/{platform}/{nid}", version="synthetic-v1",
                            updated_at=NOW - rng.randint(0, 365) * 86400, parent=parent,
                            author=f"employee-{number % 97}"), acl


def queries() -> list[dict]:
    return [{"id": f"{p}-{i}", "question": q, "expected_uid": f"{p}:{native_id(p, i)}"}
            for p, i, _, _, q in TARGETS]
