#!/usr/bin/env bash
cd "$(dirname "$0")"
for f in data/web.pid data/bot.pid; do
  [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null && rm -f "$f"
done
echo "Остановлено"
