#!/usr/bin/env python3
"""Member 3 scripted demonstration (backup for the live demo) on isolated data.

    python scripts/demo_member3.py --markdown docs/demo-transcript-member3.md

It uses a temporary data directory, so it never touches the running demo. If
IB_CHECKPOINT_S3_* is configured (for example against deploy/docker-compose.yml with
the reader/writer credentials from deploy/.env), checkpoints go to the WORM bucket under
a unique prefix. Otherwise the local, non-independent store is used and the transcript
says so. Exit status is non-zero if any scene does not behave as expected.
"""
import argparse
import os
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QUESTION = "What's the status of the database migration project and were there any blockers raised in Slack last week?"


class _Down:
    kind = "s3_object_lock"

    def _fail(self, *a):
        from app.checkpoints import CheckpointError
        raise CheckpointError("checkpoint store unreachable (demo outage)")
    append = checkpoints = assurance = _fail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markdown", help="write the transcript here")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="member3-demo-"))
    os.environ.update(IB_DATA_DIR=str(scratch), IB_AUDIT_DB=str(scratch / "audit.db"),
                      IB_ANCHOR_PATH=str(scratch / "anchors.jsonl"), IB_LLM_PROVIDER="stub")
    if os.getenv("IB_CHECKPOINT_S3_ENDPOINT"):
        os.environ["IB_CHECKPOINT_S3_PREFIX"] = f"demo-{int(time.time())}/"
    from fastapi.testclient import TestClient

    from app import audit, server

    out, failures = [], []

    def scene(title, lines, ok=True):
        out.append(f"## {title}\n\n" + "\n".join(lines) + "\n")
        if not ok:
            failures.append(title)

    def verify_copy(tamper):
        """Tamper with a COPY of the audit DB and verify it against the same checkpoints."""
        copy = scratch / f"tampered-{len(out)}.db"
        with sqlite3.connect(audit.AUDIT_DB) as src, sqlite3.connect(copy) as dst:
            src.backup(dst)
        with sqlite3.connect(copy) as c:
            tamper(c)
        live, audit.AUDIT_DB = audit.AUDIT_DB, copy
        try:
            return audit.verify_report()
        finally:
            audit.AUDIT_DB = live

    def rewrite(c):
        c.execute("UPDATE audit_log SET actor='someone-else' WHERE event='query_received'")
        prev = audit.GENESIS
        for r in c.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
            h = audit._hash(list(r[1:1 + len(audit.COLS)]), prev)
            c.execute("UPDATE audit_log SET prev_hash=?, hash=? WHERE id=?", (prev, h, r[0]))
            prev = h

    with TestClient(server.app) as c:
        def login(user):
            token = c.post("/api/login", json={"username": user, "password": "demo"}).json()["token"]
            return {"Authorization": "Bearer " + token}
        jdoe, kim, priya, dana = (login(u) for u in ("jdoe", "kim", "priya", "dana"))

        r = c.post("/api/ask", json={"question": QUESTION}, headers=jdoe)
        answer, qid = r.json(), r.json()["query_id"]
        scene("1. An employee asks a cross-platform question", [
            f"- `jdoe` asks: “{QUESTION}”",
            f"- HTTP {r.status_code}, request `{r.headers['x-request-id']}`, query `{qid}`",
            f"- Cited: {', '.join('`' + x['uid'] + '`' for x in answer['citations'])}",
            "- The response left the server only after this request's audit rows were covered by a committed checkpoint."],
            r.status_code == 200 and answer["citations"])

        r = c.post("/api/ask", json={"question": "Show me the security incident report from the Q3 breach"}, headers=kim)
        scene("2. A contractor asks for restricted material", [
            f"- `kim` receives: “{r.json()['answer']}” with {len(r.json()['citations'])} citations and no hidden titles."],
            not r.json()["citations"])

        story = c.post("/api/compliance/requests", json={"query_id": qid}, headers=priya).json()["results"][0]
        tally = Counter(f"{d['stage']}:{d['decision']}" for d in story["decisions"])
        scene("3. Compliance reconstructs the request (priya, full audit scope)", [
            f"- Question: “{story['question']}”",
            f"- Release `{story['release']}`, terminal `{story['terminal']}`, delivery `{story['delivery']}`, "
            f"generation `{(story['generation'] or {}).get('mode')}`",
            "- Versions actually sent to the model: " + ", ".join(
                f"`{d['uid']}@{d['version']}`" for a in story["context_sent"] for d in a["docs"]),
            "- Permitted but not sent: " + (", ".join(f"`{u}`" for u in story["permitted_not_sent"]) or "none"),
            "- Decisions: " + ", ".join(f"{k} ×{v}" for k, v in sorted(tally.items()))],
            story["question"] == QUESTION and story["delivery"] == "delivered")

        denied = c.post("/api/compliance/requests", json={"query_id": qid}, headers=dana)
        events = c.get("/api/audit/events?limit=200", headers=dana).json()["events"]
        sample = next(e for e in events if e["event"] == "query_received")
        scene("4. The platform admin cannot read what was asked (dana, metadata scope)", [
            f"- Request reconstruction: HTTP {denied.status_code}",
            f"- Metadata view of the same request: `{sample}`",
            f"- Question text visible anywhere in the admin view: {QUESTION in str(events)}"],
            denied.status_code == 403 and QUESTION not in str(events))

        report = c.get("/api/audit/verify", headers=priya).json()
        scene("5. The verifier checks the chain against the protected checkpoints", [
            f"- Status **{report['status']}**, {report['rows']} rows, verified through row {report['verified_through']}, "
            f"{report['uncheckpointed_rows']} uncheckpointed",
            f"- Checkpoint store `{report['checkpoint_store']}`, assurance `{report['assurance']}`",
            f"- Sealed text: {report['content']}"], report["status"] == "verified")

        rewritten = verify_copy(rewrite)
        truncated = verify_copy(lambda db: db.execute(
            "DELETE FROM audit_log WHERE id > ?", (report["verified_through"] - 3,)))
        scene("6. Tampering is detected (on copies of the audit database)", [
            f"- Edit a row and recompute every hash: **{rewritten['status']}**: {rewritten['problem']} at row {rewritten['at_id']}",
            f"- Delete the checkpointed tail: **{truncated['status']}**: {truncated['problem']} at row {truncated['at_id']}"],
            rewritten["status"] == truncated["status"] == "failed")

        real_store, audit._store = audit._store, lambda: _Down()
        try:
            withheld = c.post("/api/ask", json={"question": QUESTION}, headers=jdoe)
            unverifiable = audit.verify_report()
        finally:
            audit._store = real_store
        scene("7. The checkpoint store is unreachable", [
            f"- A new answer is withheld: HTTP {withheld.status_code} “{withheld.json()['detail']}”",
            f"- Verifier: **{unverifiable['status']}**: {unverifiable['problem']}"],
            withheld.status_code == 503 and unverifiable["status"] == "unverifiable")

        audit.log("jdoe", "request_received", request_id="demo-crash")
        audit.log("jdoe", "query_received", query_id="demo-crash-q", request_id="demo-crash", question="interrupted")
        closed = audit.recover_interrupted()
        crashed = audit.reconstruct(query_id="demo-crash-q")[0]
        scene("8. Restart recovery", [
            f"- {closed} interrupted request(s) given an explicit terminal record: "
            f"terminal `{crashed['terminal']}`, delivery `{crashed['delivery']}`, request `{crashed['request_id']}`"],
            crashed["terminal"] == "request_abandoned")

    header = ["# Member 3 demonstration transcript", "",
              f"Generated {time.strftime('%Y-%m-%d %H:%M:%S %Z')} by `scripts/demo_member3.py` on isolated data. "
              f"Checkpoint store: `{report['checkpoint_store']}` (assurance `{report['assurance']}`).",
              "", "Result: " + ("all scenes behaved as expected." if not failures else f"FAILED: {failures}"), ""]
    text = "\n".join(header) + "\n" + "\n".join(out)
    print(text)
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
