---
id: benefit-crawl-daily
tier: 1
model: sonnet
schedule: daily
allowed_tools: "Read,Write,Edit,Bash(node *),Bash(curl *),WebFetch,WebSearch"
max_turns: 40
timeout_minutes: 20
---
# What to do
AI 혜택 레이더(https://aicredits.vercel.app)의 후보 수집·검증 파이프라인 일일 실행.
전체 규칙: /Users/m4/Documents/buyornot/data/crawl/README.md 를 먼저 읽어라.

1. `node /Users/m4/Documents/buyornot/scripts/crawl-benefits.mjs` 실행 (새 후보 수집).
2. /Users/m4/Documents/buyornot/data/crawl/queue.json 에서 status가 "new"인 항목마다:
   a. 기사를 열어 어떤 혜택인지 파악한다.
   b. 다음 전부에 해당하면 검증 진행, 아니면 status를 "rejected"로 바꾸고 rejectReason 기록:
      - 개인 개발자·학생·스타트업이 직접 신청할 수 있는 AI 크레딧/해커톤/공모전/지원 프로그램이다
      - /Users/m4/Documents/buyornot/src/lib/credit-services.ts 에 같은 항목이 없다 (이름·주최·applyUrl로 검색)
      - 마감이 지나지 않았다
   c. 검증: 공식 공고 페이지(기사 말고 주최기관 페이지)를 찾고, 신청 URL을 curl로 열어
      상태코드를 실측하고, 마감일·혜택 내용을 공식 공고에서 확인한다.
   d. 전부 확인되면 README.md의 제안서 JSON 양식대로
      /Users/m4/Documents/buyornot/data/crawl/proposals/<YYYY-MM-DD>-<슬러그>.json 을 쓰고
      queue.json의 해당 항목 status를 "proposed", proposalPath를 기록한다.
      하나라도 확인 못 하면 "rejected" + rejectReason.
3. 절대 금지: src/lib/credit-services.ts 수정, 배포, git 조작. 제안서 작성까지만 한다.

## Done condition
Print `DONE: crawl new=<n> proposed=<p> rejected=<r>` as the last line.

## Block condition
If the crawler script fails or queue.json is unreadable, print `BLOCKED: <reason>` as the last line.


---
**BLOCKED** (20260722_020642): no verdict marker (exit 1)
(cost: $1.0673, turns: 19)
