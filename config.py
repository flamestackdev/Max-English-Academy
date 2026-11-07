"""Настройки проекта. Значения берутся из файла .env (см. .env.example)."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    p = os.path.join(BASE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def env(k, d=""):
    return os.environ.get(k, d)


ACADEMY = "Max English Academy"
DB_PATH = env("DB_PATH", os.path.join(BASE, "data", "academy.db"))
HOST = env("HOST", "0.0.0.0")
PORT = int(env("PORT", "8000"))

SITE_URL = env("SITE_URL", "")  # например http://192.168.1.5:8000 — показывается в боте
ADMIN_USER = env("ADMIN_USER", "admin")
ADMIN_PASS = env("ADMIN_PASS", "admin12345")

BOT_TOKEN = env("BOT_TOKEN")
BOT_USERNAME = env("BOT_USERNAME").lstrip("@")
ADMIN_TG_IDS = [int(x) for x in env("ADMIN_TG_IDS").split(",") if x.strip().isdigit()]

# Zoom Server-to-Server OAuth (необязательно: можно просто вставлять ссылки на Zoom вручную)
ZOOM_ACCOUNT_ID = env("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = env("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = env("ZOOM_CLIENT_SECRET")
TZ = env("TZ_NAME", "Asia/Tashkent")

LANGS = ("ru", "uz", "en", "qq")   # русский, узбекский, английский, каракалпакский
LANG_NAMES = {"ru": "Русский", "uz": "O'zbekcha", "en": "English", "qq": "Qaraqalpaqsha"}
ROLES = ("student", "teacher", "admin")
CURRENCIES = ["UZS", "USD", "KZT"]
# тариф -> количество дней (lesson = разовая покупка урока)
PLANS = {"lesson": 0, "m1": 30, "m3": 90, "m6": 180, "y1": 365}
PLAN_NAMES = {  # ru, uz, en, qq
    "lesson": ("1 урок", "1 dars", "1 lesson", "1 sabaq"),
    "m1": ("1 месяц", "1 oy", "1 month", "1 ay"),
    "m3": ("3 месяца", "3 oy", "3 months", "3 ay"),
    "m6": ("6 месяцев", "6 oy", "6 months", "6 ay"),
    "y1": ("1 год", "1 yil", "1 year", "1 jıl"),
}
DEFAULT_PRICES = {
    "lesson": {"UZS": 50000, "USD": 4, "KZT": 2000},
    "m1": {"UZS": 199000, "USD": 16, "KZT": 7900},
    "m3": {"UZS": 499000, "USD": 40, "KZT": 19900},
    "m6": {"UZS": 899000, "USD": 72, "KZT": 35900},
    "y1": {"UZS": 1590000, "USD": 125, "KZT": 62900},
}
