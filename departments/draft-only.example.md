---
id: weekly-drafts
tier: 1
schedule: weekly
allowed_tools: "Read,Write,Glob"
max_turns: 20
timeout_minutes: 30
---
# Reply drafts (the correct shape of a Tier-2 job)

⚠️ Principle: "send" does not exist in this system. Files only.

## Job
1. Read unanswered messages exported to `inbox_export/`.
2. Write a reply draft for each to `drafts/YYYY-MM-DD_<sender>.md`.
3. Put a [NEEDS JUDGMENT] section at the top of each draft
   (amounts, schedule commitments, contract language, etc).

## Done condition
- `DONE: N drafts created, M need judgment`

## Block condition
- A message demands a legal/financial commitment -> `BLOCKED: <sender> requires your decision`
