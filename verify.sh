#!/bin/bash
# afk-company verification suite — behavior tests with a mock claude binary
set -u
cd "$(dirname "$0")"
PASS=0; FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

[ -f config/company.json ] || cp config/company.example.json config/company.json
FAKE=/tmp/fakebin; mkdir -p $FAKE
reset() {
  rm -rf tasks/pending/*.md tasks/running/*.md tasks/done/*.md tasks/blocked/*.md \
         logs/spend_ledger.jsonl logs/heartbeat logs/*.out.txt 2>/dev/null
  cat > tasks/pending/README.md << 'EOF'
info file (not a task)
EOF
}
mktask() { # $1=id $2=schedule
  cat > "tasks/pending/$1.md" << EOF
---
id: $1
tier: 1
schedule: $2
max_turns: 5
timeout_minutes: 1
---
# test task $1
EOF
}
set_claude() { # $1=script body
  printf '#!/bin/bash\n%s\n' "$1" > $FAKE/claude; chmod +x $FAKE/claude
  python3 - << EOF
import json,pathlib
p=pathlib.Path("config/company.json"); c=json.loads(p.read_text())
c["claude_bin"]="$FAKE/claude"; c["daily_budget_usd"]=10.0
p.write_text(json.dumps(c,indent=2))
EOF
}

git init -q 2>/dev/null; git config user.email t@t; git config user.name t
git add -A >/dev/null 2>&1; git commit -qm base >/dev/null 2>&1

echo "── 1. DONE routing + spend ledger"
reset; mktask t1 once
set_claude 'echo "{\"result\":\"ok\nDONE: success\",\"total_cost_usd\":0.05,\"num_turns\":2}"'
python3 bin/runner.py >/dev/null 2>&1
[ -n "$(ls tasks/done/t1__*.md 2>/dev/null)" ] && ok "moved to done/" || bad "moved to done/"
grep -q '"cost_usd": 0.05' logs/spend_ledger.jsonl && ok "spend recorded" || bad "spend recorded"
[ -z "$(ls tasks/pending/t1.md 2>/dev/null)" ] && ok "once task removed from pending" || bad "once task lingered"

echo "── 2. BLOCKED routing"
reset; mktask t2 once
set_claude 'echo "{\"result\":\"issue found\nBLOCKED: needs human judgment\",\"total_cost_usd\":0.01,\"num_turns\":1}"'
python3 bin/runner.py >/dev/null 2>&1
f=$(ls tasks/blocked/t2__*.md 2>/dev/null | head -1)
[ -n "$f" ] && ok "moved to blocked/" || bad "moved to blocked/"
grep -q "needs human judgment" "$f" 2>/dev/null && ok "block reason kept" || bad "block reason kept"

echo "── 3. no verdict marker → blocked (safe default)"
reset; mktask t3 once
set_claude 'echo "just some words"'
python3 bin/runner.py >/dev/null 2>&1
[ -n "$(ls tasks/blocked/t3__*.md 2>/dev/null)" ] && ok "markerless output → blocked" || bad "markerless handling"

echo "── 4. daily budget gate"
reset; mktask t4 once
echo "{\"date\": \"$(date +%F)\", \"cost_usd\": 99.0, \"task\": \"x\", \"turns\": 1}" > logs/spend_ledger.jsonl
set_claude 'echo "{\"result\":\"DONE: must not run\",\"total_cost_usd\":1,\"num_turns\":1}"'
out=$(python3 bin/runner.py 2>&1)
echo "$out" | grep -q "budget reached" && ok "over budget → no run" || bad "budget gate"
[ -n "$(ls tasks/pending/t4.md 2>/dev/null)" ] && ok "task not consumed (retries tomorrow)" || bad "task consumed"

echo "── 5. daily schedule: skip if recent, original stays"
reset; mktask t5 daily
set_claude 'echo "{\"result\":\"DONE: run 1\",\"total_cost_usd\":0.01,\"num_turns\":1}"'
python3 bin/runner.py >/dev/null 2>&1
[ -n "$(ls tasks/pending/t5.md 2>/dev/null)" ] && ok "daily original stays in pending" || bad "daily original lost"
out=$(python3 bin/runner.py 2>&1)  # 2nd run same day
echo "$out" | grep -q "idle" && ok "re-run within 20h skipped" || bad "daily double-run"

echo "── 6. stale running auto-recovery"
reset; mktask t6 once
mv tasks/pending/t6.md tasks/running/t6.md
touch -d "4 hours ago" tasks/running/t6.md 2>/dev/null || touch -t $(date -d "-4 hours" +%Y%m%d%H%M) tasks/running/t6.md
set_claude 'echo "{\"result\":\"DONE: recovered and finished\",\"total_cost_usd\":0.01,\"num_turns\":1}"'
python3 bin/runner.py >/dev/null 2>&1
[ -n "$(ls tasks/done/t6__*.md 2>/dev/null)" ] && ok "dead running recovered → re-run" || bad "stale recovery"

echo "── 7. timeout → blocked"
reset; mktask t7 once
set_claude 'sleep 90'
python3 bin/runner.py >/dev/null 2>&1
f=$(ls tasks/blocked/t7__*.md 2>/dev/null | head -1)
grep -q "timeout" "$f" 2>/dev/null && ok "timeout → blocked with reason" || bad "timeout handling"

echo "── 8. contract-less files ignored + heartbeat"
reset
cat > tasks/pending/notes.md << 'EOF'
# note file without id
EOF
out=$(python3 bin/runner.py 2>&1)
echo "$out" | grep -q "idle" && ok "files without id ignored" || bad "contract-less file ran"
[ -f logs/heartbeat ] && ok "heartbeat updated" || bad "no heartbeat"

echo "── 9. daily report"
reset; mktask t9 once
set_claude 'echo "{\"result\":\"DONE: for report\",\"total_cost_usd\":0.03,\"num_turns\":1}"'
python3 bin/runner.py >/dev/null 2>&1
rep=$(python3 bin/daily_report.py 2>&1)
echo "$rep" | grep -q "done 1" && ok "report: done count" || bad "report done count"
echo "$rep" | grep -q '0.03' && ok "report: spend total" || bad "report spend total"

echo "── 10. telegram bridge handlers"
reset
cat > tasks/blocked/t10__20260101_000000.md << 'EOT'
---
id: t10
tier: 1
---
# blocked task
EOT
python3 - << 'EOT'
import sys; sys.path.insert(0, "bin")
import importlib.util
spec = importlib.util.spec_from_file_location("bridge", "bin/telegram_bridge.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
r1 = b.handle("/approve t10")
assert "back in queue" in r1, r1
import pathlib
assert pathlib.Path("tasks/pending/t10.md").exists(), "approve did not move file"
r2 = b.handle("/task test instruction")
assert "queued" in r2, r2
assert list(pathlib.Path("tasks/pending").glob("tg-*.md")), "task not created"
r3 = b.handle("/budget 15")
import json
assert json.loads(pathlib.Path("config/company.json").read_text())["daily_budget_usd"] == 15.0
r4 = b.handle("/status")
assert "queued" in r4
# reject path
pathlib.Path("tasks/blocked/t11__20260101_000000.md").write_text("---\nid: t11\n---\n# x")
r5 = b.handle("/reject t11 not needed")
assert "rejected" in r5 and list(pathlib.Path("tasks/done").glob("t11__*rejected.md"))
print("bridge-handlers-ok")
EOT
[ $? -eq 0 ] && ok "approve/reject/task/budget/status all work" || bad "bridge handlers"
# restore budget
python3 -c "
import json,pathlib
p=pathlib.Path('config/company.json'); c=json.loads(p.read_text()); c['daily_budget_usd']=10.0
p.write_text(json.dumps(c,indent=2)+'\n')"

echo "── 11. reply-to-fix feedback loop"
reset
cat > tasks/blocked/t12__20260101_000000.md << 'EOT'
---
id: t12
tier: 1
---
# feedback target
EOT
python3 - << 'EOT'
import sys, importlib.util, pathlib
spec = importlib.util.spec_from_file_location("bridge", "bin/telegram_bridge.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
r = b.cmd_feedback("t12", "redo with table output")
assert "queued for re-run" in r, r
f = pathlib.Path("tasks/pending/t12.md")
assert f.exists() and "CEO feedback" in f.read_text() and "table output" in f.read_text()
m = b.BLOCK_MSG_RE.search("Approval needed: ocr-batch")
assert m and m.group(1) == "ocr-batch"
print("feedback-ok")
EOT
[ $? -eq 0 ] && ok "reply → feedback injected → back to pending" || bad "feedback loop"

echo ""
echo "════════════════════════"
echo "PASS: $PASS  FAIL: $FAIL"
echo "── 12. telegram pairing"
reset
python3 - << 'EOT'
import sys, importlib.util, pathlib, json
spec = importlib.util.spec_from_file_location("bridge", "bin/telegram_bridge.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
cfgp = pathlib.Path("config/company.json"); c = json.loads(cfgp.read_text())
c["telegram_chat_id"] = ""; cfgp.write_text(json.dumps(c, indent=2))
pathlib.Path("logs/pairing_code").write_text("123456")
r = b.try_pair("999", "wrong")
assert r and "Pairing code required" in r, r
r = b.try_pair("999", "123456")
assert r and "Paired" in r, r
c2 = json.loads(cfgp.read_text())
assert c2["telegram_chat_id"] == "999"
assert not pathlib.Path("logs/pairing_code").exists(), "code must be single-use"
assert b.try_pair("888", "123456") is None, "already paired -> no takeover"
c2["telegram_chat_id"] = ""; cfgp.write_text(json.dumps(c2, indent=2) + "\n")
print("pairing-ok")
EOT
[ $? -eq 0 ] && ok "code check · single-use · no takeover" || bad "pairing"

echo ""
echo "════════════════════════"
echo "PASS: $PASS  FAIL: $FAIL"
[ $FAIL -eq 0 ] && echo "all scenarios passed" || echo "failures need attention"
exit $FAIL
