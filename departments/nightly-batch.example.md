---
id: nightly-batch
tier: 1
model: haiku
schedule: daily
workdir: ~/projects/my-pipeline
allowed_tools: "Read,Write,Glob,Grep,Bash(python3 *),Bash(ls *)"
max_turns: 40
timeout_minutes: 60
---
# Nightly batch processing (unattended)

## Job
1. Read `progress.json` to find the last completed item.
2. Process the next 10 items from `input/` in order.
3. Write each result to `output/<item>.md` following the rules in `FORMAT.md`.
4. Self-verify each result: required fields present, output non-empty.
5. Only items that pass verification get recorded in `progress.json`.

## Done condition
- All 10 items pass -> `DONE: items N-M complete (X/total)`

## Block conditions (never push through)
- An input item is unreadable/corrupted -> `BLOCKED: item N unreadable, needs human review`
- Format verification fails 3 times in a row -> `BLOCKED: format rules need clarification`
- No items left in input/ -> `BLOCKED: batch finished — final review requested`
