"""Scale mode: a reproducible, brief-sized Company A for benchmarks.

The brief's footprint: 50+ Confluence spaces with 12,000+ pages, 30+ Jira projects,
200+ Slack channels across multiple workspaces, shared + personal Drive. Ticket,
message and file counts aren't given, so they're our declared choices (see DEFAULTS).

Same seed -> same estate, byte for byte, so results are comparable between runs.
Text is assembled from varied vocabulary per team (not one sentence repeated), and
permissions vary on purpose: open spaces, team spaces, restricted subtrees, single-user
pages, issue security levels, private channels, external shares, personal files.

The original hand-written demo company is kept inside, so the scenario questions still
work at scale and the needles are hidden in a large haystack.
"""
from __future__ import annotations

import random
import time

from ..identity import USERS
from ..sources.world import DAY, World

DEFAULTS = dict(spaces=52, pages=12_500, projects=32, issues=6_400, workspaces=3, channels=220,
                threads=8_800, folders=120, files=3_000)

TEAMS = ["payments", "eng", "security", "it", "compliance", "billing", "growth", "data", "mobile", "infra",
         "risk", "treasury", "cards", "lending", "fraud", "support"]
GROUPS = ["eng", "payments", "security", "it", "compliance"]          # groups the personas actually have
NOUNS = ["ledger", "reconciliation job", "card authorisation", "FX quote service", "KYC pipeline", "webhook relay",
         "settlement batch", "rate limiter", "feature flag", "audit export", "invoice parser", "fraud model",
         "payout scheduler", "token vault", "statement generator", "onboarding flow", "dispute queue",
         "cache cluster", "message broker", "schema migration", "API gateway", "mobile release", "SSO integration"]
VERBS = ["times out under load", "drops events after a deploy", "double counts refunds", "needs a backfill",
         "is missing alerting", "was rolled back", "exceeded its error budget", "has stale config",
         "blocks the quarterly close", "needs an owner", "fails on month-end volume", "leaks memory slowly"]
ACTIONS = ["Add a dashboard for", "Write a runbook for", "Load test", "Deprecate", "Migrate", "Document",
           "Add retries to", "Shard", "Add tracing to", "Review access to", "Rotate credentials for"]
STATUSES = ["To Do", "In Progress", "Blocked", "In Review", "Done"]


def _sentence(r: random.Random, team: str) -> str:
    n, v = r.choice(NOUNS), r.choice(VERBS)
    return r.choice([
        f"The {team} {n} {v}.",
        f"{r.choice(ACTIONS)} the {n} owned by {team}.",
        f"Since sprint {r.randint(1, 60)}, the {n} {v}; tracked by the {team} team.",
        f"Decision: the {team} team will {r.choice(ACTIONS).lower()} the {n} before Q{r.randint(1, 4)}.",
        f"Incident note: {n} {v} at {r.randint(0, 23):02d}:{r.randint(0, 59):02d} SGT, {r.randint(1, 90)} min impact.",
    ])


def _text(r: random.Random, team: str, lo=2, hi=7) -> str:
    return "\n".join(_sentence(r, team) for _ in range(r.randint(lo, hi)))


def generate(seed: int = 7, **sizes) -> World:
    cfg = {**DEFAULTS, **sizes}
    r = random.Random(seed)
    now = time.time()
    w = World(now)            # starts with the hand-written demo company inside
    personas = sorted(USERS)
    employees = [u for u in personas if USERS[u].kind == "employee"]

    # ---------------- Confluence: spaces with mixed visibility, page trees, restrictions
    space_keys = []
    for i in range(cfg["spaces"]):
        team = TEAMS[i % len(TEAMS)]
        key = f"{team}-{i:02d}"
        roll = r.random()
        view = ({"group:all-employees"} if roll < 0.45 else
                {f"group:{r.choice(GROUPS)}"} if roll < 0.9 else
                {f"group:{a}" for a in r.sample(GROUPS, 2)})
        w.spaces[key] = {"name": f"{team.title()} {i:02d}", "view": view}
        space_keys.append((key, team))
    by_space: dict[str, list[str]] = {}
    for n in range(cfg["pages"]):
        key, team = r.choice(space_keys)
        pid = f"P-{n:05d}"
        siblings = by_space.setdefault(key, [])[-20:]
        parent = r.choice(siblings) if siblings and r.random() < 0.4 else None
        roll = r.random()
        restrict = ({f"user:{r.choice(personas)}"} if roll < 0.03 else
                    {f"group:{r.choice(GROUPS)}"} if roll < 0.10 else None)
        w.pages[pid] = dict(space=key, parent=parent, restrict=restrict, updated=now - r.uniform(0, 400) * DAY,
                            title=f"{team.title()}: {r.choice(NOUNS)} notes {n}", body=_text(r, team), links=[])
        by_space[key].append(pid)

    # ---------------- Jira: projects with different browse groups, security levels on some issues
    proj_keys = []
    for i in range(cfg["projects"]):
        team = TEAMS[i % len(TEAMS)]
        key = f"{team[:3].upper()}{i:02d}"
        browse = {"group:all-employees"} if r.random() < 0.3 else {f"group:{a}" for a in r.sample(GROUPS, r.randint(1, 2))}
        w.projects[key] = {"name": f"{team.title()} {i:02d}", "roles": {"members": browse}, "browse": {"members"}}
        proj_keys.append((key, team))
    counts: dict[str, int] = {}
    for n in range(cfg["issues"]):
        key, team = r.choice(proj_keys)
        counts[key] = num = counts.get(key, 0) + 1
        ik = f"{key}-{num}"
        w.issues[ik] = dict(project=key, level="security-only" if r.random() < 0.05 else None,
                            status=r.choice(STATUSES), updated=now - r.uniform(0, 300) * DAY,
                            summary=f"{r.choice(ACTIONS)} the {team} {r.choice(NOUNS)}", desc=_text(r, team, 1, 4),
                            links=[f"confluence:P-{r.randrange(cfg['pages']):05d}"] if r.random() < 0.2 else [])

    # ---------------- Slack: several workspaces, public + private channels, threads
    chans = []
    for i in range(cfg["channels"]):
        team = TEAMS[i % len(TEAMS)]
        name = f"{team}-{i:03d}"
        private = r.random() < 0.35
        members = set(r.sample(employees, r.randint(1, len(employees)))) if private else set(employees)
        if r.random() < 0.05:
            members.add("kim")   # a few shared vendor channels
        w.channels[name] = {"workspace": f"ws{i % cfg['workspaces']}", "private": private, "members": members,
                            "retention_days": r.choice([90, 365, 730])}
        chans.append((name, team))
    for n in range(cfg["threads"]):
        name, team = r.choice(chans)
        ts = now - r.uniform(0, 80) * DAY
        tid = f"{name}/{int(ts * 1000) + n}"
        msgs = [(r.choice(sorted(w.channels[name]["members"])), ts + k * 300, _sentence(r, team))
                for k in range(r.randint(1, 5))]
        w.threads[tid] = dict(ts=ts, msgs=msgs)

    # ---------------- Drive: shared folders, personal files, external shares
    folders = []
    for i in range(cfg["folders"]):
        team = TEAMS[i % len(TEAMS)]
        fid = f"fld-{team}-{i:03d}"
        parent = r.choice(folders)[0] if folders and r.random() < 0.3 else None
        shares = {f"group:{r.choice(GROUPS)}": "view"} if r.random() < 0.8 else {"domain": "view"}
        w.folders[fid] = {"name": f"{team.title()} files {i}", "parent": parent, "shares": shares}
        folders.append((fid, team))
    for n in range(cfg["files"]):
        roll = r.random()
        if roll < 0.75:
            folder, team = r.choice(folders)
            shares = {}
        else:
            folder, team = None, r.choice(TEAMS)
            shares = {f"user:{r.choice(personas)}": "edit"}
        if r.random() < 0.02:
            shares["anyone"] = "view"
        w.files[f"F-{n:05d}"] = dict(folder=folder, shares=shares, updated=now - r.uniform(0, 500) * DAY,
                                     name=f"{team.title()} {r.choice(NOUNS)} sheet {n}", text=_text(r, team, 1, 4),
                                     links=[])
    return w


def summary(w: World) -> dict:
    return {"confluence_spaces": len(w.spaces), "confluence_pages": len(w.pages), "jira_projects": len(w.projects),
            "jira_issues": len(w.issues), "slack_workspaces": len({c["workspace"] for c in w.channels.values()}),
            "slack_channels": len(w.channels), "slack_threads": len(w.threads),
            "drive_folders": len(w.folders), "drive_files": len(w.files)}
