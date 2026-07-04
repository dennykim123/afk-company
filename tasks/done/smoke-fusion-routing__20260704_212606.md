---
id: smoke-fusion-routing
tier: 1
schedule: once
allowed_tools: "Read,Glob"
max_turns: 6
timeout_minutes: 5
---
# What to do
Count the number of .md files in the departments/ directory of the current working directory and report the count.

## Done condition
Print `DONE: <count> department example files` as the last line.

## Block condition
If the directory cannot be read, print `BLOCKED: <reason>`.


---
**DONE** (20260704_212606): 3 department example files
(cost: $0.1134, turns: 2)
