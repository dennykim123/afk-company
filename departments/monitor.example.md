---
id: monitor
tier: 1
schedule: daily
allowed_tools: "Read,Write,WebFetch,WebSearch"
max_turns: 20
timeout_minutes: 30
---
# Daily opportunity monitor

## Job
1. Check the listed sources for announcements posted since yesterday
   (e.g., grant programs, RFPs, industry news — edit for your domain).
2. Keep only items matching your keywords: <keyword1>, <keyword2>, <keyword3>.
3. If there are new matches, save a report to `reports/YYYY-MM-DD.md`
   with: title / deadline / size / one-line fit assessment.

## Done condition
- New items found -> `DONE: N new items (top: <title>, deadline D-XX)`
- Nothing new     -> `DONE: no new items`

## Block condition
- High-fit item with a deadline within 14 days -> `BLOCKED: <title> closes D-XX, decision needed`
