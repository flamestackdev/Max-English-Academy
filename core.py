"""Общая база данных и бизнес-логика. Используется и сайтом (app.py), и ботом (bot.py)."""
import os
import re
import secrets
import sqlite3
import threading
import time
import datetime as dt
from contextlib import contextmanager

import requests
from werkzeug.security import generate_password_hash, check_password_hash

import config as C
import texts


class Err(Exception):
    def __init__(self, msg, code=400, data=None):
        super().__init__(msg)
        self.msg, self.code, self.data = msg, code, data or {}


# ---------------------------------------------------------------- база данных
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT DEFAULT '',
  pw TEXT NOT NULL, role TEXT DEFAULT 'student', lang TEXT DEFAULT 'ru', currency TEXT DEFAULT 'UZS', tg_id INTEGER UNIQUE,
  blocked INTEGER DEFAULT 0, free_used INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, ts TEXT, ip TEXT DEFAULT '', ua TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS wallets(user_id INTEGER, cur TEXT, amount REAL DEFAULT 0, PRIMARY KEY(user_id,cur));
CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, cur TEXT, delta REAL, bal REAL, reason TEXT, actor TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS prices(plan TEXT, cur TEXT, amount REAL, PRIMARY KEY(plan,cur));
CREATE TABLE IF NOT EXISTS subs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT, starts TEXT, ends TEXT, paid REAL, cur TEXT);
CREATE TABLE IF NOT EXISTS unlocks(user_id INTEGER, lesson_id INTEGER, kind TEXT, ts TEXT, PRIMARY KEY(user_id,lesson_id));
CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, cur TEXT, note TEXT,
  status TEXT DEFAULT 'pending', created TEXT, handled_by TEXT);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, title TEXT, level TEXT, descr TEXT DEFAULT '', position INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER, title TEXT, content_ru TEXT DEFAULT '',
  content_uz TEXT DEFAULT '', video_url TEXT DEFAULT '', zoom_url TEXT DEFAULT '', starts_at TEXT DEFAULT '', recording_url TEXT DEFAULT '',
  homework TEXT DEFAULT '', quiz TEXT DEFAULT '', position INTEGER DEFAULT 0, reminded INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, body TEXT DEFAULT '', ts TEXT);
CREATE TABLE IF NOT EXISTS words(id INTEGER PRIMARY KEY AUTOINCREMENT, en TEXT, ru TEXT, uz TEXT);
CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT, ip TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS linkcodes(code TEXT PRIMARY KEY, user_id INTEGER, exp TEXT);
CREATE TABLE IF NOT EXISTS live(id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id INTEGER, title TEXT, descr TEXT DEFAULT '', course_id INTEGER DEFAULT 0,
  starts_at TEXT, duration INTEGER DEFAULT 60, zoom_url TEXT DEFAULT '', recording_url TEXT DEFAULT '', status TEXT DEFAULT 'scheduled',
  started_at TEXT DEFAULT '', ended_at TEXT DEFAULT '', created TEXT, n15 INTEGER DEFAULT 0, n_start INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS seats(user_id INTEGER, live_id INTEGER, kind TEXT, ts TEXT, PRIMARY KEY(user_id,live_id));
CREATE TABLE IF NOT EXISTS joins(id INTEGER PRIMARY KEY AUTOINCREMENT, live_id INTEGER, user_id INTEGER, ts TEXT);
"""


def db():
    os.makedirs(os.path.dirname(C.DB_PATH), exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, timeout=20, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=20000")
    return con


def q(sql, a=(), one=False):
    con = db()
    try:
        rows = con.execute(sql, a).fetchall()
    finally:
        con.close()
    return (rows[0] if rows else None) if one else rows


def x(sql, a=()):
    con = db()
    try:
        return con.execute(sql, a).lastrowid
    finally:
        con.close()


def xc(sql, a=()):
    """Выполнить и вернуть число изменённых строк (для атомарных «захватов»)."""
    con = db()
    try:
        return con.execute(sql, a).rowcount
    finally:
        con.close()


@contextmanager
def trans():
    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ago(days=0, minutes=0):
    return (dt.datetime.now() - dt.timedelta(days=days, minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def log(actor, action, detail="", ip=""):
    x("INSERT INTO logs(ts,actor,action,detail,ip) VALUES(?,?,?,?,?)", (now(), actor, action, str(detail)[:500], ip))


def setting(k, d=""):
    r = q("SELECT v FROM settings WHERE k=?", (k,), True)
    return r["v"] if r else d


def set_setting(k, v):
    x("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


# ---------------------------------------------------------------- миграция старых баз
MIGRATE = {
    "users": [("full_name", "TEXT DEFAULT ''"), ("theme", "TEXT DEFAULT ''"), ("notify_tg", "INTEGER DEFAULT 1"),
              ("last_login", "TEXT DEFAULT ''"), ("streak", "INTEGER DEFAULT 0"), ("last_active", "TEXT DEFAULT ''")],
    "sessions": [("ip", "TEXT DEFAULT ''"), ("ua", "TEXT DEFAULT ''")],
    "lessons": [("content_en", "TEXT DEFAULT ''"), ("content_qq", "TEXT DEFAULT ''")],
    "words": [("qq", "TEXT DEFAULT ''")],
}


def migrate():
    con = db()
    for table, cols in MIGRATE.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    con.close()


# ---------------------------------------------------------------- пользователи
def create_user(username, password, email="", lang="ru", tg_id=None, role="student"):
    return x(
        "INSERT INTO users(username,email,pw,role,lang,currency,tg_id,created) VALUES(?,?,?,?,?,?,?,?)",
        (username, email, hash_pw(password), role, lang if lang in C.LANGS else "ru", "UZS", tg_id, now()),
    )


def hash_pw(p):
    return generate_password_hash(p, method="pbkdf2:sha256")


def check_login(username, password):
    u = q("SELECT * FROM users WHERE lower(username)=lower(?)", (username.strip(),), True)
    return u if u and check_password_hash(u["pw"], password) else None


def new_session(uid, ip="", ua=""):
    t = secrets.token_hex(24)
    x("INSERT INTO sessions(token,user_id,ts,ip,ua) VALUES(?,?,?,?,?)", (t, uid, now(), ip[:45], short_ua(ua)))
    x("UPDATE users SET last_login=? WHERE id=?", (now(), uid))
    return t


def short_ua(ua):
    ua = ua or ""
    os_ = next((n for k, n in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Mac OS", "macOS"), ("Linux", "Linux")) if k in ua), "")
    br = next((n for k, n in (("Edg", "Edge"), ("OPR", "Opera"), ("Firefox", "Firefox"), ("Chrome", "Chrome"), ("Safari", "Safari")) if k in ua), "")
    return (br + (" · " if br and os_ else "") + os_) or "Unknown"


def free_left(u):
    return max(0, int(setting("free_lessons", "1")) - u["free_used"])


def public_user(uid):
    u = q("SELECT * FROM users WHERE id=?", (uid,), True)
    sb = active_sub(uid)
    prog = q("SELECT (SELECT COUNT(*) FROM lessons) AS total, (SELECT COUNT(DISTINCT lesson_id) FROM results WHERE user_id=?) AS done", (uid,), True)
    streak = u["streak"] if u["last_active"] in (today(), today(-1)) else 0
    return {
        "id": u["id"], "username": u["username"], "email": u["email"], "role": u["role"], "lang": u["lang"],
        "currency": u["currency"], "tg": bool(u["tg_id"]), "free_left": free_left(u), "bal": balances(uid),
        "sub": dict(sb) if sb else None, "bot": C.BOT_USERNAME, "full_name": u["full_name"], "theme": u["theme"],
        "notify_tg": bool(u["notify_tg"]), "created": u["created"], "last_login": u["last_login"], "streak": streak,
        "progress": {"done": prog["done"], "total": prog["total"]},
    }


def today(shift=0):
    return (dt.date.today() + dt.timedelta(days=shift)).isoformat()


def touch(uid):
    """Серия дней подряд: вызывается, когда ученик учится (открыл урок / прошёл тест)."""
    u = q("SELECT streak, last_active FROM users WHERE id=?", (uid,), True)
    if not u or u["last_active"] == today():
        return
    st = (u["streak"] + 1) if u["last_active"] == today(-1) else 1
    x("UPDATE users SET streak=?, last_active=? WHERE id=?", (st, today(), uid))


def user_stats(uid):
    pts = {r["username"]: r["pts"] for r in leaderboard(10 ** 6)}
    me = q("SELECT username FROM users WHERE id=?", (uid,), True)["username"]
    rank = (sum(1 for v in pts.values() if v > pts.get(me, 0)) + 1) if me in pts else None
    r = q("SELECT COUNT(*) AS tests, COUNT(DISTINCT lesson_id) AS lessons FROM results WHERE user_id=?", (uid,), True)
    return {"tests": r["tests"], "lessons": r["lessons"], "points": pts.get(me, 0), "rank": rank,
            "unlocked": q("SELECT COUNT(*) c FROM unlocks WHERE user_id=?", (uid,), True)["c"]}


def sessions(uid, current_token):
    return [{"id": r["id"], "ip": r["ip"], "ua": r["ua"], "ts": r["ts"], "current": r["token"] == current_token}
            for r in q("SELECT rowid AS id, token, ip, ua, ts FROM sessions WHERE user_id=? ORDER BY ts DESC", (uid,))]


def delete_user(uid):
    for t in ("sessions", "wallets", "tx", "subs", "unlocks", "topups", "results", "linkcodes"):
        x(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    x("DELETE FROM users WHERE id=?", (uid,))


def make_code(uid):
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    x("DELETE FROM linkcodes WHERE user_id=? OR exp<?", (uid, now()))
    x("INSERT INTO linkcodes(code,user_id,exp) VALUES(?,?,?)", (code, uid, ago(minutes=-10)))
    return code


def use_code(code, tg_id):
    r = q("SELECT * FROM linkcodes WHERE code=? AND exp>?", (code.strip(), now()), True)
    if not r:
        raise Err("bad_code")
    link_tg(r["user_id"], tg_id)
    x("DELETE FROM linkcodes WHERE code=?", (code.strip(),))
    return r["user_id"]


def link_tg(uid, tg_id):
    """Привязать Telegram к аккаунту сайта; временный аккаунт бота сливается с аккаунтом сайта."""
    with trans() as con:
        old = con.execute("SELECT id, free_used FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if old and old["id"] != uid:
            o = old["id"]
            for r in con.execute("SELECT cur, amount FROM wallets WHERE user_id=?", (o,)).fetchall():
                if r["amount"]:
                    _adj(con, uid, r["cur"], r["amount"], "merge", "system")
            for t in ("unlocks", "subs", "results", "topups", "tx"):
                con.execute(f"UPDATE OR IGNORE {t} SET user_id=? WHERE user_id=?", (uid, o))
            con.execute("UPDATE users SET free_used=MAX(free_used,?) WHERE id=?", (old["free_used"], uid))
            for t in ("unlocks", "wallets", "sessions"):
                con.execute(f"DELETE FROM {t} WHERE user_id=?", (o,))
            con.execute("DELETE FROM users WHERE id=?", (o,))
        con.execute("UPDATE users SET tg_id=? WHERE id=?", (tg_id, uid))


# ---------------------------------------------------------------- деньги
def balances(uid):
    d = {c: 0 for c in C.CURRENCIES}
    for r in q("SELECT cur, amount FROM wallets WHERE user_id=?", (uid,)):
        d[r["cur"]] = r["amount"]
    return d


def _adj(con, uid, cur, delta, reason, actor):
    if cur not in C.CURRENCIES:
        raise Err("bad_currency")
    con.execute("INSERT OR IGNORE INTO wallets(user_id,cur,amount) VALUES(?,?,0)", (uid, cur))
    have = con.execute("SELECT amount FROM wallets WHERE user_id=? AND cur=?", (uid, cur)).fetchone()["amount"]
    new = round(have + delta, 2)
    if new < 0:
        raise Err("insufficient", 402, {"need": round(-delta, 2), "have": have, "cur": cur})
    con.execute("UPDATE wallets SET amount=? WHERE user_id=? AND cur=?", (new, uid, cur))
    con.execute("INSERT INTO tx(user_id,cur,delta,bal,reason,actor,ts) VALUES(?,?,?,?,?,?,?)",
                (uid, cur, delta, new, reason, actor, now()))
    return new


def adjust(uid, cur, delta, reason, actor):
    with trans() as con:
        return _adj(con, uid, cur, delta, reason, actor)


def set_balance(uid, cur, value, reason, actor):
    with trans() as con:
        con.execute("INSERT OR IGNORE INTO wallets(user_id,cur,amount) VALUES(?,?,0)", (uid, cur))
        have = con.execute("SELECT amount FROM wallets WHERE user_id=? AND cur=?", (uid, cur)).fetchone()["amount"]
        return _adj(con, uid, cur, round(value - have, 2), reason, actor)


def prices():
    out = {}
    for r in q("SELECT * FROM prices"):
        out.setdefault(r["plan"], {})[r["cur"]] = r["amount"]
    return out


def price(plan, cur):
    r = q("SELECT amount FROM prices WHERE plan=? AND cur=?", (plan, cur), True)
    if not r:
        raise Err("no_price")
    return r["amount"]


def money(a, cur):
    if cur == "USD":
        return f"${a:,.2f}".replace(".00", "")
    return f"{a:,.0f}".replace(",", " ") + (" ₸" if cur == "KZT" else " UZS")


def plan_name(plan, lang):
    return C.PLAN_NAMES[plan][1 if lang == "uz" else 0]


# ---------------------------------------------------------------- подписки и доступ
def active_sub(uid):
    return q("SELECT * FROM subs WHERE user_id=? AND ends>? ORDER BY ends DESC", (uid, now()), True)


def _add_sub(con, uid, plan, cur, paid):
    last = con.execute("SELECT MAX(ends) e FROM subs WHERE user_id=? AND ends>?", (uid, now())).fetchone()["e"]
    start = dt.datetime.strptime(last, "%Y-%m-%d %H:%M:%S") if last else dt.datetime.now()
    end = (start + dt.timedelta(days=C.PLANS[plan])).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("INSERT INTO subs(user_id,plan,starts,ends,paid,cur) VALUES(?,?,?,?,?,?)",
                (uid, plan, start.strftime("%Y-%m-%d %H:%M:%S"), end, paid, cur))
    return end


def buy_plan(uid, plan, cur):
    if plan not in C.PLANS or plan == "lesson":
        raise Err("bad_plan")
    p = price(plan, cur)
    with trans() as con:
        _adj(con, uid, cur, -p, "sub:" + plan, "user")
        end = _add_sub(con, uid, plan, cur, p)
    return end


def grant_plan(uid, plan, actor):
    with trans() as con:
        return _add_sub(con, uid, plan, "", 0)


def access(uid, lid):
    if active_sub(uid):
        return "sub"
    if q("SELECT 1 FROM unlocks WHERE user_id=? AND lesson_id=?", (uid, lid), True):
        return "owned"
    return ""


def unlock(uid, lid, cur):
    """Открыть урок: подписка -> уже куплен -> бесплатный урок -> оплата с баланса."""
    if not q("SELECT 1 FROM lessons WHERE id=?", (lid,), True):
        raise Err("not_found", 404)
    a = access(uid, lid)
    if a:
        return a
    with trans() as con:
        u = con.execute("SELECT free_used FROM users WHERE id=?", (uid,)).fetchone()
        if u["free_used"] < int(setting("free_lessons", "1")):
            con.execute("UPDATE users SET free_used=free_used+1 WHERE id=?", (uid,))
            kind = "free"
        else:
            _adj(con, uid, cur, -price("lesson", cur), f"lesson:{lid}", "user")
            kind = "paid"
        con.execute("INSERT INTO unlocks(user_id,lesson_id,kind,ts) VALUES(?,?,?,?)", (uid, lid, kind, now()))
    return kind


# ---------------------------------------------------------------- тесты
def pick(row, lang):
    """Текст урока на языке пользователя, иначе на первом доступном."""
    for l in (lang, "ru", "en", "uz", "qq"):
        v = row["content_" + l]
        if v:
            return v
    return ""


def parse_quiz(text):
    """Формат строки: Вопрос | вариант 1 | вариант 2 | вариант 3 | номер верного (с 1)"""
    out = []
    for line in (text or "").splitlines():
        p = [s.strip() for s in line.split("|")]
        if len(p) >= 4 and p[-1].isdigit() and 1 <= int(p[-1]) <= len(p) - 2:
            out.append({"q": p[0], "opts": p[1:-1], "ans": int(p[-1]) - 1})
    return out


def grade(uid, lid, answers):
    l = q("SELECT quiz FROM lessons WHERE id=?", (lid,), True)
    if not l:
        raise Err("not_found", 404)
    qs = parse_quiz(l["quiz"])
    score = sum(1 for i, a in enumerate(qs) if i < len(answers) and answers[i] == a["ans"])
    x("INSERT INTO results(user_id,lesson_id,score,total,ts) VALUES(?,?,?,?,?)", (uid, lid, score, len(qs), now()))
    return score, len(qs), [a["ans"] for a in qs]


def leaderboard(n=20):
    return [dict(r) for r in q(
        "SELECT u.username, SUM(b.best)*10 AS pts FROM (SELECT user_id, MAX(score) best FROM results GROUP BY user_id, lesson_id) b "
        "JOIN users u ON u.id=b.user_id GROUP BY b.user_id HAVING pts>0 ORDER BY pts DESC LIMIT ?", (n,))]


def daily_words(n=10):
    w = q("SELECT * FROM words ORDER BY id")
    if not w:
        return []
    off = (dt.date.today().toordinal() * n) % len(w)
    return [dict(w[(off + i) % len(w)]) for i in range(min(n, len(w)))]


# ---------------------------------------------------------------- Telegram и Zoom
def tg(method, **data):
    if not C.BOT_TOKEN:
        return None
    try:
        return requests.post(f"https://api.telegram.org/bot{C.BOT_TOKEN}/{method}", json=data, timeout=25).json()
    except Exception as e:
        print("telegram error:", e)
        return None


def notify(uid, key, **kw):
    u = q("SELECT tg_id, lang FROM users WHERE id=?", (uid,), True)
    if u and u["tg_id"]:
        tg("sendMessage", chat_id=u["tg_id"], text=texts.m(u["lang"], key, **kw))


def notify_admins(key, **kw):
    done = set()
    for r in q("SELECT tg_id, lang FROM users WHERE role='admin' AND tg_id IS NOT NULL AND notify_tg=1"):
        done.add(r["tg_id"])
        tg("sendMessage", chat_id=r["tg_id"], text=texts.m(r["lang"], key, **kw))
    for i in set(C.ADMIN_TG_IDS) - done:
        tg("sendMessage", chat_id=i, text=texts.m("ru", key, **kw))


def broadcast(text):
    def run():
        for r in q("SELECT tg_id FROM users WHERE tg_id IS NOT NULL AND blocked=0 AND notify_tg=1"):
            tg("sendMessage", chat_id=r["tg_id"], text=text)
            time.sleep(0.06)
    ids = q("SELECT COUNT(*) c FROM users WHERE tg_id IS NOT NULL AND blocked=0 AND notify_tg=1", (), True)["c"]
    if C.BOT_TOKEN:
        threading.Thread(target=run, daemon=True).start()
    return ids if C.BOT_TOKEN else 0


def zoom_create(topic, start, minutes=60):
    """Создаёт встречу Zoom через API (нужны ZOOM_* в .env). start = 'ГГГГ-ММ-ДД ЧЧ:ММ'."""
    if not (C.ZOOM_ACCOUNT_ID and C.ZOOM_CLIENT_ID and C.ZOOM_CLIENT_SECRET):
        raise Err("zoom_not_configured")
    try:
        t = requests.post("https://zoom.us/oauth/token", params={"grant_type": "account_credentials", "account_id": C.ZOOM_ACCOUNT_ID},
                          auth=(C.ZOOM_CLIENT_ID, C.ZOOM_CLIENT_SECRET), timeout=20).json()
        if "access_token" not in t:
            raise Err("zoom_auth", 502)
        r = requests.post("https://api.zoom.us/v2/users/me/meetings", headers={"Authorization": "Bearer " + t["access_token"]},
                          json={"topic": topic, "type": 2, "start_time": start.replace(" ", "T") + ":00", "duration": minutes,
                                "timezone": C.TZ, "settings": {"waiting_room": True}}, timeout=20)
    except requests.RequestException:
        raise Err("zoom_fail", 502)
    if r.status_code >= 300:
        raise Err("zoom_fail", 502, {"detail": r.text[:200]})
    return r.json()["join_url"]


# ---------------------------------------------------------------- онлайн-уроки (Zoom)
ASYNC = True            # уведомления в Telegram отправляются в фоне (в тестах отключается)
LIVE_FIELDS = ("title", "descr", "course_id", "starts_at", "duration", "zoom_url", "recording_url")


def fmt_now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def display_name(uid):
    u = q("SELECT username, full_name FROM users WHERE id=?", (uid,), True)
    return (u["full_name"] or u["username"]) if u else "?"


def live_row(lid):
    r = q("SELECT * FROM live WHERE id=?", (lid,), True)
    if not r:
        raise Err("not_found", 404)
    return r


def can_manage(user, l):
    """Админ управляет всеми онлайн-уроками, учитель — только своими."""
    return user["role"] == "admin" or (user["role"] == "teacher" and l["teacher_id"] == user["id"])


def check_live_fields(d, creating):
    out = {}
    if "title" in d or creating:
        out["title"] = str(d.get("title") or "").strip()[:120]
        if not out["title"]:
            raise Err("bad_title")
    if "descr" in d:
        out["descr"] = str(d.get("descr") or "").strip()[:500]
    if "course_id" in d:
        out["course_id"] = int(d.get("course_id") or 0)
    if "starts_at" in d or creating:
        st = str(d.get("starts_at") or "").strip().replace("T", " ")[:16]
        if not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", st):
            raise Err("bad_date")
        out["starts_at"] = st
    if "duration" in d or creating:
        out["duration"] = max(10, min(300, int(d.get("duration") or 60)))
    for f in ("zoom_url", "recording_url"):
        if f in d:
            v = str(d.get(f) or "").strip()
            if v and not v.startswith(("http://", "https://")):
                raise Err("bad_url")
            out[f] = v
    return out


def live_create(teacher, d):
    if teacher["role"] != "teacher":
        raise Err("only_teacher", 403)
    f = check_live_fields(d, True)
    if f["starts_at"] < ago(minutes=5)[:16]:
        raise Err("past_time")
    soon = f["starts_at"] <= (dt.datetime.now() + dt.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
    f.update(teacher_id=teacher["id"], created=now(), n15=1 if soon else 0)
    lid = x(f"INSERT INTO live({','.join(f)}) VALUES({','.join('?' * len(f))})", tuple(f.values()))
    live_notify(lid, "live_new")
    return lid


def live_update(user, lid, d):
    l = live_row(lid)
    if not can_manage(user, l):
        raise Err("not_owner", 403)
    f = check_live_fields({k: v for k, v in d.items() if k in LIVE_FIELDS}, False)
    moved = "starts_at" in f and f["starts_at"] != l["starts_at"] and l["status"] == "scheduled"
    if f:
        x("UPDATE live SET " + ",".join(f"{k}=?" for k in f) + " WHERE id=?", (*f.values(), lid))
    if moved:
        soon = f["starts_at"] <= (dt.datetime.now() + dt.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
        x("UPDATE live SET n15=?, n_start=0 WHERE id=?", (1 if soon else 0, lid))
        live_notify(lid, "live_moved")
    return lid


def live_action(user, lid, action):
    l = live_row(lid)
    if not can_manage(user, l):
        raise Err("not_owner", 403)
    if action == "start":
        if xc("UPDATE live SET status='live', started_at=?, n_start=1 WHERE id=? AND status='scheduled'", (now(), lid)) != 1:
            raise Err("bad_status")
        live_notify(lid, "live_start")
    elif action == "end":
        if xc("UPDATE live SET status='ended', ended_at=? WHERE id=? AND status='live'", (now(), lid)) != 1:
            raise Err("bad_status")
    elif action == "cancel":
        if xc("UPDATE live SET status='cancelled', ended_at=? WHERE id=? AND status IN ('scheduled','live')", (now(), lid)) != 1:
            raise Err("bad_status")
        live_notify(lid, "live_cancel")
    elif action == "delete":
        for t in ("seats", "joins"):
            x(f"DELETE FROM {t} WHERE live_id=?", (lid,))
        x("DELETE FROM live WHERE id=?", (lid,))
    else:
        raise Err("bad_action")
    return live_row(lid) if action != "delete" else None


def live_access(uid, l):
    u = q("SELECT role FROM users WHERE id=?", (uid,), True)
    if u and u["role"] in ("admin", "teacher"):
        return "staff"
    if active_sub(uid):
        return "sub"
    return "seat" if q("SELECT 1 FROM seats WHERE user_id=? AND live_id=?", (uid, l["id"]), True) else ""


def unlock_live(uid, lid, cur):
    """Занять место на онлайн-уроке: подписка -> уже есть -> бесплатный урок -> оплата с баланса."""
    l = live_row(lid)
    if l["status"] in ("ended", "cancelled"):
        raise Err("bad_status")
    a = live_access(uid, l)
    if a:
        return a
    with trans() as con:
        u = con.execute("SELECT free_used FROM users WHERE id=?", (uid,)).fetchone()
        if u["free_used"] < int(setting("free_lessons", "1")):
            con.execute("UPDATE users SET free_used=free_used+1 WHERE id=?", (uid,))
            kind = "free"
        else:
            _adj(con, uid, cur, -price("lesson", cur), f"live:{lid}", "user")
            kind = "paid"
        con.execute("INSERT INTO seats(user_id,live_id,kind,ts) VALUES(?,?,?,?)", (uid, lid, kind, now()))
    return kind


def live_join(uid, lid):
    l = live_row(lid)
    if l["status"] not in ("scheduled", "live"):
        raise Err("bad_status")
    acc = live_access(uid, l)
    if not acc:
        raise Err("locked", 403)
    if not l["zoom_url"]:
        raise Err("no_link")
    if acc != "staff" and l["status"] == "scheduled" and l["starts_at"] > (dt.datetime.now() + dt.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"):
        raise Err("too_early")
    x("INSERT INTO joins(live_id,user_id,ts) VALUES(?,?,?)", (lid, uid, now()))
    return l["zoom_url"]


def attendees(lid):
    return [dict(r) for r in q("SELECT u.username, u.full_name, MIN(j.ts) AS first, COUNT(*) AS n FROM joins j JOIN users u ON u.id=j.user_id "
                               "WHERE j.live_id=? GROUP BY j.user_id ORDER BY first", (lid,))]


def live_list(user, status=""):
    """Список для панели: админ видит все уроки, учитель — только свои."""
    sql = ("SELECT l.*, u.username, u.full_name, c.title AS course, (SELECT COUNT(DISTINCT user_id) FROM joins WHERE live_id=l.id) AS joined, "
           "(SELECT COUNT(*) FROM seats WHERE live_id=l.id) AS seats FROM live l JOIN users u ON u.id=l.teacher_id LEFT JOIN courses c ON c.id=l.course_id WHERE 1=1")
    a = []
    if user["role"] != "admin":
        sql += " AND l.teacher_id=?"
        a.append(user["id"])
    if status:
        sql += " AND l.status=?"
        a.append(status)
    return [dict(r) for r in q(sql + " ORDER BY CASE l.status WHEN 'live' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END, "
                               "CASE WHEN l.status IN ('live','scheduled') THEN l.starts_at END ASC, l.starts_at DESC LIMIT 200", tuple(a))]


def live_notify(lid, key, sync=None):
    """Рассылка в Telegram всем, кто подключил бота (и не отключил уведомления)."""
    if not C.BOT_TOKEN:
        return
    def run():
        l = live_row(lid)
        tname = display_name(l["teacher_id"])
        for u in q("SELECT id, tg_id, lang FROM users WHERE tg_id IS NOT NULL AND blocked=0 AND notify_tg=1 AND id<>?", (l["teacher_id"],)):
            text = texts.m(u["lang"], key, title=l["title"], teacher=tname, when=l["starts_at"], dur=l["duration"])
            d = {"chat_id": u["tg_id"], "text": text}
            if key != "live_cancel":
                if l["zoom_url"] and live_access(u["id"], l):
                    d["reply_markup"] = {"inline_keyboard": [[{"text": texts.m(u["lang"], "btn_zoom"), "callback_data": f"jn:{lid}"}]]}
                else:
                    d["reply_markup"] = {"inline_keyboard": [[{"text": texts.m(u["lang"], "btn_open"), "callback_data": f"lv:{lid}"}]]}
            tg("sendMessage", **d)
            time.sleep(0.05)
    if ASYNC if sync is None else not sync:
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


def live_tick():
    """Раз в ~30 секунд: напоминание за 15 минут, автостарт в назначенное время, автозавершение.
    Идемпотентно (захват флагов через UPDATE ... WHERE), поэтому безопасно вызывать и из сайта, и из бота."""
    t = fmt_now()
    in15 = (dt.datetime.now() + dt.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
    for r in q("SELECT id FROM live WHERE status='scheduled' AND n15=0 AND starts_at<=? AND starts_at>?", (in15, t)):
        if xc("UPDATE live SET n15=1 WHERE id=? AND n15=0", (r["id"],)) == 1:
            live_notify(r["id"], "live_15", sync=True)
    for r in q("SELECT id FROM live WHERE status='scheduled' AND n_start=0 AND starts_at<=?", (t,)):
        if xc("UPDATE live SET status='live', started_at=?, n_start=1, n15=1 WHERE id=? AND n_start=0 AND status='scheduled'", (now(), r["id"])) == 1:
            live_notify(r["id"], "live_start", sync=True)
    for r in q("SELECT id, started_at, duration FROM live WHERE status='live'"):
        st = dt.datetime.strptime(r["started_at"], "%Y-%m-%d %H:%M:%S")
        if dt.datetime.now() > st + dt.timedelta(minutes=r["duration"] + 30):
            xc("UPDATE live SET status='ended', ended_at=? WHERE id=? AND status='live'", (now(), r["id"]))


def start_scheduler():
    def loop():
        while True:
            try:
                live_tick()
            except Exception as e:
                print("scheduler error:", e)
            time.sleep(30)
    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- начальные данные
WORDS = [  # en, ru, uz, qq
    ("apple", "яблоко", "olma", "alma"), ("book", "книга", "kitob", "kitap"), ("water", "вода", "suv", "suw"), ("house", "дом", "uy", "úy"),
    ("friend", "друг", "do'st", "dos"), ("family", "семья", "oila", "shańaraq"), ("city", "город", "shahar", "qala"), ("work", "работа", "ish", "jumıs"),
    ("study", "учиться", "o'qimoq", "oqıw"), ("happy", "счастливый", "baxtli", "baxıtlı"), ("big", "большой", "katta", "úlken"), ("small", "маленький", "kichik", "kishi"),
    ("fast", "быстрый", "tez", "tez"), ("teacher", "учитель", "o'qituvchi", "muǵallim"), ("student", "ученик", "o'quvchi", "oqıwshı"), ("morning", "утро", "ertalab", "azan"),
    ("night", "ночь", "tun", "tún"), ("food", "еда", "ovqat", "awqat"), ("time", "время", "vaqt", "waqıt"), ("language", "язык", "til", "til")]

DLG = "— Hello! I'm Anna.\n— Hi, Anna! I'm Tom. Nice to meet you."
# (категория, название, уровень, описание, [(урок, {ru, uz, en, qq}, тест, домашка)])
SEED = [
    ("grammar", "Grammar Basics", "A1", "Basic grammar for beginners", [
        ("To be: am / is / are",
         ("Глагол to be: I am, you are, he/she/it is, we/you/they are.\nПример: She is a teacher.", "to be fe'li: I am, you are, he/she/it is, we/you/they are.\nMisol: She is a teacher.",
          "The verb to be: I am, you are, he/she/it is, we/you/they are.\nExample: She is a teacher.", "to be feli: I am, you are, he/she/it is, we/you/they are.\nMısal: She is a teacher."),
         "She ___ a teacher. | am | is | are | 2\nI ___ a student. | am | is | are | 1\nThey ___ friends. | is | am | are | 3", "Write 5 sentences with am / is / are."),
        ("Present Simple",
         ("Present Simple — привычки и факты: I work, He works. Вопрос: Do you work?", "Present Simple — odatlar va faktlar: I work, He works. Savol: Do you work?",
          "Present Simple — habits and facts: I work, He works. Question: Do you work?", "Present Simple — ádetler hám faktler: I work, He works. Sorawı: Do you work?"),
         "He ___ football every day. | play | plays | playing | 2\nDo you ___ English? | speak | speaks | speaking | 1", "Describe your day in 6 sentences."),
        ("Articles: a / an / the",
         ("a — перед согласным звуком (a book), an — перед гласным (an apple), the — конкретный предмет.", "a — undosh tovush oldidan (a book), an — unli tovush oldidan (an apple), the — aniq narsa.",
          "a — before a consonant sound (a book), an — before a vowel sound (an apple), the — a specific thing.", "a — únsiz dawıs aldında (a book), an — dawıslı dawıs aldında (an apple), the — anıq zat."),
         "___ apple | a | an | the | 2\n___ sun is hot. | A | An | The | 3", "")]),
    ("listening", "Listening Basics", "A1", "Audio, exercises, transcripts", [
        ("Introducing yourself", ("Диалог:\n" + DLG, "Dialog:\n" + DLG, "Dialogue:\n" + DLG, "Dialog:\n" + DLG), "Tom says: Nice to ___ you. | meet | see | know | 1", "")]),
    ("reading", "Reading Practice", "A2", "Texts, vocabulary, comprehension", [
        ("A day in London", ("Tom lives in London. He gets up at 7 o'clock and goes to work by bus.",) * 4, "How does Tom go to work? | by bus | by car | on foot | 1", "")]),
    ("speaking", "Speaking Practice", "A1", "Speaking practice, questions, answers", [
        ("Ordering in a café", ("Фразы: Can I have a coffee, please? How much is it?", "Iboralar: Can I have a coffee, please? How much is it?",
                               "Phrases: Can I have a coffee, please? How much is it?", "Sóz dizbekleri: Can I have a coffee, please? How much is it?"),
         "Polite way to ask: | Give me coffee | Can I have a coffee, please? | I want coffee now | 2", "Record yourself ordering a drink.")]),
    ("writing", "Writing Workshop", "B1", "Letters, essays, templates", [
        ("A short email", ("Dear Anna, Thank you for your letter. ... Best regards, Tom",) * 4, "Formal ending: | Best regards | See ya | Bye bye | 1", "Write a short email to a friend.")]),
    ("vocabulary", "Daily Vocabulary", "A1", "Daily words, translations, revision", [
        ("Family and friends", ("mother, father, sister, brother, grandmother, grandfather, friend",) * 4, "Mother's mother is your ___ | aunt | grandmother | sister | 2", "Learn 10 new words.")]),
]

DEFAULT_SETTINGS = {
    "free_lessons": "1", "support": "@max_english_support",
    "pay_info": "Переведите сумму на карту 0000 0000 0000 0000 (Max English Academy), затем отправьте заявку на пополнение. / Transfer the amount to card 0000 0000 0000 0000 (Max English Academy), then send a top-up request.",
    "social_instagram": "https://instagram.com/", "social_telegram": "https://t.me/", "social_youtube": "https://youtube.com/",
    "social_facebook": "https://facebook.com/", "social_tiktok": "https://tiktok.com/",
    "contact_phone": "+998 90 000 00 00", "contact_address": "Tashkent, Uzbekistan",
}
PUBLIC_KEYS = ("social_instagram", "social_telegram", "social_youtube", "social_facebook", "social_tiktok", "contact_phone", "contact_address", "support")


def public_info():
    st = {k: setting(k) for k in PUBLIC_KEYS}
    st["stats"] = {"students": q("SELECT COUNT(*) c FROM users WHERE role='student'", (), True)["c"], "lessons": q("SELECT COUNT(*) c FROM lessons", (), True)["c"],
                   "courses": q("SELECT COUNT(*) c FROM courses", (), True)["c"], "teachers": q("SELECT COUNT(*) c FROM users WHERE role='teacher'", (), True)["c"]}
    return st


def migrate_old_zoom():
    """Старые уроки с полями zoom_url/starts_at превращаются в онлайн-уроки (владелец — первый админ)."""
    if q("SELECT 1 FROM live LIMIT 1", (), True):
        return
    adm = q("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1", (), True)
    for l in q("SELECT * FROM lessons WHERE zoom_url<>'' AND starts_at<>''"):
        st = "ended" if l["starts_at"] < fmt_now() else "scheduled"
        x("INSERT INTO live(teacher_id,title,course_id,starts_at,zoom_url,recording_url,status,created,n15,n_start) VALUES(?,?,?,?,?,?,?,?,1,1)",
          (adm["id"], l["title"], l["course_id"], l["starts_at"], l["zoom_url"], l["recording_url"], st, now()))


def init():
    con = db()
    con.executescript(SCHEMA)
    con.close()
    migrate()
    if not q("SELECT 1 FROM users WHERE username=?", (C.ADMIN_USER,), True):
        create_user(C.ADMIN_USER, C.ADMIN_PASS, "admin@local", role="admin")
    for plan, d in C.DEFAULT_PRICES.items():
        for cur, amt in d.items():
            x("INSERT OR IGNORE INTO prices(plan,cur,amount) VALUES(?,?,?)", (plan, cur, amt))
    for k, v in DEFAULT_SETTINGS.items():
        x("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k, v))
    if not q("SELECT 1 FROM courses LIMIT 1", (), True):
        for i, (cat, title, level, descr, lessons) in enumerate(SEED):
            cid = x("INSERT INTO courses(cat,title,level,descr,position) VALUES(?,?,?,?,?)", (cat, title, level, descr, i))
            for j, (lt, c4, quiz, hw) in enumerate(lessons):
                x("INSERT INTO lessons(course_id,title,content_ru,content_uz,content_en,content_qq,quiz,homework,position) VALUES(?,?,?,?,?,?,?,?,?)", (cid, lt, *c4, quiz, hw, j))
        x("INSERT INTO announcements(title,body,ts) VALUES(?,?,?)", ("Добро пожаловать! / Welcome! / Xush kelibsiz!", "Первый урок бесплатный. / The first lesson is free. / Birinchi dars bepul.", now()))
    if not q("SELECT 1 FROM words LIMIT 1", (), True):
        for w in WORDS:
            x("INSERT INTO words(en,ru,uz,qq) VALUES(?,?,?,?)", w)
    x("UPDATE words SET qq=en WHERE qq IS NULL OR qq=''")
    migrate_old_zoom()
