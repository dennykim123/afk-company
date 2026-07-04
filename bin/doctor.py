#!/usr/bin/env python3
"""
afk-company doctor
──────────────────
Run this before you leave, and any time something feels off.
Every check maps to a real way the company dies while you're gone.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK, BAD, WARN = "✅", "❌", "⚠️ "
failures = 0


def check(label: str, ok: bool, hint: str = "", warn_only: bool = False) -> None:
    global failures
    mark = OK if ok else (WARN if warn_only else BAD)
    print(f"{mark} {label}" + ("" if ok else f"  → {hint}"))
    if not ok and not warn_only:
        failures += 1


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


def main() -> int:
    print("afk-company doctor\n" + "─" * 40)

    # config
    cfg_path = ROOT / "config" / "company.json"
    cfg = {}
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        check("config/company.json parses", True)
    except Exception as e:
        check("config/company.json parses", False, str(e))

    # claude CLI — the single most common point of failure
    claude_bin = cfg.get("claude_bin", "claude")
    found = shutil.which(claude_bin) is not None
    check(f"claude CLI ({claude_bin})", found, "npm i -g @anthropic-ai/claude-code, then run `claude` once to log in")
    if found:
        r = sh([claude_bin, "-p", "reply with exactly: pong", "--max-turns", "1"])
        check("claude headless response (auth alive)", "pong" in r.stdout.lower(),
              "auth may have expired — re-login via interactive `claude`")

    # git — the audit log and the sync channel
    check("git repo", (ROOT / ".git").exists(), "git init && add a remote")
    r = sh(["git", "remote", "-v"])
    check("git remote (origin)", "origin" in r.stdout, "connect a private GitHub repo")
    r = sh(["git", "push", "--dry-run"])
    check("git push access", r.returncode == 0, "check SSH key/token — use one that won't expire while you're away")

    # telegram
    has_tg = bool(cfg.get("telegram_token") and cfg.get("telegram_chat_id"))
    check("Telegram configured", has_tg, "without a bot there are no reports while you're away", warn_only=True)

    # launchd
    r = sh(["launchctl", "list"])
    loaded = "com.afkcompany" in r.stdout
    check("launchd loaded", loaded, "run install.sh or launchctl load", warn_only=not loaded)

    # heartbeat freshness
    hb = ROOT / "logs" / "heartbeat"
    fresh = False
    if hb.exists():
        try:
            last = datetime.fromisoformat(hb.read_text().strip())
            fresh = datetime.now(timezone.utc) - last < timedelta(hours=6)
        except ValueError:
            pass
    check("heartbeat within 6h", fresh, "runner has not run yet, or has stopped", warn_only=True)

    # disk
    du = shutil.disk_usage(str(ROOT))
    check("disk free 10GB+", du.free > 10 * 2**30, f"{du.free / 2**30:.1f}GB left", warn_only=True)

    # power (mac): company dies if the machine sleeps
    r = sh(["pmset", "-g"])
    if r.returncode == 0:
        check("sleep disabled (sleep 0)", " sleep                0" in r.stdout or "sleep\t0" in r.stdout,
              "sudo pmset -a sleep 0 — if the machine sleeps, so does the company", warn_only=True)

    print("─" * 40)
    if failures == 0:
        print("You are clear to leave. ✈️")
    else:
        print(f"{failures} item(s) could kill the company. Fix them before you go.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
