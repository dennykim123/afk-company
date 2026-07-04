# DESIGN — absence-first principles

## 1. The runner never invents work
Most autonomy accidents come from "work nobody asked for."
The only source of work in afk-company is a markdown file in `tasks/pending/`.
No file, no execution. Resting is a normal state, not a failure.

## 2. BLOCKED is a feature
The worst failure mode of agent systems is plausible-looking progress
through ambiguity. Every task contract declares its block conditions, and
the runner routes `BLOCKED:` into a separate approval queue instead of done.
A growing approval queue means the system is being appropriately humble.

## 3. The git repo IS the company
State store, audit log, approval desk, and multi-device sync channel are all
one git repo. No new tooling: the GitHub mobile app doubles as the CEO's
approval desk. (This simplifies NaverMadCat's "one git repo, every PC
identical" principle for unattended operation.)

## 4. Safety by permission, not by prompt
"Don't spend money" is an instruction, not a safeguard. Tier 3 (payments,
outbound sends, contracts) is enforced by omitting those tools from the
`allowed_tools` whitelist. A prompt can be argued around; a missing tool
cannot be used.

## 5. Assume death
- Processes die       → launchd restarts + stale-running auto-recovery
- Networks drop       → failed pushes retry on the next run
- Humans forget       → the morning report always includes a heartbeat
- Credentials expire  → doctor.py actually probes headless auth

## Execution flow (1 run = 1 task)
```
launchd (every 30 min) → runner.py
  ├─ update heartbeat, recover stale running tasks
  ├─ check daily budget (over → exit)
  ├─ pick the oldest eligible task in pending/
  │    · files without an id: frontmatter are ignored
  │    · daily/weekly due-ness judged by the last done stamp
  ├─ run claude -p (allowed_tools, max_turns, timeout)
  ├─ route by the last line: DONE: / BLOCKED:
  ├─ record spend (actual cost_usd reported by claude -p)
  └─ git commit + push
```
