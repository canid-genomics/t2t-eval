# Test 2 assessment: ROS_Cfam_2.0 evaluation run by two Claudes over WG

**Status: DRAFT.** This version has the **sf lane only** (Steven's side), written by Steven's Claude on
2026-11-23. Authorship: Steven's **interactive** Claude session wrote this draft, the final M03
render, #15 and every review and merge listed for the sf side, not a wg worker. The sf wg graph's
`sf/M03` task stayed paused and never ran (§3). The jc lane's sections are to be added by Jonah's Claude. Neither human has approved
it. The joint version needs both humans' approval.

**Scope:** the process, not the biology. The results are in `reports/jc/M01/`, `reports/sf/M02/` and
`reports/sf/M03/` and stand as signed off. This report asks what it took to produce them, what broke,
what caught each break, and what each human gate was worth.

**Evidence:**
- git history on `main` (commit messages carry wg task ids);
- the PRs (#1–#15) and their reviews;
- tickets (agate job ids);
- `PROVENANCE.md`, `HANDOFFS.md`, `LESSONS.md`;
- the sf wg graph (`wg list` / `wg show`);
- the append-only discussion log both Claudes keep beside the WG mailbox.

Times are US Central (CST) unless marked Z (UTC, as GitHub reports them).

**Convention (from the phrs deep dive):** a sentence beginning *Interpretation:* is the author's
reading. Everything else cites evidence.

---

## 1. Summary (sf lane)

- **Delivered:** M02 (agate telomere-motif scan, 156 chromosome ends) and M03 (local per-chromosome
  table + figure joining M01 and M02). Both summaries are signed off by Steven, with descriptive
  counts only. Main has 30 sf commits, all carrying an `sf/` task id, and 12 sf PRs, all merged.
- **Elapsed vs compute:**
  - Elapsed: about 21 h from the scaffold (Nov 22 11:41) to the M03 sign-off (Nov 23 ~09:00), plus a threshold revision merged ~13:15.
  - Compute: the sf lane used about 10 core-minutes on agate (one failed 3-min job, one 7-min job).
  - Nearly all the elapsed time was waiting for the other lane or a human, mostly overnight.
- **What went well:**
  - Two Claudes ran separate lanes with cross-review.
  - M03's code was written and tested on synthetic fixtures before M01 existed. As a result, the M03 PR was up 7 minutes after M01 reached main (#11 merged 14:43Z, #12 opened 14:50Z).
  - Every number in the M02 and M03 summaries was re-derived from the tables before sign-off.
- **What went wrong (§4, §7):**
  - The two most consequential catches came from **Jonah reading the work as a human**, not from either Claude's review: the 10 kb end definition, and the objection to custom code where a published tool exists.
  - Steven's Claude merged #9 six minutes before a re-review arrived.
  - Steven's Claude then stopped polling and put M03 to Steven without that re-review, so the M03 sign-off gate saw incomplete information.
- **Main lesson:**
  - *Interpretation:* the plumbing failures were cheap and caught by machines: a failed job, a refused ticket, CI.
  - The costly ones were judgment calls that both Claudes passed: tool choice and the threshold definition.
  - Those need a named review question and a human reading, not more automation.

## 2. Timeline (sf lane, with the joint milestones)

| When | What | Evidence |
|---|---|---|
| Nov 22 11:41 | jc scaffold pushed (`/new-wg-snake`) | first commit on main |
| ~12:00 | sf lane set up; sf wg graph published (M02 chain + M03); Opus worker on `sf/M02-ticket` | wg graph |
| 12:25–12:35 | M02 worker blocked twice: a local settings `ask` rule reached its worktree; an in-worktree `.pixi/` (~17k files) deadlocked the wg daemon | log; LESSONS.md; AGENTS.md "no pixi in worktree" |
| 12:35 | Steven: SPEC rows M01–M04 agreed ("This all is okay with me"); standing OK to push PR branches | round 5 |
| 18:27Z–20:53Z | PRs #1 (scaffold fixes), #2 (lane rules + sf agate exception), #3 (M02) reviewed by Jonah's Claude, merged by Jonah | PRs |
| ~14:20 | #2/#3 idle ~1 h: Jonah had no notification path. GitHub review requests became the PR channel | log |
| 14:58 | **First Claude-submitted agate job:** M02 job 7851561 | `tickets/sf/M02.md` |
| 15:01 | 7851561 **failed** after 3 min: image pinned without `docker://` (scaffold convention bug) | ticket Attempts 1 |
| 16:18 | #4 (docker:// URIs + parse-time guard) merged | PR #4 |
| 16:22–16:28 | M02 attempt 2, job 7853288: **completed in 7 min**, 156 rows on Tier 2 | ticket Attempts 2 |
| 16:50–16:55 | M02 report + draft summary (#6). Steven: "Approved" | PROVENANCE row; `6116925` |
| ~18:00 | Steven: "We need more speed". sf Claude may self-merge lane-only PRs | round 7 |
| 18:15–18:20 | #8 (pixi `fig` env) and #9 (M03 code on synthetic fixtures) opened before M01 ran | PRs #8, #9 |
| 23:15 | Merging #6 after #5 made the jc M01 ticket refusable at main HEAD (only `reports/sf` + logs differed). M01 submitted from `36b870d` instead | log; PR #10 motivation |
| 23:55 | M01 job 7865313 completed (jc) | jc ticket |
| Nov 23 12:40Z | Jonah's Claude reviews #9: M03's 1 kb default disagrees with M02's approved 100 kb reading (142 vs 147) | #9 review 1 |
| ~07:05 | Steven chose 100 kb (match M02) | `ed4fb16`; NEEDS-HUMAN |
| 14:43Z | Jonah merged #11 (M01 report) | PR #11 |
| **14:48Z** | **Steven's Claude merged #9** as lane-only (it was not: it touched `tests/sf/`, which both review) | PR #9 |
| **14:54Z** | Jonah's Claude re-reviews #9 for Jonah: **10 kb** is a better definition of "at the end" | #9 review 2 |
| 14:50Z–15:01Z | M03 rendered on main's M01 + M02 → #12; Steven signs off; merged | PR #12; `dfa3429` |
| 15:02Z | Jonah's Claude's msg 22 (10 kb; lane-only should wait on open reviews). **Not seen by Steven's Claude**, whose polling had stopped | WG; log |
| 15:46Z | msg 23: Jonah objects to custom Python where tools exist; rev 6 "tools-first" proposal | WG |
| ~12:30 CST | Steven's Claude finds msgs 22/23 from Jonah's side log while drafting this report | log (timestamps corrected 13:17) |
| ~12:55 CST | Steven agrees: 10 kb, tools-first rev 6 items 1–5, a refined lane-only rule. #15 (10 kb; table byte-identical) | round 9; PR #15 |
| 19:08Z | Jonah's Claude approves #15; merged | PR #15 |

## 3. Effort vs what survived (sf lane)

| Work | Size | Status after test 2 |
|---|---|---|
| `workflow/scripts/sf/telomere_scan.py` | 287 lines | M02 result stands. Going forward, superseded by tidk under rev 6 (M02b compares them) |
| `workflow/scripts/sf/telomeres_publish.py` | 170 lines | Near-duplicate of jc's publisher. To be replaced by the shared publisher (#14, rev 6 item 5) |
| `workflow/scripts/shared/ncbi_fetch.py` (first written in sf) | 130 lines | Moved to shared for M01. *Interpretation:* candidate for NCBI `datasets` + `md5sum -c` |
| `workflow/scripts/sf/completeness.py` (M03) | 474 lines | Survives as glue (join + plot). *Interpretation:* heavy for glue; the figure code is most of it |
| `tests/sf/` | 782 lines | Survive with the code they test |
| Scaffold fixes (#1), lane rules + sf agate exception (#2), docker:// guard (#4), follow-ups (#7), relaxed ticket check (#10), lane-prefix rule (#13) | 6 PRs | All survive; #10 already prevented a repeat of the #6-after-#5 ticket refusal |
| M03 threshold | 3 values | 1 kb (worker default) → 100 kb (Steven, to match M02) → **10 kb** (Jonah's proposal). The counts are the same at 100 kb and 10 kb (147/156) |
| wg task `sf/M03` | paused | Never ran. The final M03 was done by Steven's interactive Claude once M01 landed. The graph shows it paused, which is accurate |

*Interpretation:* about 1,060 lines of sf Python plus 780 lines of tests produced two
results that would have needed a fraction of that with tidk and a shared publisher. The worker brief
for M02 said "Prefer a standard tool (e.g. `tidk search --string TTAGGG`) or a short, testable Python
`script:`" (wg task `sf/M02-ticket`). The worker took the second option. Neither Claude's review
asked whether a tool already did the job. That review question is now rev 6 item 3.

## 4. Failures and what caught them (sf lane)

| # | Failure | Caught by | Cost | Fix |
|---|---|---|---|---|
| F1 | Images pinned without `docker://`, so apptainer looked for a local path (scaffold convention) | **the agate run** (job 7851561); dry runs and CI can't see it | 3 min of compute, ~1.3 h of elapsed time | #4: `docker://` URIs and a Snakefile parse-time guard. The same bug in M01's gfastats pin was caught by Steven's Claude's review of #5 |
| F2 | Step-log names contained a literal `{assembly}` | the same failed run | — | `wildcards_pattern=wc.assembly` |
| F3 | A local settings `ask` rule blocked worker commits in nested worktrees | the worker could not commit | worker attempts | interactive settings moved outside the clone (#7); LESSONS entry |
| F4 | An in-worktree `.pixi/` deadlocked the wg daemon | Steven's Claude saw the stall | a stalled worker | AGENTS.md: no pixi in worker worktrees |
| F5 | An untracked file in the main checkout blocked wg landing | wg refused to land | minutes | moved the file out |
| F6 | `wg resume sf/M02-run` also un-paused downstream `sf/M03` | Steven's Claude | none (re-paused) | noted in the sf setup notes |
| F7 | A merge in one lane made the other lane's pending ticket refusable (#6 after #5) | Steven's Claude, watching the M01 submit | M01 submitted from an older commit | #10: the ticket check ignores the other lane's folders and the append-only logs |
| F8 | M03's 1 kb default silently disagreed with M02's approved reading (142 vs 147 ends) | **Jonah's Claude**, reviewing #9 | one decision round | Steven's decision; README names the five ends |
| F9 | 100 kb is a search window, not a definition of "at the end": it would count an array 80 kb in | **Jonah**, reading #9 | one more round + #15 | 10 kb; counts unchanged |
| F10 | #9 merged 6 min before Jonah's re-review; #12 merged without polling | Steven's Claude, ~3.5 h later, reading the jc side log | Steven signed off M03 without the 10 kb proposal in front of him | refined lane-only rule (round 9); poll and re-check reviews before every merge |
| F11 | #9 classified lane-only although it touched `tests/sf/` | Steven's Claude, while scoping #15 | merged without the other side's approval | rule restated in the merge checklist |
| F12 | Custom telomere scanner where tidk exists | **Jonah**, reading the code after the fact | ~460 lines that rev 6 retires | rev 6 tools-first; M02b |
| F13 | #13 changed AGENTS.md without CLAUDE.md (must be identical) | Jonah's Claude, reviewing #13 | one review round | copied; `cmp` clean |
| F14 | The M02b ticket (jc, #14) pins a commit that predates #13, so it would be refused at main HEAD | Steven's Claude, reviewing #14 | not yet incurred | re-ticket after merging main (review note) |
| F15 | **The WG mailbox silently stopped carrying messages** in both directions from ~10:22 CST. Google Drive for desktop on Steven's Mac had hung: the instance running since Nov 13 stayed alive beside an auto-restarted one, from 16:59. Steven's Claude's sends (13:05, 13:20) never left the Mac, and Jonah's msgs 24–25 never arrived. Every poll returned `consumable: 0`, which read as "nothing new" | **Jonah's Claude**, noticing that nothing from the sf side had arrived; relayed by Jonah over Slack at 21:01 | ~10.5 h of one-way silence. GitHub and a Slack relay carried the work meanwhile | Drive restarted 21:05 (with Steven's OK). Proposal: a liveness check, e.g. compare the other side's log mtime, or echo a heartbeat, so a dead transport doesn't look like a quiet peer |

*Interpretation:* F1–F7 and F13–F15 were mechanical, and a machine or a careful read caught each
within minutes. F8–F12 were about meaning or process. Two of them (F9, F12) were caught only by a
human reading the work. F10–F11 were caught by the author, late.

## 5. Human gates (Steven) and what each was worth

| Gate | Decision | Changed the outcome? |
|---|---|---|
| Repo, org, visibility, Tier 2 layout (rounds 2–3) | neutral org, public repo, one bucket with lane folders | Enabling; nothing to catch |
| SPEC rows M01–M04 (round 5) | agreed as written | No. *Interpretation:* the row said "telomere-motif scan" without a tool, and the gate didn't ask. Rev 6 adds a `tool` column so this gate sees it |
| sf agate exception (A2 within caps) | Claude submits sf jobs | Yes for speed: M02 was resubmitted within an hour of the fix, with no human in the loop. Caps were never approached (~10 of 120,000 core-min) |
| Standing OKs: push branches, approve Jonah's PRs, self-merge lane-only and approved PRs (rounds 4, 6, 7) | granted | Yes for speed. The self-merge OK also enabled F10 |
| M02 summary sign-off | "Approved", as drafted | No change. An accountability gate; every number had been re-derived before |
| M03 threshold (1 kb vs 100 kb) | 100 kb, to match M02 | Resolved F8, but chose the looser value. Revised to 10 kb after Jonah's argument |
| M03 sign-off | "Approved", as drafted | **Weakened by F10**: made without Jonah's 10 kb proposal, which had been posted 5 min after #12 opened |
| Round 9 (10 kb, tools-first, merge rule) | agreed | Yes: changes the project's rules from test 3 on |

*Interpretation:* Steven's gates were fast, usually minutes from a push notification, and mostly
confirmatory. The gates that changed outcomes were decisions between options a Claude had laid out.
None of Steven's gates caught an error the Claudes had missed. On the jc side, Jonah's reading did
twice (F9, F12).

## 6. Cost (sf lane)

- **Agate:** ~10 core-minutes. Job 7851561: 3 min, failed before any download. Job 7853288: 7 min (1 core per step, five step jobs). Scratch was ~1.5 GB, against caps of 2,000 core-h and 500 GB.
- **Tier 2:** one run folder, 7 objects.
- **Claude:**
  - not metered in this report;
  - wg workers (Opus) ran 7 sf tasks, and `sf/M02-ticket` took 5 attempts, mostly blocked by F3/F4;
  - Steven's interactive Claude ran a 10-minute polling driver for most of the ~21 h, cheap per tick but continuous.
- **Human time (Steven):** about 15 decisions or approvals across rounds 2–9, almost all answered from a phone within minutes.

## 7. What Steven's Claude got wrong

| Error | Effect | Caught by |
|---|---|---|
| Ran `spec2wg --apply` before both humans had agreed the SPEC rows | graph created early; disclosed; rows then agreed unchanged | own check against protocol §6 |
| Printed a credential value into a local session transcript (not pushed anywhere) | disclosed to Steven; handled per his decision | own check |
| @-mentioned both owners in a PR body | an unwanted notification | own check |
| M02 worker brief allowed custom Python as an equal option to tidk | F12 | Jonah |
| Merged #9 without re-checking for a pending re-review; misclassified it as lane-only | F10, F11 | own reading, late |
| Stopped polling the mailbox once M03 looked done, and merged #12 without a final poll | Steven's M03 sign-off missed msg 22 | own reading, ~3.5 h later |
| Changed AGENTS.md without CLAUDE.md (#13) | one review round | Jonah's Claude |
| Logged estimated timestamps as if read from a clock (two entries, 2 h off) | log accuracy | own check (corrected by an appended line) |
| WG send and poll invoked with missing flags | silent no-op / error, retried | the tool's error message |
| Read `consumable: 0` for ~10 h as "Jonah's side is quiet" without checking that the transport worked (F15). The same afternoon I had looked at Jonah's inbox folder and seen my 13:05/13:20 files there locally, and wrongly took that as delivery | Steven, and Jonah's Claude, waited on messages that never arrived | Jonah's Claude |

## 8. Carry into rev 6 / test 3 (sf view)

1. **Tools-first** (agreed, round 9): every measurement runs a citable tool in a pinned container, and custom code is glue only. The SPEC `tool` column makes the tool choice part of the SPEC gate.
2. **Merge checklist for Claudes**, done right before any merge:
   - re-read that PR's reviews and comments;
   - poll the mailbox;
   - confirm every changed path is in a lane folder (`tests/<lane>/` is not).
   - Lane-only PRs wait on unresolved comments, reviews, or review requests a person made (round 9).
3. **Keep watching after "done":** don't stop polling while anything just merged could still draw a reply.
4. **Write the threshold rationale next to the threshold** (as `completeness.py` now does), so a reviewer can argue with it.
5. **Timestamps from `date`**, never estimated, in any evidence log.

---

## jc lane

*(To be added by Jonah's Claude: timeline, effort vs survival, failures and catches, Jonah's gates,
cost, what Jonah's Claude got wrong.)*

## Joint conclusions

*(After both lanes are in; for both humans to approve.)*
