#!/usr/bin/env python3
"""
afk-company telegram bridge
───────────────────────────
Turns Telegram from a one-way report into the company's command channel.
(vooy-style: one message in your messenger → action, with confirmation
 before anything real happens.)

Commands (only from the authorized chat_id — everyone else is ignored):
  /status                  instant company report
  /approve <task-id>       blocked → pending  (re-runs on next cycle)
  /reject <task-id> [why]  blocked → done (archived with your reason)
  /task <free text>        create a new Tier-1 task from your phone
  /budget <usd>            change today's ceiling

Inline buttons: when the runner blocks a task it pushes a message with
[✅ approve] [❌ reject] buttons; tapping them does the same as /approve //reject.

Runs as a launchd KeepAlive daemon (long polling). No webhook, no open port.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
LOGS = ROOT / "logs"
CFG_PATH = ROOT / "config" / "company.json"


def cfg() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def api(method: str, **params):
    c = cfg()
    token = c.get("telegram_token", "")
    if not token:
        raise RuntimeError("telegram_token not configured")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
    ).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def say(text: str, buttons: list | None = None) -> None:
    kw = {"chat_id": cfg().get("telegram_chat_id"), "text": text}
    if buttons:
        kw["reply_markup"] = {"inline_keyboard": buttons}
    api("sendMessage", **kw)


PAIRING_FILE = LOGS / "pairing_code"


def try_pair(chat_id: str, text: str) -> str | None:
    """First-run pairing: if no owner is set and the message equals the code
    printed at install time, claim this chat as the owner. Code is single-use."""
    if cfg().get("telegram_chat_id"):
        return None
    if not PAIRING_FILE.exists():
        return None
    if text.strip() != PAIRING_FILE.read_text().strip():
        return "🔑 Pairing code required. Send the 6-digit code shown at install time."
    c = cfg()
    c["telegram_chat_id"] = chat_id
    CFG_PATH.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PAIRING_FILE.unlink()
    return "🔗 Paired! This chat is now the company command channel.\nJust type to queue a task; /status for the overview."


def find_blocked(task_id: str) -> Path | None:
    hits = sorted((TASKS / "blocked").glob(f"{task_id}*"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


# ── command handlers (pure-ish: testable without Telegram) ──────────

def cmd_status() -> str:
    pending = [f for f in (TASKS / "pending").glob("*.md") if f.name.lower() != "readme.md"]
    blocked = list((TASKS / "blocked").glob("*.md"))
    done_today = [f for f in (TASKS / "done").glob("*.md")
                  if datetime.fromtimestamp(f.stat().st_mtime).date() == datetime.now().date()]
    spend = 0.0
    ledger = LOGS / "spend_ledger.jsonl"
    if ledger.exists():
        today = datetime.now().date().isoformat()
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("date") == today:
                    spend += float(r.get("cost_usd", 0))
            except (json.JSONDecodeError, ValueError):
                pass
    lines = [f"📋 queued {len(pending)} · 🔒 awaiting approval {len(blocked)} · ✅ done today {len(done_today)} · 💸 ${spend:.2f}"]
    for f in blocked[:5]:
        lines.append(f"  🔒 {f.stem}")
    return "\n".join(lines)


def cmd_approve(task_id: str) -> str:
    f = find_blocked(task_id)
    if not f:
        return f"❓ '{task_id}' not found in blocked/"
    # strip the __timestamp suffix so re-run gets a clean id-based name
    clean = re.sub(r"__\d{8}_\d{6}", "", f.name)
    dest = TASKS / "pending" / clean
    text = f.read_text(encoding="utf-8") + f"\n\n---\n**APPROVED** ({datetime.now():%m/%d %H:%M}) via telegram — queued for re-run\n"
    dest.write_text(text, encoding="utf-8")
    f.unlink()
    return f"✅ {task_id} → back in queue. Re-runs next cycle."


def cmd_reject(task_id: str, reason: str = "") -> str:
    f = find_blocked(task_id)
    if not f:
        return f"❓ '{task_id}' not found in blocked/"
    text = f.read_text(encoding="utf-8") + f"\n\n---\n**REJECTED** ({datetime.now():%m/%d %H:%M}): {reason or 'no reason given'}\n"
    dest = TASKS / "done" / f.name.replace(".md", "__rejected.md")
    dest.write_text(text, encoding="utf-8")
    f.unlink()
    return f"❌ {task_id} rejected (record kept)."


def cmd_task(text: str) -> str:
    if not text.strip():
        return "Usage: /task <what to do>"
    ts = datetime.now().strftime("%m%d_%H%M")
    task_id = f"tg-{ts}"
    tools = cfg().get("default_allowed_tools", "Read,Grep,Glob")
    body = f"""---
id: {task_id}
tier: 1
schedule: once
allowed_tools: "{tools}"
max_turns: 25
---
# Telegram directive ({datetime.now():%Y-%m-%d %H:%M})

{text.strip()}

## Rules
- If the instruction is ambiguous or requires destructive changes, do not proceed;
  print `BLOCKED: <reason>` as the last line.
- On success print `DONE: <summary>` as the last line.
"""
    (TASKS / "pending" / f"{task_id}.md").write_text(body, encoding="utf-8")
    return f"📝 Task queued: {task_id}\n(tools: {tools} — read-mostly defaults; raise allowed_tools in the repo for write jobs)"


def cmd_budget(amount: str) -> str:
    try:
        usd = float(amount)
    except ValueError:
        return "Usage: /budget 15"
    c = cfg()
    c["daily_budget_usd"] = usd
    CFG_PATH.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"💸 Daily budget → ${usd:.2f}"


def cmd_feedback(task_id: str, feedback: str) -> str:
    """Reply-to-fix: your reply becomes a directive appended to the contract,
    and the task returns to pending for a re-run. (HITL 'reject with reason →
    agent adapts plan' pattern, without making you choose reject.)"""
    f = find_blocked(task_id)
    if not f:
        return f"❓ '{task_id}' not found in blocked/"
    clean = re.sub(r"__\d{8}_\d{6}", "", f.name)
    text = f.read_text(encoding="utf-8") + (
        f"\n\n## CEO feedback ({datetime.now():%m/%d %H:%M}) — highest priority\n{feedback.strip()}\n"
    )
    (TASKS / "pending" / clean).write_text(text, encoding="utf-8")
    f.unlink()
    return f"↩️ Feedback applied, {task_id} queued for re-run:\n\"{feedback.strip()[:100]}\""


BLOCK_MSG_RE = re.compile(r"Approval needed: (\S+)")


def handle(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1] if len(parts) > 1 else ""
    if cmd == "/status":
        return cmd_status()
    if cmd == "/approve":
        return cmd_approve(arg.strip())
    if cmd == "/reject":
        a = arg.split(maxsplit=1)
        return cmd_reject(a[0] if a else "", a[1] if len(a) > 1 else "")
    if cmd == "/task":
        return cmd_task(arg)
    if cmd == "/budget":
        return cmd_budget(arg.strip())
    return "Commands: /status /approve <id> /reject <id> [why] /task <text> /budget <usd>"


# ── polling loop ─────────────────────────────────────────────────────

def main() -> None:
    offset = 0
    authorized = str(cfg().get("telegram_chat_id", ""))
    print(f"telegram bridge up (authorized chat: {authorized or 'NOT SET'})")
    while True:
        try:
            res = api("getUpdates", offset=offset, timeout=50)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1

                # inline button taps
                cb = upd.get("callback_query")
                if cb:
                    if str(cb["message"]["chat"]["id"]) != authorized:
                        continue
                    action, _, tid = cb.get("data", "").partition(":")
                    reply = cmd_approve(tid) if action == "approve" else cmd_reject(tid, "rejected via button")
                    api("answerCallbackQuery", callback_query_id=cb["id"])
                    say(reply)
                    continue

                msg = upd.get("message") or {}
                chat_id = str(msg.get("chat", {}).get("id"))
                authorized = str(cfg().get("telegram_chat_id", ""))  # re-read: pairing may have just set it
                if not authorized:
                    reply = try_pair(chat_id, msg.get("text", ""))
                    if reply:
                        api("sendMessage", chat_id=chat_id, text=reply)
                    continue
                if chat_id != authorized:
                    continue  # strangers shout into the void
                text = msg.get("text", "")
                if not text:
                    continue

                # reply to an approval card → feedback + re-run
                replied = (msg.get("reply_to_message") or {}).get("text", "")
                m = BLOCK_MSG_RE.search(replied)
                if m and not text.startswith("/"):
                    say(cmd_feedback(m.group(1), text))
                    continue

                if text.startswith("/"):
                    say(handle(text))
                else:
                    # vooy-style: a plain message IS an instruction
                    say(cmd_task(text))
        except KeyboardInterrupt:
            break
        except Exception as e:  # noqa: BLE001 — daemon must survive anything
            print(f"bridge error (retry in 15s): {e}")
            time.sleep(15)


if __name__ == "__main__":
    main()
