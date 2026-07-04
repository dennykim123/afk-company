# 🏢 afk-company

> **사장이 두 달 자리를 비워도 돌아가는 1인 회사.**
> A one-person company that keeps running while the CEO is away for two months.

[English README](README.md)

멀티에이전트 오케스트레이션 프레임워크가 아닙니다. 그 반대입니다 —
**당신이 없다는 전제(absence-first)로 설계된, Claude Code 위의 최소 무인 운영 스택**입니다.

```
당신 (지구 반대편, 폰만 있음)
 │  하루 5분: 텔레그램 일일보고 확인 + 결재
 ▼
GitHub repo  ←──  회사의 장부이자 결재판이자 동기화 채널
 ▲
 │  30분마다
Mac mini (launchd) ── runner.py ── claude -p (도구 화이트리스트)
                          │
              tasks/pending → running → done
                                └─────→ blocked  ← "사람 판단 필요" 는 실패가 아니라 기능
```

## 왜 이게 다른가

에이전트 프레임워크들은 "AI가 얼마나 많이 할 수 있는가"를 자랑합니다.
afk-company는 반대 질문에서 시작합니다: **"당신이 없을 때 무엇이 망가지는가?"**

| 망가지는 방식 | afk-company의 답 |
|---|---|
| AI가 폭주해서 이상한 걸 만듦 | 작업 파일에 명시된 것만 실행. 러너는 일을 만들어내지 않음 |
| 토큰 요금 폭탄 | 일일 지출 상한. 초과 시 회사는 그냥 쉼 |
| 애매한 상황에서 억지로 진행 | `BLOCKED:` 마커 하나로 멈추고 결재 대기 |
| 프로세스가 죽고 아무도 모름 | heartbeat + 매일 아침 생존 보고 |
| 뭘 했는지 알 수 없음 | 모든 상태 변화가 git 커밋. 레포가 곧 감사 로그 |
| 돈·발송·계약 사고 | Tier 3 금지 구역: 애초에 도구를 안 줌 |

## 3-Tier 자율성 모델

- **Tier 1 — 무인 실행**: 결정적이고, 검증 가능하고, 되돌릴 수 있는 것. (배치 처리, 모니터링, 수집)
- **Tier 2 — 초안까지만**: 메일 회신, 지원서, 제안서. 파일 생성까지. **발송 버튼은 자동화하지 않는다.**
- **Tier 3 — 금지**: 결제, 계약, 외부 발송, 배포. 프롬프트로 막는 게 아니라 도구 화이트리스트에서 뺀다.

## 빠른 시작

```bash
git clone https://github.com/YOU/afk-company && cd afk-company
./install.sh                      # launchd 등록 + 진단
vi config/company.json            # 텔레그램 토큰, 일일 예산
cp departments/ocr-batch.example.md tasks/pending/my-first-task.md
python3 bin/runner.py             # 수동 1회 실행으로 확인
python3 bin/doctor.py             # 전부 ✅ 이면 출장 가세요 ✈️
```

## 작업 파일 = 직원

작업 하나가 마크다운 한 장입니다. frontmatter가 근로계약서입니다.

```markdown
---
id: ocr-batch
tier: 1
schedule: daily          # once | daily | weekly
allowed_tools: "Read,Write,Bash(python3 *)"   # 이것 외엔 물리적으로 못 씀
max_turns: 40
timeout_minutes: 60
---
# 할 일
...
## 완료 조건 → 마지막 줄에 DONE: <요약>
## 차단 조건 → 마지막 줄에 BLOCKED: <사유>   ← 억지로 진행하지 말 것
```

## 부재 중 운영 루프

1. 매일 아침 텔레그램 1통: ✅완료 / 🔒결재대기 / 💸지출 / ❤️생존
2. 작업이 차단되는 **즉시** 푸시 알림 + **[✅승인] [❌반려]** 인라인 버튼 — 탭 한 번으로 결재 끝
3. 텔레그램이 곧 지휘 채널: `/status`, `/approve <id>`, `/reject <id> [사유]`, `/task <지시>` 로 폰에서 새 작업 투입, `/budget <usd>`
4. GitHub 모바일은 백업 결재 창구 (`tasks/blocked/` 파일 직접 편집)

## 정직한 한계

- 2개월 **완전** 무인은 불가능합니다. OAuth는 만료되고 CLI는 업데이트됩니다. 이 시스템의 목표는 "무인"이 아니라 **"하루 5분 관리로 축소"**입니다.
- macOS + launchd 기준입니다 (Linux는 systemd timer로 치환 가능, PR 환영).
- Claude Code 구독(요금제 한도) 기준으로 설계됐습니다. API 키 직결 시 예산 상한을 반드시 확인하세요.

## 영감

- NAVER Engineering Day 2026 "AI 에이전트 회사 차리기" (신동민) — 조직 은유, 라이프사이클 훅, git 동기화
- Daniel Miessler의 PAI — 개인 AI 인프라라는 관점

차이점: 저들은 **당신이 자리에 있을 때** 더 강해지는 시스템이고, 이건 **당신이 없을 때** 죽지 않는 시스템입니다.

## License

MIT
