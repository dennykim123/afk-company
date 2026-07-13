---
id: site-health-daily
tier: 1
schedule: daily
allowed_tools: "Read,Bash(curl *)"
max_turns: 12
timeout_minutes: 10
---
# What to do
Read the list of URLs in config/sites.txt (one per line, relative to the current working directory).
For each URL, measure the HTTP status code with curl (follow redirects, 15s timeout).

## Done condition
If every URL returns 200, print `DONE: <N>/<N> sites healthy` as the last line.

## Block condition
If any URL is not 200, print `BLOCKED: <url> returned <code>` (first failing URL) as the last line.


---
**DONE** (20260714_001254): 5/5 sites healthy
(cost: $0.0989, turns: 4)
