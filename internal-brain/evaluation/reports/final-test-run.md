# Final test run (clean checkout)

- Date: 14 Oct 2026
- Commit tested: `4df3b51` (integration of main a7b77b5 with PRs #8 to #14)
- Machine: Apple Silicon macOS, Python 3.13.15
- Method: `git worktree add` of that commit, new venv, `pip install -r requirements-lock.txt`, no `.env`
- CI: `.github/workflows/tests.yml` runs the same two commands on every PR and push to main

| Command (from `internal-brain/`) | Result |
|---|---|
| `python -m pytest -q` | **439 passed, 5 skipped** |
| `IB_ATLASSIAN_MODE=sim python -m pytest -q` | **427 passed, 17 skipped** |

Every skip is expected; none hides a failure:

| Skipped tests | Why | Where they were run |
|---|---|---|
| 4 in `test_member3_s3.py`, 1 in `test_member3_anchors.py` | Need live S3 Object Lock endpoints (`IB_TEST_S3_ENDPOINT`, `_2`) | Passed live on 12 Oct 2026 against two local MinIO instances, 18/18: `member3-worm-checkpoints.txt` |
| 10 in `test_lifecycle_probe.py`, 1 each in `test_atlassian_http.py`, `test_atlassian_review.py` (sim mode only) | They drive the HTTP Atlassian connectors, which only exist in fixture mode | Pass in the fixture-mode run above |
