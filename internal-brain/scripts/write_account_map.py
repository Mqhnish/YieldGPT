"""Write accounts.json (persona -> Atlassian accountId) from the personas' emails.

  python scripts/write_account_map.py jdoe=a@x.com ravi=b@x.com asha=c@x.com priya=d@x.com

Uses GET /rest/api/3/user/search?query=<email> with the IB_ATLASSIAN_* settings. Personas not
given (kim) get {} = no Atlassian account. Prints only found / not found, never ids or emails.
One Atlassian account covers Confluence and Jira on the same site. accounts.json is gitignored.
"""
import json
import pathlib
import sys

sys.path.insert(0, ".")
from app import config  # noqa: E402
from app.sources.atlassian_client import AtlassianClient  # noqa: E402

PERSONAS = ("jdoe", "ravi", "asha", "priya", "kim")


def main(args, out="accounts.json"):
    pairs = dict(a.split("=", 1) for a in args)
    bad = set(pairs) - set(PERSONAS)
    if bad or not pairs:
        sys.exit(f"usage: persona=email ... (personas: {', '.join(PERSONAS)})")
    if not (config.ATLASSIAN_SITE and config.ATLASSIAN_EMAIL and config.ATLASSIAN_API_TOKEN):
        sys.exit("set IB_ATLASSIAN_SITE, IB_ATLASSIAN_EMAIL and IB_ATLASSIAN_API_TOKEN in .env first")
    api = AtlassianClient(config.ATLASSIAN_SITE, config.ATLASSIAN_EMAIL, config.ATLASSIAN_API_TOKEN)
    mapping, ok = {}, True
    for persona in PERSONAS:
        email = pairs.get(persona)
        if not email:
            mapping[persona] = {}
            print(f"{persona:6} no Atlassian account (by design)" if persona == "kim" else f"{persona:6} not given")
            continue
        hits = [u for u in api.get("/rest/api/3/user/search", query=email) or []
                if u.get("accountType") == "atlassian" and (u.get("emailAddress") in (None, "", email))]
        if len(hits) != 1:
            ok = False
            mapping[persona] = {}
            print(f"{persona:6} NOT FOUND ({len(hits)} matches): has the invite been accepted?")
            continue
        acct = hits[0]["accountId"]
        mapping[persona] = {"confluence": acct, "jira": acct}
        print(f"{persona:6} found")
    pathlib.Path(out).write_text(json.dumps(mapping, indent=1) + "\n")
    print(f"\nwrote {out}" + ("" if ok else " (with gaps: fix and re-run)"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
