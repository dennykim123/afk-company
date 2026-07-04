#!/bin/bash
# afk-company one-command onboarding (macOS)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$ROOT/logs"
CFG="$ROOT/config/company.json"
[ -f "$CFG" ] || cp "$ROOT/config/company.example.json" "$CFG"

echo "🏢 Installing afk-company — $ROOT"
echo ""

# 0. behavior tests first — never install something broken
./verify.sh >/dev/null 2>&1 && echo "✅ behavior tests passed" || { echo "❌ verify.sh failed — aborting install"; exit 1; }

# 1. claude CLI probe (auth + json shape, parser is field-name tolerant)
if command -v claude >/dev/null; then
  if claude -p "reply with exactly: DONE: pong" --max-turns 1 --output-format json 2>/dev/null | grep -q pong; then
    echo "✅ claude CLI authenticated"
  else
    echo "⚠️  claude CLI found but not responding — run 'claude' once to log in"
  fi
else
  echo "❌ claude CLI missing: npm i -g @anthropic-ai/claude-code"
fi

# 2. telegram: token prompt + pairing code (chat_id is set by messaging the code to the bot)
TOKEN=$(python3 -c "import json;print(json.load(open('$CFG')).get('telegram_token',''))")
if [ -z "$TOKEN" ]; then
  read -rp "🤖 Telegram bot token (@BotFather /newbot, Enter to skip): " TOKEN || true
  if [ -n "${TOKEN:-}" ]; then
    python3 - << PYEOF
import json; p="$CFG"; c=json.load(open(p)); c["telegram_token"]="$TOKEN"
json.dump(c, open(p,"w"), indent=2, ensure_ascii=False)
PYEOF
  fi
fi
if [ -n "${TOKEN:-}" ]; then
  CODE=$(python3 -c "import random;print(random.randint(100000,999999))")
  echo "$CODE" > "$ROOT/logs/pairing_code"
  echo "✅ Telegram ready — send this code to your bot to pair:"
  echo ""
  echo "        🔑 Pairing code: $CODE"
  echo ""
fi

# 3. launchd registration
for name in runner report telegram; do
  src="$ROOT/config/com.afkcompany.$name.plist"
  dst="$AGENTS/com.afkcompany.$name.plist"
  sed "s|__AFK_ROOT__|$ROOT|g" "$src" > "$dst"
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
done
echo "✅ launchd loaded (runner every 30min · report daily 08:00 · telegram always-on)"

# 4. keep-awake (if the machine sleeps, so does the company)
if pmset -g 2>/dev/null | grep -qE "^\s*sleep\s+0"; then
  echo "✅ sleep disabled"
else
  echo "⚠️  If the Mac sleeps, the company stops: sudo pmset -a sleep 0"
fi

# 5. git (audit log + sync channel)
chmod +x "$ROOT"/bin/*.py
if [ ! -d "$ROOT/.git" ]; then
  git init -q "$ROOT" && echo "✅ git initialized (recommended: gh repo create my-afk-ops --private --source=. --push)"
fi

echo ""
echo "── Remaining: send the pairing code to your bot → then just type your first task ──"
python3 "$ROOT/bin/doctor.py" || true
