# YieldGPT demo video script (target 7:00, limit 5 to 8 min)

Three voices: **M** = Mohnish, **I** = Imaad, **P** = Punya. Slides come from `docs/deck/index.html`
(press F for fullscreen). The app runs locally with **Confluence and Jira live** on our Atlassian site;
Slack and Drive are simulated, and the answer writer is the extractive mode (no live model yet).
Say so on screen; never imply more. Every number below is from a dated report in `evaluation/reports/`.

This replaces the earlier outline in `DEMO_MEDIA.md` for the recording itself (that file keeps the
listing copy and capture checklist). It drops what we can't show honestly: there is no "repository file"
source, no Hunyuan generation, and no token cost yet.

---

## Before you hit record (10 minutes)

1. Cloudflare WARP **disconnected** (it broke lookups of our Atlassian site on 14 Oct).
2. `cd internal-brain && python scripts/reset_demo.py` (fresh audit trail for the recording).
3. Start the app against the live site:
   ```bash
   IB_ATLASSIAN_MODE=live IB_ACCOUNT_MAP=accounts.json python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --workers 1
   ```
   Wait for "Application startup complete", open http://127.0.0.1:8000.
4. Second browser tab: Confluence, space **PAYMENTGATEWAY**, page **Runbook: payment-service incident**,
   signed in as the site admin. Check it has **no** restrictions.
5. Third tab: the deck, `docs/deck/index.html`.
6. Rehearse each question once (answers below were checked live on 14 Oct). Close Slack/mail
   notifications. Browser zoom 125%, 1080p or higher.
7. On screen, top corner, a small caption for the whole video:
   **"Live: Confluence + Jira (Atlassian Cloud) · Simulated: Slack, Drive · Answers: extractive mode"**.

---

## 0:00 to 0:25 · Hook (deck slides 1 and 2) · M

> Ask your company assistant a question and it answers from Confluence, Jira, Slack and Drive.
> But each of those has its own permission rules. Copy everything into one index and the assistant
> can show people what they were never allowed to open. And nobody can prove afterwards who saw what.

Slide 2 on "each of those". Pause on the amber callout.

## 0:25 to 1:00 · What YieldGPT does (slides 3 and 4) · M

> YieldGPT answers only from sources you may open right now, and the platforms themselves decide.
> Every candidate goes through six checks: a prefilter, a live check before reading, again after
> reading, again before release, and once more when you open a citation.

Slide 4: let the animation run 5 seconds.

> Anything denied drops out, is recorded, and is never shown. A denied document looks exactly like
> one that never existed.

## 1:00 to 1:55 · Live: one question, four platforms · I

App tab. Sign in as **Jane Doe (jdoe)**. Ask:

**"What's the status of the database migration project and were there any blockers raised in Slack last week?"**

> I'm Jane, a backend engineer. One question. The answer pulls the migration epic and the blocked
> replication-lag ticket from our real Jira site, the engineers' Slack thread, and the cutover
> checklist in Drive.

Open the **Jira MIG-2** citation (status Blocked), then the **Slack** citation.

> Every citation is re-checked when I open it. And the private leads channel Jane isn't in? Never
> appears. Not as a title, not as a hint.

## 1:55 to 2:40 · Negative cases · I

Sign out. Sign in as **Kim Lee (kim)**, the external contractor. Ask:

**"Show me the security incident report from the Q3 breach"**

> Kim has no Atlassian account. She gets a neutral answer.

Ask: **"Show me the unicorn migration to mars report"**

> And this report doesn't exist at all. Same answer, word for word. Kim can't tell whether the breach
> report exists.

Sign in as **Jane** again, ask **"Show me all security vulnerabilities"**: no PAY-4.
Sign in as **Asha Tan (asha)**, same question: PAY-4 appears.

> PAY-4 sits behind a Jira issue security level. Jane can browse the project and is still denied;
> Asha is in the security group. Jira made that decision, not us.

## 2:40 to 3:45 · Live revocation on the real Confluence site · M

Sign in as **Ravi Menon (ravi)**. Ask:

**"What's the latest runbook for the payment-service incident?"**

> Ravi is on call for payments. The runbook comes from our live Confluence space.

Switch to the **Confluence tab**. On the runbook page: **•••** > **Restrictions** > "Only specific
people can view or edit" > add **Asha** > **Apply**. Keep it on screen two seconds.

> I've just restricted the page in Confluence. We don't reindex anything.

Back to the app, ask the **same question** again as Ravi.

> The runbook is gone on the very next query. In our measured live run, the next query was denied
> in 0.27 seconds, and the denial held from then on.

Sign in as **Asha**, ask the same question: the runbook is still there.

> Asha still gets it, because Confluence still allows her.

**After recording:** remove the restriction (Restrictions > "Anyone can view and edit").

## 3:45 to 4:35 · Audit · P

Sign in as **Priya Nair (priya)**, open **/compliance**. Type:

**"Show me everything user 'ravi' accessed related to the 'payment-gateway' Confluence space in the last 30 days"**

> I'm Priya, compliance. I ask in plain language. For each request I get the question, every
> per-document decision, what was released, and the answer.

Point at Ravi's two runbook requests: **allowed** the first time, **denied** after the restriction.

Deck slide 7 (the chain animation).

> Every row is hash-chained. Edit one and every link after it breaks. And no checkpoint, no answer:
> if we can't record it on two write-once stores, the user gets a refusal, never an unrecorded answer.

## 4:35 to 5:25 · Proof (slides 8, 9, 10) · P

Slide 8:

> On a real Atlassian Cloud site: 84 of 84 permission decisions matched Atlassian, 14 of 14 brief
> scenarios passed, and 21 of 21 lifecycle steps, including an inherited page restriction.

Slide 9:

> Under load, 25 users for five minutes: 19,223 answers, zero permission leaks, zero audit gaps.
> These numbers use fixture data and no live model, and the slide says so.

Slide 10:

> Against the original pipeline on the same questions: 65 of 65 instead of 50, and zero false accepts.

## 5:25 to 5:55 · Tencent ecosystem (slide 11) · P

> YieldGPT plugs into CodeBuddy through an MCP connector, with every permission check still applied.
> Answers in this submission are extractive: built on the server, word for word, from passages the
> user may see, each line cited. The adapter for Hunyuan's OpenAI-compatible API is ready and tested,
> so switching the model on is configuration. And the Docker deployment
> is ready for Tencent Cloud.

If the WorkBuddy connector is merged and working on the day, cut in a 5-second clip of a CodeBuddy
chat calling YieldGPT. If not, stay on the slide.

## 5:55 to 6:25 · How we built it with CodeBuddy / WorkBuddy · each of us, ~10 s

The handbook requires the video to include "a short reflection on your build approach and any
development tool tips with reference to CodeBuddy/WorkBuddy". Show one real CodeBuddy or WorkBuddy
chat screenshot per person (the same ones submitted as proof of usage). Fill in from what you
actually did; don't read these placeholders out:

- **M:** one thing CodeBuddy/WorkBuddy did on the connectors or permission checks, and one tip.
  [fill in]
- **I:** one thing on retrieval, grounding or the UI, and one tip. [fill in]
- **P:** one thing on the audit chain, checkpoints or deployment, and one tip. [fill in]

A line that works for all three, if true for you:

> We split the build into three owners with no shared files, so our coding agents could work in
> parallel without stepping on each other.

## 6:25 to 7:00 · Honest status and close (slides 12 and 13) · M

> What's live and verified: Confluence and Jira on a real site, write-once checkpoints, and the full
> test suite on every pull request. What's still pending: switching Hunyuan on, live Slack and
> Drive, the public URL, and human scoring. Every number in this video has a date and a label.

Slide 13.

> YieldGPT. Ask once. See only what you may. Prove it afterwards.

---

## Notes for editing

- Trim waiting time on answers, but never cut between the revoke in Confluence and Ravi's next query:
  that continuity is the proof.
- Blur or crop anything showing an email address, account id, API token or the site URL bar.
- If a live step misbehaves on the day, re-record that segment; don't splice in a fixture run without
  changing the caption to "fixture".
- Update a line here whenever a number changes; the source report is named next to it in the README.
