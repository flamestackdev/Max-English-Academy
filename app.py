"""Сайт + API. Запуск: python app.py"""
import csv
import io
import os
import re
import sqlite3
import tempfile
import time
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, send_file, g, Response
from werkzeug.security import check_password_hash

import config as C
import core
from core import q, x, Err, log

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.sort_keys = False
STATIC = os.path.join(C.BASE, "static")


def J(data=None, _status=200, **kw):
    return jsonify(data if data is not None else kw), _status


def ip():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:45]


def body():
    return request.get_json(force=True, silent=True) or {}


@app.errorhandler(Err)
def on_err(e):
    return jsonify(error=e.msg, **e.data), e.code


@app.errorhandler(404)
def on_404(e):
    return (jsonify(error="not_found"), 404) if request.path.startswith("/api/") else ("Not found", 404)


@app.errorhandler(Exception)
def on_exc(e):
    if hasattr(e, "code") and isinstance(e.code, int):
        return jsonify(error="http_%s" % e.code), e.code
    log("system", "error", repr(e), ip())
    return jsonify(error="server"), 500


def auth(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            h = request.headers.get("Authorization", "")
            tok = h[7:] if h.startswith("Bearer ") else ""
            u = q("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND sessions.ts>?",
                  (tok, core.ago(30)), True) if tok else None
            if not u:
                raise Err("auth", 401)
            if u["blocked"]:
                raise Err("blocked", 403)
            if role == "admin" and u["role"] != "admin":
                raise Err("forbidden", 403)
            if role == "staff" and u["role"] not in ("admin", "teacher"):
                raise Err("forbidden", 403)
            g.u, g.tok = u, tok
            return f(*a, **k)
        return w
    return deco


# ---------------------------------------------------------------- страницы
@app.get("/")
def p_index():
    return send_from_directory(STATIC, "landing.html")


@app.get("/login")
def p_login():
    return send_from_directory(STATIC, "login.html")


@app.get("/app")
def p_app():
    return send_from_directory(STATIC, "app.html")


@app.get("/admin")
def p_admin():
    return send_from_directory(STATIC, "admin.html")


@app.get("/api/public")
def public():
    return J(core.public_info())


# ---------------------------------------------------------------- регистрация и вход
FAILS = {}


def too_many(key):
    t = time.time()
    FAILS[key] = [a for a in FAILS.get(key, []) if t - a < 600]
    return len(FAILS[key]) >= 8


def check_username(u, exclude=0):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,24}", u):
        raise Err("bad_username")
    if q("SELECT 1 FROM users WHERE lower(username)=lower(?) AND id<>?", (u, exclude), True):
        raise Err("username_taken", 409)


def check_email(e, exclude=0):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) or len(e) > 100:
        raise Err("bad_email")
    if q("SELECT 1 FROM users WHERE lower(email)=lower(?) AND id<>?", (e, exclude), True):
        raise Err("email_taken", 409)


def ua():
    return request.headers.get("User-Agent", "")


@app.post("/api/register")
def register():
    d = body()
    u, e, p = (d.get("username") or "").strip(), (d.get("email") or "").strip(), d.get("password") or ""
    check_username(u)
    check_email(e)
    if len(p) < 6 or len(p) > 100:
        raise Err("short_password")
    uid = core.create_user(u, p, e, lang=d.get("lang", "ru"))
    log(u, "register", e, ip())
    return J(token=core.new_session(uid, ip(), ua()), user=core.public_user(uid))


@app.post("/api/login")
def login():
    d = body()
    name = (d.get("username") or "").strip()
    key = ip() + "|" + name.lower()
    if too_many(key):
        raise Err("too_many", 429)
    u = core.check_login(name, d.get("password") or "")
    if not u:
        FAILS.setdefault(key, []).append(time.time())
        log(name, "login_failed", "", ip())
        raise Err("bad_creds", 401)
    if u["blocked"]:
        raise Err("blocked", 403)
    log(u["username"], "login", "", ip())
    return J(token=core.new_session(u["id"], ip(), ua()), user=core.public_user(u["id"]))


@app.post("/api/logout")
@auth()
def logout():
    tok = request.headers.get("Authorization", "")[7:]
    x("DELETE FROM sessions WHERE token=?", (tok,))
    return J(ok=True)


@app.get("/api/me")
@auth()
def me():
    return J(core.public_user(g.u["id"]))


@app.patch("/api/me")
@auth()
def me_patch():
    d = body()
    if d.get("lang") in C.LANGS:
        x("UPDATE users SET lang=? WHERE id=?", (d["lang"], g.u["id"]))
    if d.get("currency") in C.CURRENCIES:
        x("UPDATE users SET currency=? WHERE id=?", (d["currency"], g.u["id"]))
    if d.get("theme") in ("light", "dark"):
        x("UPDATE users SET theme=? WHERE id=?", (d["theme"], g.u["id"]))
    if "notify_tg" in d:
        x("UPDATE users SET notify_tg=? WHERE id=?", (1 if d["notify_tg"] else 0, g.u["id"]))
    return J(core.public_user(g.u["id"]))


@app.get("/api/profile")
@auth()
def profile():
    uid = g.u["id"]
    return J(user=core.public_user(uid), stats=core.user_stats(uid), sessions=core.sessions(uid, g.tok))


def need_password(pw):
    """Проверка текущего пароля с защитой от подбора (8 ошибок за 10 минут)."""
    key = "pw|%s" % g.u["id"]
    if too_many(key):
        raise Err("too_many", 429)
    if not check_password_hash(g.u["pw"], pw or ""):
        FAILS.setdefault(key, []).append(time.time())
        log(g.u["username"], "wrong_current_password", "", ip())
        raise Err("wrong_password", 403)


@app.post("/api/me/account")
@auth()
def me_account():
    d, u = body(), g.u
    name = (d.get("username") or u["username"]).strip()
    email = (d.get("email") if "email" in d else u["email"]) or ""
    email = email.strip()
    full = str(d.get("full_name", u["full_name"]) or "").strip()[:60]
    if name != u["username"] or email != (u["email"] or ""):
        need_password(d.get("current_password"))
        if name != u["username"]:
            check_username(name, u["id"])
        if email != (u["email"] or ""):
            check_email(email, u["id"])
    x("UPDATE users SET username=?, email=?, full_name=? WHERE id=?", (name, email, full, u["id"]))
    changed = [k for k, a, b in (("username", name, u["username"]), ("email", email, u["email"]), ("full_name", full, u["full_name"])) if a != b]
    if changed:
        log(name, "profile_update", f"{', '.join(changed)} (was {u['username']})", ip())
    return J(core.public_user(u["id"]))


@app.post("/api/me/password")
@auth()
def me_password():
    d = body()
    need_password(d.get("current"))
    new = d.get("new") or ""
    if len(new) < 6 or len(new) > 100:
        raise Err("short_password")
    if new == d.get("current"):
        raise Err("same_password")
    x("UPDATE users SET pw=? WHERE id=?", (core.hash_pw(new), g.u["id"]))
    x("DELETE FROM sessions WHERE user_id=? AND token<>?", (g.u["id"], g.tok))
    log(g.u["username"], "password_changed", "other sessions closed", ip())
    return J(ok=True)


@app.post("/api/me/sessions/revoke")
@auth()
def me_revoke():
    sid = body().get("id")
    if sid == "others":
        x("DELETE FROM sessions WHERE user_id=? AND token<>?", (g.u["id"], g.tok))
    else:
        x("DELETE FROM sessions WHERE rowid=? AND user_id=? AND token<>?", (int(sid or 0), g.u["id"], g.tok))
    log(g.u["username"], "session_revoked", str(sid), ip())
    return J(sessions=core.sessions(g.u["id"], g.tok))


@app.post("/api/me/unlink_tg")
@auth()
def me_unlink():
    x("UPDATE users SET tg_id=NULL WHERE id=?", (g.u["id"],))
    log(g.u["username"], "telegram_unlinked", "", ip())
    return J(core.public_user(g.u["id"]))


@app.post("/api/me/delete")
@auth()
def me_delete():
    if g.u["role"] == "admin":
        raise Err("forbidden", 403)
    need_password(body().get("password"))
    log(g.u["username"], "account_deleted", f"id={g.u['id']}", ip())
    core.delete_user(g.u["id"])
    return J(ok=True)


@app.post("/api/linkcode")
@auth()
def linkcode():
    return J(code=core.make_code(g.u["id"]), bot=C.BOT_USERNAME)


# ---------------------------------------------------------------- курсы и уроки
@app.get("/api/courses")
@auth()
def courses():
    uid = g.u["id"]
    sub = bool(core.active_sub(uid))
    owned = {r["lesson_id"] for r in q("SELECT lesson_id FROM unlocks WHERE user_id=?", (uid,))}
    done = {r["lesson_id"] for r in q("SELECT DISTINCT lesson_id FROM results WHERE user_id=?", (uid,))}
    out = []
    for c in q("SELECT * FROM courses ORDER BY position, id"):
        ls = [{"id": l["id"], "title": l["title"], "open": sub or l["id"] in owned, "done": l["id"] in done}
              for l in q("SELECT id,title FROM lessons WHERE course_id=? ORDER BY position, id", (c["id"],))]
        out.append({**dict(c), "lessons": ls})
    return J(out)


@app.get("/api/lessons/<int:lid>")
@auth()
def lesson(lid):
    l = q("SELECT l.*, c.title AS course FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?", (lid,), True)
    if not l:
        raise Err("not_found", 404)
    acc = core.access(g.u["id"], lid)
    out = {"id": lid, "title": l["title"], "course": l["course"], "course_id": l["course_id"], "access": acc,
           "price": core.prices().get("lesson", {}).get(g.u["currency"])}
    sib = [r["id"] for r in q("SELECT id FROM lessons WHERE course_id=? ORDER BY position, id", (l["course_id"],))]
    i = sib.index(lid)
    out["prev"], out["next"] = (sib[i - 1] if i > 0 else None), (sib[i + 1] if i < len(sib) - 1 else None)
    if acc:
        core.touch(g.u["id"])
        lang = g.u["lang"]
        best = q("SELECT MAX(score) s, MAX(total) t FROM results WHERE user_id=? AND lesson_id=?", (g.u["id"], lid), True)
        out.update(content=core.pick(l, lang), video_url=l["video_url"], homework=l["homework"], best=[best["s"], best["t"]] if best["s"] is not None else None,
                   quiz=[{"q": a["q"], "opts": a["opts"]} for a in core.parse_quiz(l["quiz"])])
    return J(out)


@app.post("/api/lessons/<int:lid>/unlock")
@auth()
def unlock(lid):
    how = core.unlock(g.u["id"], lid, g.u["currency"])
    if how in ("free", "paid"):
        log(g.u["username"], "unlock_" + how, f"lesson {lid}", ip())
    return J(how=how)


@app.post("/api/lessons/<int:lid>/quiz")
@auth()
def quiz(lid):
    if not core.access(g.u["id"], lid):
        raise Err("locked", 403)
    ans = [a if isinstance(a, int) else -1 for a in (body().get("answers") or [])]
    s, t, correct = core.grade(g.u["id"], lid, ans)
    core.touch(g.u["id"])
    return J(score=s, total=t, correct=correct)


@app.get("/api/live")
@auth()
def live():
    uid = g.u["id"]
    rows = q("SELECT l.*, u.username, u.full_name, c.title AS course FROM live l JOIN users u ON u.id=l.teacher_id LEFT JOIN courses c ON c.id=l.course_id "
             "WHERE l.status IN ('scheduled','live') OR (l.status='ended' AND l.ended_at>?) "
             "ORDER BY CASE l.status WHEN 'live' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END, l.starts_at LIMIT 60", (core.ago(1),))
    out = [{"id": r["id"], "title": r["title"], "descr": r["descr"], "course": r["course"], "teacher": r["full_name"] or r["username"], "starts_at": r["starts_at"],
            "duration": r["duration"], "status": r["status"], "has_link": bool(r["zoom_url"]), "open": bool(core.live_access(uid, r)),
            "joined": bool(q("SELECT 1 FROM joins WHERE live_id=? AND user_id=?", (r["id"], uid), True))} for r in rows]
    recs = []
    for r in q("SELECT l.id, l.title, l.recording_url, c.title AS course FROM live l LEFT JOIN courses c ON c.id=l.course_id WHERE l.recording_url<>'' ORDER BY l.id DESC LIMIT 20"):
        ok = bool(core.live_access(uid, {"id": r["id"]}))
        recs.append({"id": r["id"], "title": r["title"], "course": r["course"], "open": ok, "url": r["recording_url"] if ok else ""})
    return J(live=out, recordings=recs, free_left=core.free_left(g.u), price=core.prices().get("lesson", {}).get(g.u["currency"]))


@app.post("/api/live/<int:lid>/seat")
@auth()
def live_seat(lid):
    how = core.unlock_live(g.u["id"], lid, g.u["currency"])
    if how in ("free", "paid"):
        log(g.u["username"], "seat_" + how, f"live {lid}", ip())
    return J(how=how)


@app.post("/api/live/<int:lid>/join")
@auth()
def live_join(lid):
    return J(url=core.live_join(g.u["id"], lid))


# ---------------------------------------------------------------- онлайн-уроки: учитель (свои) и админ (все)
@app.get("/api/tlive")
@auth("staff")
def t_list():
    rows = core.live_list(g.u, request.args.get("status", ""))
    return J(rows=rows, can_create=g.u["role"] == "teacher", zoom=bool(C.ZOOM_ACCOUNT_ID and C.ZOOM_CLIENT_ID and C.ZOOM_CLIENT_SECRET),
             now=core.fmt_now())


@app.post("/api/tlive")
@auth("staff")
def t_save():
    d = body()
    if d.get("id"):
        lid = core.live_update(g.u, int(d["id"]), d)
        log(g.u["username"], "live_update", f"#{lid}", ip())
    else:
        lid = core.live_create(g.u, d)
        log(g.u["username"], "live_create", f"#{lid} {d.get('title', '')[:60]} {d.get('starts_at', '')}", ip())
    return J(id=lid)


@app.post("/api/tlive/<int:lid>/action")
@auth("staff")
def t_action(lid):
    act = body().get("action")
    core.live_action(g.u, lid, act)
    log(g.u["username"], "live_" + str(act), f"#{lid}", ip())
    return J(ok=True)


@app.get("/api/tlive/<int:lid>/attendees")
@auth("staff")
def t_attendees(lid):
    if not core.can_manage(g.u, core.live_row(lid)):
        raise Err("not_owner", 403)
    return J(core.attendees(lid))


@app.post("/api/tlive/zoom")
@auth("staff")
def t_zoom():
    if g.u["role"] != "teacher":
        raise Err("only_teacher", 403)
    d = body()
    url = core.zoom_create(str(d.get("topic") or "English lesson")[:100], str(d.get("start") or "").replace("T", " ")[:16], int(d.get("duration") or 60))
    log(g.u["username"], "zoom_create", d.get("topic", ""), ip())
    return J(url=url)


@app.get("/api/announcements")
@auth()
def announcements():
    return J([dict(r) for r in q("SELECT * FROM announcements ORDER BY id DESC LIMIT 10")])


@app.get("/api/words")
@auth()
def words():
    return J(core.daily_words(10))


@app.get("/api/leaderboard")
@auth()
def leaderboard():
    return J(core.leaderboard())


# ---------------------------------------------------------------- деньги
@app.get("/api/prices")
@auth()
def prices():
    return J(prices=core.prices(), free_lessons=int(core.setting("free_lessons", "1")), pay_info=core.setting("pay_info"),
             support=core.setting("support"))


@app.get("/api/wallet")
@auth()
def wallet():
    uid = g.u["id"]
    return J(subs=[dict(r) for r in q("SELECT * FROM subs WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))],
             tx=[dict(r) for r in q("SELECT cur,delta,bal,reason,ts FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))],
             topups=[dict(r) for r in q("SELECT id,amount,cur,status,created FROM topups WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))])


@app.post("/api/subscribe")
@auth()
def subscribe():
    plan = body().get("plan")
    end = core.buy_plan(g.u["id"], plan, g.u["currency"])
    log(g.u["username"], "subscribe", f"{plan} {g.u['currency']}", ip())
    return J(ends=end)


@app.post("/api/topup")
@auth()
def topup():
    d = body()
    cur = d.get("currency") if d.get("currency") in C.CURRENCIES else g.u["currency"]
    try:
        amount = round(float(d.get("amount")), 2)
    except (TypeError, ValueError):
        raise Err("bad_amount")
    if not 0 < amount <= 1e9:
        raise Err("bad_amount")
    if q("SELECT COUNT(*) c FROM topups WHERE user_id=? AND status='pending'", (g.u["id"],), True)["c"] >= 5:
        raise Err("too_many_pending")
    tid = x("INSERT INTO topups(user_id,amount,cur,note,created) VALUES(?,?,?,?,?)", (g.u["id"], amount, cur, str(d.get("note", ""))[:200], core.now()))
    log(g.u["username"], "topup_request", f"#{tid} {amount} {cur}", ip())
    core.notify_admins("admin_topup", id=tid, user=g.u["username"], amount=core.money(amount, cur))
    return J(id=tid)


# ---------------------------------------------------------------- панель учителя/админа: контент
TABLES = {
    "courses": (["cat", "title", "level", "descr", "position"], "position, id"),
    "lessons": (["course_id", "title", "content_ru", "content_uz", "content_en", "content_qq", "video_url", "homework", "quiz", "position"], "course_id, position, id"),
    "announcements": (["title", "body"], "id DESC"),
    "words": (["en", "ru", "uz", "qq"], "id DESC"),
}
INTS = {"course_id", "position"}


@app.get("/api/staff/<t>")
@auth("staff")
def staff_list(t):
    if t not in TABLES:
        raise Err("not_found", 404)
    return J([dict(r) for r in q(f"SELECT * FROM {t} ORDER BY {TABLES[t][1]} LIMIT 500")])


@app.post("/api/staff/<t>")
@auth("staff")
def staff_save(t):
    if t not in TABLES:
        raise Err("not_found", 404)
    d, fields = body(), TABLES[t][0]
    vals = {}
    for f in fields:
        if f in d:
            vals[f] = (int(d[f] or 0) if f in INTS else str(d[f] or "").strip())
    for f in ("video_url",):
        if vals.get(f) and not vals[f].startswith(("http://", "https://")):
            raise Err("bad_url")
    if d.get("id"):
        if vals:
            x(f"UPDATE {t} SET " + ",".join(f"{k}=?" for k in vals) + " WHERE id=?", (*vals.values(), int(d["id"])))
        rid = int(d["id"])
    else:
        if t == "announcements":
            vals["ts"] = core.now()
        rid = x(f"INSERT INTO {t}({','.join(vals)}) VALUES({','.join('?' * len(vals))})", tuple(vals.values()))
        if t == "announcements" and d.get("push"):
            core.broadcast("📢 " + vals.get("title", "") + "\n\n" + vals.get("body", ""))
    log(g.u["username"], f"staff_save_{t}", f"id={rid}", ip())
    return J(id=rid)


@app.delete("/api/staff/<t>/<int:rid>")
@auth("staff")
def staff_delete(t, rid):
    if t not in TABLES:
        raise Err("not_found", 404)
    if t == "courses" and g.u["role"] != "admin":
        raise Err("forbidden", 403)
    if t == "courses":
        x("DELETE FROM lessons WHERE course_id=?", (rid,))
    x(f"DELETE FROM {t} WHERE id=?", (rid,))
    log(g.u["username"], f"staff_delete_{t}", f"id={rid}", ip())
    return J(ok=True)


# ---------------------------------------------------------------- админ-панель
@app.get("/api/admin/stats")
@auth("admin")
def a_stats():
    n = lambda s, a=(): q(s, a, True)[0]
    return J(users=n("SELECT COUNT(*) FROM users"), new7=n("SELECT COUNT(*) FROM users WHERE created>?", (core.ago(7),)),
             subs=n("SELECT COUNT(DISTINCT user_id) FROM subs WHERE ends>?", (core.now(),)),
             pending=n("SELECT COUNT(*) FROM topups WHERE status='pending'"), lessons=n("SELECT COUNT(*) FROM lessons"),
             tg=n("SELECT COUNT(*) FROM users WHERE tg_id IS NOT NULL"),
             revenue={r["cur"]: r["s"] for r in q("SELECT cur, -SUM(delta) s FROM tx WHERE reason LIKE 'sub:%' OR reason LIKE 'lesson:%' OR reason LIKE 'live:%' GROUP BY cur")},
             signups=signups(14), live_now=n("SELECT COUNT(*) FROM live WHERE status='live'"), live_up=n("SELECT COUNT(*) FROM live WHERE status='scheduled'"),
             teachers=n("SELECT COUNT(*) FROM users WHERE role='teacher'"))


def signups(days):
    got = {r["d"]: r["c"] for r in q("SELECT substr(created,1,10) d, COUNT(*) c FROM users WHERE created>=? GROUP BY d", (core.today(-days + 1),))}
    return [{"d": core.today(-i), "c": got.get(core.today(-i), 0)} for i in range(days - 1, -1, -1)]


@app.get("/api/admin/users.csv")
@auth("admin")
def a_users_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "username", "email", "full_name", "role", "lang", "telegram_id", "blocked", "created", "last_login", "UZS", "USD", "KZT", "subscription_until"])
    for r in q("SELECT * FROM users ORDER BY id"):
        b, sb = core.balances(r["id"]), core.active_sub(r["id"])
        w.writerow([r["id"], r["username"], r["email"], r["full_name"], r["role"], r["lang"], r["tg_id"] or "", r["blocked"], r["created"], r["last_login"],
                    b["UZS"], b["USD"], b["KZT"], sb["ends"] if sb else ""])
    log(g.u["username"], "export_users_csv", "", ip())
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})


@app.get("/api/admin/users")
@auth("admin")
def a_users():
    s = "%" + request.args.get("q", "").strip() + "%"
    out = []
    for r in q("SELECT id,username,email,role,lang,blocked,tg_id,created,free_used FROM users "
               "WHERE username LIKE ? OR email LIKE ? OR CAST(tg_id AS TEXT) LIKE ? ORDER BY id DESC LIMIT 100", (s, s, s)):
        d = dict(r)
        d["bal"] = core.balances(r["id"])
        sb = core.active_sub(r["id"])
        d["sub"] = sb["ends"] if sb else None
        out.append(d)
    return J(out)


def target(uid):
    u = q("SELECT * FROM users WHERE id=?", (uid,), True)
    if not u:
        raise Err("not_found", 404)
    return u


@app.patch("/api/admin/users/<int:uid>")
@auth("admin")
def a_user_patch(uid):
    u, d, me_ = target(uid), body(), g.u["username"]
    if "role" in d and d["role"] in ("student", "teacher", "admin"):
        if uid == g.u["id"] and d["role"] != "admin":
            raise Err("forbidden", 403)
        x("UPDATE users SET role=? WHERE id=?", (d["role"], uid))
        log(me_, "set_role", f"{u['username']} -> {d['role']}", ip())
    if "blocked" in d:
        if uid == g.u["id"]:
            raise Err("forbidden", 403)
        x("UPDATE users SET blocked=? WHERE id=?", (1 if d["blocked"] else 0, uid))
        if d["blocked"]:
            x("DELETE FROM sessions WHERE user_id=?", (uid,))
        log(me_, "block" if d["blocked"] else "unblock", u["username"], ip())
    if d.get("password"):
        if len(d["password"]) < 6:
            raise Err("short_password")
        x("UPDATE users SET pw=? WHERE id=?", (core.hash_pw(d["password"]), uid))
        x("DELETE FROM sessions WHERE user_id=? AND user_id<>?", (uid, g.u["id"]))
        log(me_, "reset_password", u["username"], ip())
    if "free_used" in d:
        x("UPDATE users SET free_used=? WHERE id=?", (max(0, int(d["free_used"])), uid))
        log(me_, "set_free_used", f"{u['username']} = {d['free_used']}", ip())
    return J(ok=True)


@app.post("/api/admin/users/<int:uid>/balance")
@auth("admin")
def a_balance(uid):
    u, d = target(uid), body()
    cur, mode = d.get("cur"), d.get("mode")
    try:
        amount = round(float(d.get("amount")), 2)
    except (TypeError, ValueError):
        raise Err("bad_amount")
    if cur not in C.CURRENCIES or mode not in ("add", "sub", "set") or amount < 0:
        raise Err("bad_amount")
    reason = "admin:" + (str(d.get("reason") or "")[:80] or mode)
    new = (core.set_balance(uid, cur, amount, reason, g.u["username"]) if mode == "set"
           else core.adjust(uid, cur, amount if mode == "add" else -amount, reason, g.u["username"]))
    log(g.u["username"], "balance_" + mode, f"{u['username']} {amount} {cur} -> {new}", ip())
    core.notify(uid, "bal_changed", amount=core.money(new, cur))
    return J(balance=new)


@app.post("/api/admin/users/<int:uid>/grant")
@auth("admin")
def a_grant(uid):
    u, plan = target(uid), body().get("plan")
    if plan not in C.PLANS or plan == "lesson":
        raise Err("bad_plan")
    end = core.grant_plan(uid, plan, g.u["username"])
    log(g.u["username"], "grant_sub", f"{u['username']} {plan} until {end}", ip())
    core.notify(uid, "sub_granted", date=end[:10])
    return J(ends=end)


@app.get("/api/admin/prices")
@auth("admin")
def a_prices():
    return J(core.prices())


@app.put("/api/admin/prices")
@auth("admin")
def a_prices_put():
    d, changes = body(), []
    for plan, row in d.items():
        for cur, val in (row or {}).items():
            if plan in C.PLANS and cur in C.CURRENCIES:
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    raise Err("bad_amount")
                if val < 0:
                    raise Err("bad_amount")
                old = q("SELECT amount FROM prices WHERE plan=? AND cur=?", (plan, cur), True)
                if not old or old["amount"] != val:
                    changes.append(f"{plan}/{cur}: {old['amount'] if old else '-'} -> {val}")
                x("INSERT INTO prices(plan,cur,amount) VALUES(?,?,?) ON CONFLICT(plan,cur) DO UPDATE SET amount=excluded.amount", (plan, cur, val))
    log(g.u["username"], "prices_changed", "; ".join(changes) or "no changes", ip())
    return J(ok=True)


@app.get("/api/admin/topups")
@auth("admin")
def a_topups():
    st = request.args.get("status", "")
    sql = "SELECT t.*, u.username FROM topups t JOIN users u ON u.id=t.user_id " + ("WHERE t.status=? " if st else "") + "ORDER BY t.id DESC LIMIT 100"
    return J([dict(r) for r in q(sql, (st,) if st else ())])


@app.post("/api/admin/topups/<int:tid>")
@auth("admin")
def a_topup_handle(tid):
    act = body().get("action")
    if act not in ("approve", "reject"):
        raise Err("bad_action")
    with core.trans() as con:
        t = con.execute("SELECT * FROM topups WHERE id=?", (tid,)).fetchone()
        if not t:
            raise Err("not_found", 404)
        if t["status"] != "pending":
            raise Err("already_handled", 409)
        if act == "approve":
            core._adj(con, t["user_id"], t["cur"], t["amount"], f"topup:{tid}", g.u["username"])
        con.execute("UPDATE topups SET status=?, handled_by=? WHERE id=?", ("approved" if act == "approve" else "rejected", g.u["username"], tid))
    log(g.u["username"], "topup_" + act, f"#{tid} {t['amount']} {t['cur']}", ip())
    core.notify(t["user_id"], "topup_ok" if act == "approve" else "topup_no", amount=core.money(t["amount"], t["cur"]))
    return J(ok=True)


@app.get("/api/admin/logs")
@auth("admin")
def a_logs():
    s = "%" + request.args.get("q", "").strip() + "%"
    off = max(0, int(request.args.get("offset", 0) or 0))
    return J([dict(r) for r in q("SELECT * FROM logs WHERE actor LIKE ? OR action LIKE ? OR detail LIKE ? ORDER BY id DESC LIMIT 100 OFFSET ?", (s, s, s, off))])


@app.get("/api/admin/tx")
@auth("admin")
def a_tx():
    s = "%" + request.args.get("q", "").strip() + "%"
    return J([dict(r) for r in q("SELECT t.*, u.username FROM tx t JOIN users u ON u.id=t.user_id WHERE u.username LIKE ? OR t.reason LIKE ? ORDER BY t.id DESC LIMIT 150", (s, s))])


@app.get("/api/admin/settings")
@auth("admin")
def a_settings():
    return J({k: core.setting(k) for k in core.DEFAULT_SETTINGS})


@app.put("/api/admin/settings")
@auth("admin")
def a_settings_put():
    d = body()
    for k in core.DEFAULT_SETTINGS:
        if k in d:
            if k == "free_lessons" and not str(d[k]).isdigit():
                raise Err("bad_amount")
            v = str(d[k]).strip()[:500]
            if k.startswith("social_") and v and not v.startswith(("http://", "https://")):
                raise Err("bad_url")
            core.set_setting(k, v)
    log(g.u["username"], "settings_changed", {k: d[k] for k in d if k in ("free_lessons", "support")}, ip())
    return J(ok=True)


@app.post("/api/admin/broadcast")
@auth("admin")
def a_broadcast():
    text = str(body().get("text") or "").strip()[:3500]
    if not text:
        raise Err("empty")
    n = core.broadcast(text)
    log(g.u["username"], "broadcast", f"{n} users: {text[:80]}", ip())
    return J(sent=n, bot=bool(C.BOT_TOKEN))


@app.get("/api/admin/backup")
@auth("admin")
def a_backup():
    path = os.path.join(tempfile.gettempdir(), "academy-backup.db")
    if os.path.exists(path):
        os.remove(path)
    src, dst = core.db(), sqlite3.connect(path)
    src.backup(dst)
    dst.close()
    src.close()
    log(g.u["username"], "backup_download", "", ip())
    return send_file(path, as_attachment=True, download_name="academy-backup.db")


if __name__ == "__main__":
    core.init()
    core.start_scheduler()
    if C.ADMIN_PASS == "admin12345":
        print("!!! Смените ADMIN_PASS в файле .env (сейчас пароль по умолчанию) !!!")
    print(f"Сайт: http://localhost:{C.PORT}   Админка: http://localhost:{C.PORT}/admin")
    app.run(host=C.HOST, port=C.PORT, threaded=True)
