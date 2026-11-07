# Max English Academy — сайт + Telegram-бот + общая база (SQLite)

Файлы: `app.py` (сайт и API), `bot.py` (бот), `core.py` (общая логика и база), `texts.py` (тексты бота на 4 языках), `config.py`, `static/` (интерфейс).

## Возможности
- Главная страница с анимацией (печать текста при свайпе, карточки курсов, вход/регистрация, соцсети)
- 4 языка: Русский, English, O'zbek, Qaraqalpaq — сайт, админ-панель и бот (`static/i18n.js`, `texts.py`)
- 3 роли: Ученик (по умолчанию), Учитель, Админ
- Онлайн-уроки Zoom: создаёт учитель, управляют учитель (свои) и админ (все); уведомления в Telegram
- Курсы, тесты, подписки (1/3/6/12 мес.), валюты UZS/USD/KZT, первый урок бесплатно
- Личный кабинет, светлая/тёмная тема, админ-панель, логи, рассылка, CSV, резервная копия

## Запуск в Termux
```bash
pkg update -y && pkg install -y python
pip install flask requests
cp .env.example .env && nano .env     # пароль админа, BOT_TOKEN
chmod +x start.sh stop.sh && ./start.sh
```
Сайт: http://localhost:8000 · Админка: http://localhost:8000/admin · Логи: `logs/web.log`, `logs/bot.log` · Остановка: `./stop.sh`

## Обновление с прошлой версии
`./stop.sh`, сделайте копию папки, замените файлы (папку `data/` и `.env` не трогайте), затем `./start.sh`. База обновится сама.
