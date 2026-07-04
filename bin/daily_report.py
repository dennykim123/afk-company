#!/usr/bin/env python3
"""
afk-company daily report
────────────────────────
Runs once a day (launchd). Sends ONE Telegram message:

  ✅ what got done in the last 24h
  🔒 what is blocked and waiting for your approval
  💸 what it cost
  ❤️ heartbeat status (is the company alive?)

This is the entire management interface while you're away.
Reply to blocked items by editing the .md in tasks/blocked/ from any
device (GitHub mobile app works fine) and moving it back to pending/.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
LOGS = ROOT / "logs"
CONFIG = json.loads((ROOT / "config" / "company.json").read_text(encoding="utf-8"))


def recent(folder: str, hours: int = 24) -> list[Path]:
    cutoff = datetime.now().timestamp() - hours * 3600
    return sorted(
        (f for f in (TASKS / folder).glob("*.md") if f.stat().st_mtime >= cutoff),
        key=lambda p: p.stat().st_mtime,
    )


def today_spend() -> float:
    ledger = LOGS / "spend_ledger.jsonl"
    if not ledger.exists():
        return 0.0
    today = datetime.now().date().isoformat()
    total = 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("date") == today:
                total += float(rec.get("cost_usd", 0.0))
        except (json.JSONDecodeError, ValueError):
            continue
    return total


def heartbeat_ok() -> bool:
    hb = LOGS / "heartbeat"
    if not hb.exists():
        return False
    try:
        last = datetime.fromisoformat(hb.read_text().strip())
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last < timedelta(hours=6)


def title_of(f: Path) -> str:
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("id:"):
            return line[3:].strip()
        if line.startswith("# "):
            return line[2:].strip()
    return f.stem


def build_message() -> str:
    done = recent("done")
    blocked = sorted((TASKS / "blocked").glob("*.md"), key=lambda p: p.stat().st_mtime)
    pending = list((TASKS / "pending").glob("*.md"))

    lines = [f"🏢 afk-company daily report {datetime.now():%m/%d}"]
    lines.append("❤️ systems nominal" if heartbeat_ok() else "🚨 no heartbeat — runner has not run for 6h+")
    lines.append("")

    lines.append(f"✅ done {len(done)}")
    for f in done[:8]:
        lines.append(f"  · {title_of(f)}")

    lines.append(f"🔒 awaiting approval {len(blocked)}" + (" ← action needed" if blocked else ""))
    for f in blocked[:8]:
        lines.append(f"  · {title_of(f)}")

    lines.append(f"📋 queued {len(pending)}")
    lines.append(f"💸 spend today ${today_spend():.2f} / ${CONFIG.get('daily_budget_usd', 10):.0f}")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ.get("AFK_TELEGRAM_TOKEN") or CONFIG.get("telegram_token", "")
    chat_id = os.environ.get("AFK_TELEGRAM_CHAT_ID") or CONFIG.get("telegram_chat_id", "")
    if not token or not chat_id:
        print("telegram not configured — printing report instead:\n")
        print(text)
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


if __name__ == "__main__":
    send_telegram(build_message())
