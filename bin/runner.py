#!/usr/bin/env python3
"""
afk-company runner
──────────────────
The heartbeat of the company. Called by launchd on a schedule.

One invocation = one task:
  1. Pick the oldest eligible task from tasks/pending/
  2. Move it to tasks/running/ (crash-safe: stale running tasks are recovered)
  3. Execute it headless via `claude -p` with a whitelist of allowed tools
  4. Route the result:
       - last line starts with "BLOCKED:"  -> tasks/blocked/  (needs human approval)
       - exit code != 0 or budget exceeded -> tasks/blocked/  (needs human eyes)
       - otherwise                         -> tasks/done/
  5. git commit + push everything (the repo IS the audit log)

Design principles (absence-first):
  - Every run is bounded: max turns, per-task timeout, daily spend ceiling.
  - The runner never invents work. No task file, no execution.
  - Anything ambiguous stops and asks. Blocked is a feature, not a failure.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
LOGS = ROOT / "logs"
CONFIG = json.loads((ROOT / "config" / "company.json").read_text(encoding="utf-8"))

HEARTBEAT = LOGS / "heartbeat"
SPEND_LEDGER = LOGS / "spend_ledger.jsonl"  # one JSON line per run
STALE_RUNNING_MIN = CONFIG.get("stale_running_minutes", 180)


# ── helpers ──────────────────────────────────────────────────────────

def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOGS / "runner.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd: list[str], timeout: int | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML-ish frontmatter parser: `key: value` lines between --- fences."""
    meta: dict = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"')
        body = m.group(2)
    return meta, body


def extract_first_float(payload: dict, dotted_keys: list[str]) -> float:
    """CLI versions rename fields; try every known spelling, incl. nested a.b paths."""
    for key in dotted_keys:
        node = payload
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if node is not None:
            try:
                return float(node)
            except (TypeError, ValueError):
                continue
    return 0.0


def today_spend_usd() -> float:
    """Sum today's recorded spend from the ledger."""
    if not SPEND_LEDGER.exists():
        return 0.0
    today = datetime.now().date().isoformat()
    total = 0.0
    for line in SPEND_LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("date") == today:
                total += float(rec.get("cost_usd", 0.0))
        except (json.JSONDecodeError, ValueError):
            continue
    return total


def record_spend(task_id: str, cost_usd: float, turns: int) -> None:
    rec = {
        "date": datetime.now().date().isoformat(),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "task": task_id,
        "cost_usd": round(cost_usd, 4),
        "turns": turns,
    }
    with open(SPEND_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def notify_blocked(task_id: str, dest_name: str, reason: str,
                   task_gist: str = "", output_preview: str = "") -> None:
    """HITL best practice: an approval request must carry enough context to decide.
    Card = what the task was / why it stopped / what it produced so far.
    Replying to this message (in telegram_bridge) injects your feedback and re-runs."""
    token = CONFIG.get("telegram_token", "")
    chat_id = CONFIG.get("telegram_chat_id", "")
    if not token or not chat_id:
        return
    import urllib.parse
    import urllib.request
    stem = dest_name.rsplit(".md", 1)[0]
    parts = [f"🔒 Approval needed: {task_id}"]
    if task_gist:
        parts.append(f"📋 Task: {task_gist[:150]}")
    parts.append(f"⛔ Blocked because: {reason}")
    if output_preview:
        parts.append(f"📄 Output preview:\n{output_preview[:600]}")
    parts.append("↩️ Reply to this message and your reply becomes a directive for the re-run.")
    payload = {
        "chat_id": chat_id,
        "text": "\n\n".join(parts)[:4000],
        "reply_markup": json.dumps({"inline_keyboard": [[
            {"text": "✅ Re-run as is", "callback_data": f"approve:{stem}"},
            {"text": "❌ Reject", "callback_data": f"reject:{stem}"},
        ]]}),
    }
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode(payload).encode(),
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001 — notification failure must not kill the run
        log(f"blocked-notify failed: {e}")


def git_commit_push(message: str) -> None:
    sh(["git", "add", "-A"])
    r = sh(["git", "commit", "-m", message])
    if r.returncode == 0:
        log(f"committed: {message}")
    push = sh(["git", "push"], timeout=120)
    if push.returncode != 0:
        # Offline is fine — next run will push. Absence-first means tolerate flaky networks.
        log(f"push failed (will retry next run): {push.stderr.strip()[:200]}")


def recover_stale_running() -> None:
    """If a previous run crashed mid-task, move its task back to pending."""
    cutoff = time.time() - STALE_RUNNING_MIN * 60
    for f in (TASKS / "running").glob("*.md"):
        if f.stat().st_mtime < cutoff:
            log(f"recovering stale running task: {f.name}")
            shutil.move(str(f), TASKS / "pending" / f.name)


def is_due(meta: dict, task_file: Path) -> bool:
    """schedule: once | daily | weekly  — daily/weekly tasks are cloned into done/,
    so the pending copy stays; we check the last done timestamp of the same id."""
    schedule = meta.get("schedule", "once")
    if schedule == "once":
        return True
    task_id = meta.get("id", task_file.stem)
    stamps = sorted((TASKS / "done").glob(f"{task_id}__*.md"))
    if not stamps:
        return True
    last = datetime.fromtimestamp(stamps[-1].stat().st_mtime)
    gap = {"daily": timedelta(hours=20), "weekly": timedelta(days=6, hours=12)}.get(schedule)
    return gap is not None and datetime.now() - last >= gap


def pick_task() -> Path | None:
    candidates = sorted((TASKS / "pending").glob("*.md"), key=lambda p: p.stat().st_mtime)
    for f in candidates:
        if f.name.lower() == "readme.md":
            continue
        meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        if "id" not in meta:
            continue  # not a task file (no contract, no work)
        if int(meta.get("tier", 1)) != 1:
            continue  # only Tier 1 runs unattended; Tier 2 drafts also use tier: 1 mechanics with draft-only prompts
        if is_due(meta, f):
            return f
    return None


# ── main ─────────────────────────────────────────────────────────────

def main() -> int:
    HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())
    recover_stale_running()

    # 1. budget gate
    ceiling = float(CONFIG.get("daily_budget_usd", 10.0))
    spent = today_spend_usd()
    if spent >= ceiling:
        log(f"daily budget reached (${spent:.2f} / ${ceiling:.2f}) — company is resting")
        return 0

    # 2. pick work
    task_file = pick_task()
    if task_file is None:
        log("no eligible pending tasks — idle")
        return 0

    meta, body = parse_frontmatter(task_file.read_text(encoding="utf-8"))
    task_id = meta.get("id", task_file.stem)
    schedule = meta.get("schedule", "once")
    max_turns = str(meta.get("max_turns", CONFIG.get("default_max_turns", 25)))
    timeout_s = int(meta.get("timeout_minutes", CONFIG.get("default_timeout_minutes", 45))) * 60
    allowed = meta.get("allowed_tools", CONFIG.get("default_allowed_tools", "Read,Grep,Glob"))

    # 3. move to running (recurring tasks stay in pending; we work on a copy)
    if schedule == "once":
        running = TASKS / "running" / task_file.name
        shutil.move(str(task_file), running)
    else:
        running = TASKS / "running" / task_file.name
        shutil.copy2(str(task_file), running)
    git_commit_push(f"run start: {task_id}")

    # 4. execute headless
    prompt = (
        f"{body.strip()}\n\n"
        "-- afk-company execution protocol --\n"
        "1. Do only the job above. Never touch files outside its scope.\n"
        "2. If human judgment is needed or the done condition cannot be met, stop\n"
        "   trying alternatives and print exactly `BLOCKED: <one-line reason>` as the last line.\n"
        "3. On success, print `DONE: <one-line summary>` as the last line.\n"
        "4. Never take actions that spend money or send anything to the outside world.\n"
    )
    cmd = [
        CONFIG.get("claude_bin", "claude"),
        "-p", prompt,
        "--max-turns", max_turns,
        "--allowedTools", allowed,
        "--output-format", "json",
    ]
    workdir = Path(os.path.expanduser(meta.get("workdir", str(ROOT)))).resolve()
    log(f"executing {task_id} (tools={allowed}, max_turns={max_turns}, cwd={workdir})")

    verdict, summary, cost, turns = "blocked", "unknown failure", 0.0, 0
    raw_out = ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, cwd=workdir)
        raw_out = r.stdout
        try:
            payload = json.loads(r.stdout)
            result_text = payload.get("result", "")
            cost = extract_first_float(payload, ["total_cost_usd", "cost_usd", "total_cost",
                                                  "usage.cost_usd", "usage.total_cost_usd"])
            turns = int(extract_first_float(payload, ["num_turns", "turns", "usage.num_turns"]))
        except json.JSONDecodeError:
            result_text = r.stdout
        last_line = result_text.strip().splitlines()[-1] if result_text.strip() else ""
        if r.returncode == 0 and last_line.startswith("DONE:"):
            verdict, summary = "done", last_line[5:].strip()
        elif last_line.startswith("BLOCKED:"):
            verdict, summary = "blocked", last_line[8:].strip()
        else:
            verdict, summary = "blocked", f"no verdict marker (exit {r.returncode})"
        (LOGS / f"{task_id}__{datetime.now():%Y%m%d_%H%M%S}.out.txt").write_text(
            result_text or raw_out, encoding="utf-8")
    except subprocess.TimeoutExpired:
        summary = f"timeout after {timeout_s // 60}min"
    except FileNotFoundError:
        summary = "claude CLI not found — run doctor.py"

    record_spend(task_id, cost, turns)

    # 5. route result
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    note = f"\n\n---\n**{verdict.upper()}** ({stamp}): {summary}\n(cost: ${cost:.4f}, turns: {turns})\n"
    running.write_text(running.read_text(encoding="utf-8") + note, encoding="utf-8")
    dest_dir = TASKS / ("done" if verdict == "done" else "blocked")
    dest = dest_dir / f"{task_id}__{stamp}.md"
    shutil.move(str(running), dest)
    if verdict == "blocked":
        # task gist = first heading or first body line of the contract
        gist = next((ln.lstrip("# ").strip() for ln in body.splitlines()
                     if ln.strip() and not ln.startswith("---")), "")
        preview = ""
        try:
            outs = sorted(LOGS.glob(f"{task_id}__*.out.txt"))
            if outs:
                raw = outs[-1].read_text(encoding="utf-8").strip()
                # drop the verdict line itself; show what came before it
                lines = [l for l in raw.splitlines() if not l.startswith(("BLOCKED:", "DONE:"))]
                preview = "\n".join(lines)[-600:]
        except OSError:
            pass
        notify_blocked(task_id, dest.name, summary, task_gist=gist, output_preview=preview)

    log(f"{task_id} -> {verdict}: {summary} (${cost:.4f})")
    git_commit_push(f"{verdict}: {task_id} — {summary[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
