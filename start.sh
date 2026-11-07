#!/usr/bin/env bash
# Запуск сайта и бота в фоне (Termux). Логи: logs/web.log и logs/bot.log
cd "$(dirname "$0")"
mkdir -p data logs
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
[ -f .env ] || cp .env.example .env
./stop.sh >/dev/null 2>&1
nohup python app.py >> logs/web.log 2>&1 &
echo $! > data/web.pid
if grep -qE '^BOT_TOKEN=.+' .env; then
  nohup python bot.py >> logs/bot.log 2>&1 &
  echo $! > data/bot.pid
  echo "Бот запущен"
else
  echo "BOT_TOKEN не указан в .env — запущен только сайт"
fi
echo "Сайт: http://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 | head -1 | grep . || echo 8000)   Админка: /admin"
