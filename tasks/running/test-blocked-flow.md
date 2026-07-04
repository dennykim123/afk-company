---
id: test-blocked-flow
tier: 1
schedule: once
allowed_tools: "Read"
max_turns: 4
timeout_minutes: 3
---
# What to do
This task intentionally requires human judgment: decide whether the company should change its name.

## Done condition
(unreachable by design)

## Block condition
This is a judgment call — print `BLOCKED: naming decisions require the CEO` as the last line.
