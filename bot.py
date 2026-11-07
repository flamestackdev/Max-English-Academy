"""Telegram-бот (4 языка). Использует ту же базу, что и сайт. Запуск: python bot.py"""
import secrets
import time

import requests

import config as C
import core
import texts
from core import q, x, Err

if not C.BOT_TOKEN:
    raise SystemExit("Укажите BOT_TOKEN в файле .env (токен получите у @BotFather)")

API = f"https://api.telegram.org/bot{C.BOT_TOKEN}/"
QZ = {}  # chat_id -> состояние теста


def call(method, **data):
    try:
        return requests.post(API + method, json=data, timeout=70).json()
    except Exception as e:
        print("telegram error:", e)
        time.sleep(2)
        return {}


def T(u, key, **kw):
    return texts.m(u["lang"], key, **kw)


def send(chat, text, kb=None, inline=None):
    d = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
    if inline:
        d["reply_markup"] = {"inline_keyboard": inline}
    elif kb:
        d["reply_markup"] = kb
    call("sendMessage", **d)


def edit(chat, msg_id, text, inline):
    call("editMessageText", chat_id=chat, message_id=msg_id, text=text[:4000], reply_markup={"inline_keyboard": inline})


BY_LABEL = {lab: k for k, v in texts.LABELS.items() for lab in v}


def menu(u):
    i = texts.IDX[u["lang"]]
    keys = [k for k in texts.LABELS if k != "teacher" or u["role"] in ("teacher", "admin")]
    rows = [[{"text": texts.LABELS[k][i]} for k in keys[n:n + 2]] for n in range(0, len(keys), 2)]
    return {"keyboard": rows, "resize_keyboard": True}


def fresh(u):
    return q("SELECT * FROM users WHERE id=?", (u["id"],), True)


def get_user(frm):
    tid = frm["id"]
    u = q("SELECT * FROM users WHERE tg_id=?", (tid,), True)
    if u:
        return None if u["blocked"] else u
    lc = (frm.get("language_code") or "")[:2]
    name = f"tg{tid}"
    core.create_user(name, secrets.token_urlsafe(12), "", lang=lc if lc in ("uz", "en") else "ru", tg_id=tid)
    core.log(name, "register", "telegram")
    return q("SELECT * FROM users WHERE tg_id=?", (tid,), True)


def err_text(u, e):
    key = {"insufficient": "err_insufficient", "no_price": "err_no_price", "bad_amount": "err_bad_amount", "bad_code": "err_bad_code"}.get(e.msg, "err_generic")
    return T(u, key)


# ---------------------------------------------------------------- курсы и уроки
def start(chat, u):
    send(chat, T(u, "start"), kb=menu(u))


def show_courses(chat, u):
    rows = [[{"text": f"{r['title']} ({r['level']})", "callback_data": f"c:{r['id']}"}] for r in q("SELECT * FROM courses ORDER BY position, id")]
    send(chat, T(u, "choose_course"), inline=rows)


def show_course(chat, u, cid):
    c = q("SELECT * FROM courses WHERE id=?", (cid,), True)
    if c:
        rows = [[{"text": ("🔓 " if core.access(u["id"], l["id"]) else "🔒 ") + l["title"], "callback_data": f"l:{l['id']}"}]
                for l in q("SELECT id,title FROM lessons WHERE course_id=? ORDER BY position, id", (cid,))]
        send(chat, f"{c['title']} · {c['level']}\n{c['descr']}", inline=rows or None)


def show_lesson(chat, u, lid):
    l = q("SELECT * FROM lessons WHERE id=?", (lid,), True)
    if not l:
        return
    if not core.access(u["id"], lid):
        p = core.prices().get("lesson", {}).get(u["currency"])
        rows, fl = [], core.free_left(u)
        if fl:
            rows.append([{"text": T(u, "open_free", n=fl), "callback_data": f"ul:{lid}"}])
        elif p:
            rows.append([{"text": T(u, "buy_lesson", price=core.money(p, u["currency"])), "callback_data": f"ul:{lid}"}])
        rows.append([{"text": T(u, "plans_btn"), "callback_data": "plans"}])
        return send(chat, f"🔒 {l['title']}\n" + T(u, "closed"), inline=rows)
    msg = f"📘 {l['title']}\n\n{core.pick(l, u['lang'])}"
    if l["homework"]:
        msg += T(u, "homework") + l["homework"]
    rows = []
    if l["video_url"]:
        rows.append([{"text": T(u, "video"), "url": l["video_url"]}])
    if core.parse_quiz(l["quiz"]):
        rows.append([{"text": T(u, "take_quiz"), "callback_data": f"qz:{lid}"}])
    core.touch(u["id"])
    send(chat, msg, inline=rows or None)


def do_unlock(chat, u, lid):
    try:
        how = core.unlock(u["id"], lid, u["currency"])
        if how in ("free", "paid"):
            core.log(u["username"], "unlock_" + how, f"lesson {lid} (bot)")
        show_lesson(chat, fresh(u), lid)
    except Err as e:
        send(chat, err_text(u, e))


# ---------------------------------------------------------------- тарифы, баланс
def show_plans(chat, u):
    pr = core.prices()
    rows = [[{"text": f"{core.plan_name(p, u['lang'])} — {core.money(pr[p][u['currency']], u['currency'])}", "callback_data": f"buy:{p}"}]
            for p in ("m1", "m3", "m6", "y1") if p in pr and u["currency"] in pr[p]]
    sb = core.active_sub(u["id"])
    send(chat, (T(u, "sub_until", date=sb["ends"][:10]) if sb else "") + T(u, "plans_head", cur=u["currency"]), inline=rows)


def show_wallet(chat, u):
    b = core.balances(u["id"])
    rows = [[{"text": ("✅ " if c == u["currency"] else "") + c, "callback_data": f"cur:{c}"} for c in C.CURRENCIES]]
    send(chat, T(u, "wallet_head") + "\n".join(core.money(b[c], c) for c in C.CURRENCIES) + T(u, "topup_hint", cur=u["currency"]) + core.setting("pay_info"), inline=rows)


# ---------------------------------------------------------------- онлайн-уроки
def live_card(u, l, teacher):
    return T(u, "live_card", when=l["starts_at"], dur=l["duration"], title=l["title"], teacher=teacher, status=T(u, "st_" + l["status"]))


def live_buttons(u, l):
    acc = core.live_access(u["id"], l)
    if acc:
        return [[{"text": T(u, "btn_zoom"), "callback_data": f"jn:{l['id']}"}]] if l["zoom_url"] else []
    fl = core.free_left(u)
    p = core.prices().get("lesson", {}).get(u["currency"])
    rows = []
    if fl:
        rows.append([{"text": T(u, "seat_free", n=fl), "callback_data": f"sk:{l['id']}"}])
    elif p:
        rows.append([{"text": T(u, "seat_pay", price=core.money(p, u["currency"])), "callback_data": f"sk:{l['id']}"}])
    rows.append([{"text": T(u, "plans_btn"), "callback_data": "plans"}])
    return rows


def show_live(chat, u):
    rows = q("SELECT l.*, us.username, us.full_name FROM live l JOIN users us ON us.id=l.teacher_id WHERE l.status IN ('scheduled','live') "
             "ORDER BY CASE l.status WHEN 'live' THEN 0 ELSE 1 END, l.starts_at LIMIT 10")
    if not rows:
        return send(chat, T(u, "no_live"))
    for l in rows:
        send(chat, live_card(u, l, l["full_name"] or l["username"]), inline=live_buttons(u, l) or None)


def show_live_item(chat, u, lid):
    l = q("SELECT l.*, us.username, us.full_name FROM live l JOIN users us ON us.id=l.teacher_id WHERE l.id=?", (lid,), True)
    if l:
        send(chat, live_card(u, l, l["full_name"] or l["username"]), inline=live_buttons(u, l) or None)


def do_join(chat, u, lid):
    try:
        url = core.live_join(u["id"], lid)
        send(chat, "🎥 " + core.live_row(lid)["title"], inline=[[{"text": T(u, "btn_zoom"), "url": url}]])
    except Err as e:
        send(chat, {"locked": T(u, "closed"), "no_link": "⏳", "too_early": "⏳ 30 min", "bad_status": "—"}.get(e.msg, err_text(u, e)))


def do_seat(chat, u, lid):
    try:
        how = core.unlock_live(u["id"], lid, u["currency"])
        if how in ("free", "paid"):
            core.log(u["username"], "seat_" + how, f"live {lid} (bot)")
        send(chat, T(u, "seat_ok"))
        show_live_item(chat, fresh(u), lid)
    except Err as e:
        send(chat, err_text(u, e))


def show_teacher(chat, u):
    rows = [l for l in core.live_list(u) if l["status"] in ("scheduled", "live")]
    if not rows:
        return send(chat, T(u, "t_empty"))
    send(chat, T(u, "t_head"))
    for l in rows:
        btn = []
        if l["status"] == "scheduled":
            btn.append({"text": T(u, "t_start"), "callback_data": f"tl:start:{l['id']}"})
        if l["status"] == "live":
            btn.append({"text": T(u, "t_end"), "callback_data": f"tl:end:{l['id']}"})
        btn.append({"text": T(u, "t_cancel"), "callback_data": f"tl:cancel:{l['id']}"})
        send(chat, live_card(u, l, l["full_name"] or l["username"]) + "\n" + T(u, "t_joined", n=l["joined"]), inline=[btn])


def teacher_action(chat, u, act, lid):
    try:
        core.live_action(u, lid, act)
        core.log(u["username"], "live_" + act, f"#{lid} (bot)")
        send(chat, T(u, "t_done"))
    except Err as e:
        send(chat, T(u, "t_forbidden") if e.msg == "not_owner" else err_text(u, e))


# ---------------------------------------------------------------- рейтинг, слова, профиль, настройки
def show_top(chat, u):
    rows = core.leaderboard(10)
    send(chat, T(u, "top_head") + ("\n".join(f"{i + 1}. {r['username']} — {r['pts']}" for i, r in enumerate(rows)) or T(u, "empty")))


def show_words(chat, u):
    key = "ru" if u["lang"] == "en" else u["lang"]
    send(chat, T(u, "words_head") + "\n".join(f"• {w['en']} — {w[key] or w['en']}" for w in core.daily_words(10)))


def show_link(chat, u):
    send(chat, T(u, "link_help"))


def show_profile(chat, u):
    u = fresh(u)
    p, st = core.public_user(u["id"]), core.user_stats(u["id"])
    b = p["bal"]
    sub = T(u, "prof_until", d=p["sub"]["ends"][:10]) if p["sub"] else T(u, "prof_none")
    rank = T(u, "prof_rank", r=st["rank"]) if st["rank"] else ""
    txt = (f"👤 {u['username']}" + (f" ({u['full_name']})" if u["full_name"] else "") + f"\n📧 {u['email'] or '—'}\n" + T(u, "role_line", r=T(u, "role_" + u["role"])) + "\n"
           + (f"🌐 {C.SITE_URL}\n" if C.SITE_URL else "") + T(u, "prof_sub", v=sub) + "\n💰 " + " · ".join(core.money(b[c], c) for c in C.CURRENCIES) + "\n"
           + T(u, "prof_stats", streak=p["streak"], pts=st["points"], rank=rank, done=p["progress"]["done"], total=p["progress"]["total"]))
    send(chat, txt, inline=[[{"text": T(u, "btn_link"), "callback_data": "linkhelp"}, {"text": T(u, "btn_newpass"), "callback_data": "newpass"}], [{"text": T(u, "btn_settings"), "callback_data": "st:open"}]])


def settings_view(u):
    mark = lambda ok: "✅ " if ok else ""
    langs = [{"text": mark(u["lang"] == l) + C.LANG_NAMES[l], "callback_data": f"st:lang:{l}"} for l in C.LANGS]
    rows = [langs[:2], langs[2:], [{"text": mark(c == u["currency"]) + c, "callback_data": f"st:cur:{c}"} for c in C.CURRENCIES],
            [{"text": T(u, "notify_btn", s=T(u, "on" if u["notify_tg"] else "off")), "callback_data": "st:notify"}],
            [{"text": T(u, "btn_profile"), "callback_data": "st:profile"}]]
    return T(u, "settings_text"), rows


def show_settings(chat, u):
    text, rows = settings_view(fresh(u))
    send(chat, text, inline=rows)


def on_settings(cb, chat, u, arg):
    kind, _, val = arg.partition(":")
    if kind == "profile":
        return show_profile(chat, u)
    if kind == "lang" and val in C.LANGS:
        x("UPDATE users SET lang=? WHERE id=?", (val, u["id"]))
        core.log(u["username"], "set_lang", f"{val} (bot)")
        send(chat, texts.m(val, "lang_set"), kb=menu(fresh(u)))
    elif kind == "cur" and val in C.CURRENCIES:
        x("UPDATE users SET currency=? WHERE id=?", (val, u["id"]))
    elif kind == "notify":
        x("UPDATE users SET notify_tg=? WHERE id=?", (0 if u["notify_tg"] else 1, u["id"]))
    text, rows = settings_view(fresh(u))
    edit(chat, cb["message"]["message_id"], text, rows)


def do_newpass(chat, u):
    pw = secrets.token_urlsafe(8)
    x("UPDATE users SET pw=? WHERE id=?", (core.hash_pw(pw), u["id"]))
    x("DELETE FROM sessions WHERE user_id=?", (u["id"],))
    core.log(u["username"], "password_reset", "via bot")
    send(chat, T(u, "newpass", login=u["username"], pw=pw))


ACTIONS = {"courses": show_courses, "live": show_live, "plans": show_plans, "wallet": show_wallet, "words": show_words,
           "top": show_top, "profile": show_profile, "settings": show_settings, "teacher": show_teacher}


# ---------------------------------------------------------------- тесты
def quiz_start(chat, u, lid):
    l = q("SELECT quiz FROM lessons WHERE id=?", (lid,), True)
    qs = core.parse_quiz(l["quiz"]) if l else []
    if qs and core.access(u["id"], lid):
        QZ[chat] = {"lid": lid, "qs": qs, "i": 0, "ans": []}
        quiz_ask(chat, u)


def quiz_ask(chat, u):
    s = QZ[chat]
    cur = s["qs"][s["i"]]
    send(chat, T(u, "quiz_q", i=s["i"] + 1, n=len(s["qs"]), q=cur["q"]), inline=[[{"text": o, "callback_data": f"a:{j}"}] for j, o in enumerate(cur["opts"])])


def quiz_answer(chat, u, j):
    s = QZ.get(chat)
    if not s:
        return
    s["ans"].append(j)
    s["i"] += 1
    if s["i"] < len(s["qs"]):
        return quiz_ask(chat, u)
    QZ.pop(chat)
    score, total, _ = core.grade(u["id"], s["lid"], s["ans"])
    core.touch(u["id"])
    send(chat, T(u, "quiz_res", s=score, n=total, p=score * 10))


# ---------------------------------------------------------------- обработка
def on_message(m):
    chat, text = m["chat"]["id"], (m.get("text") or "").strip()
    u = get_user(m["from"])
    if not u:
        return
    if text.startswith("/start"):
        return start(chat, u)
    if text.startswith("/link"):
        parts = text.split()
        if len(parts) < 2:
            return show_link(chat, u)
        try:
            core.use_code(parts[1], m["from"]["id"])
            nu = q("SELECT * FROM users WHERE tg_id=?", (m["from"]["id"],), True)
            return send(chat, T(nu, "link_ok"), kb=menu(nu))
        except Err as e:
            return send(chat, err_text(u, e))
    if text.startswith("/newpass"):
        return do_newpass(chat, u)
    if text.startswith(("/settings", "/lang")):
        return show_settings(chat, u)
    if text.startswith("/profile"):
        return show_profile(chat, u)
    if text.startswith("/topup"):
        try:
            amount = round(float(text.split()[1].replace(",", ".")), 2)
            if not 0 < amount <= 1e9:
                raise ValueError
        except (IndexError, ValueError):
            return send(chat, T(u, "topup_example"))
        tid = x("INSERT INTO topups(user_id,amount,cur,note,created) VALUES(?,?,?,?,?)", (u["id"], amount, u["currency"], "telegram", core.now()))
        core.log(u["username"], "topup_request", f"#{tid} {amount} {u['currency']} (bot)")
        core.notify_admins("admin_topup", id=tid, user=u["username"], amount=core.money(amount, u["currency"]))
        return send(chat, T(u, "topup_sent", id=tid, amount=core.money(amount, u["currency"]), info=core.setting("pay_info")))
    k = BY_LABEL.get(text)
    if k:
        return ACTIONS[k](chat, u)
    send(chat, T(u, "pick_menu"), kb=menu(u))


def on_callback(cb):
    call("answerCallbackQuery", callback_query_id=cb["id"])
    chat = cb["message"]["chat"]["id"]
    u = get_user(cb["from"])
    if not u:
        return
    act, _, arg = cb["data"].partition(":")
    num = lambda: int(arg.split(":")[-1])
    if act == "c":
        show_course(chat, u, num())
    elif act == "l":
        show_lesson(chat, u, num())
    elif act == "ul":
        do_unlock(chat, u, num())
    elif act == "qz":
        quiz_start(chat, u, num())
    elif act == "a":
        quiz_answer(chat, u, num())
    elif act == "plans":
        show_plans(chat, u)
    elif act == "buy":
        try:
            end = core.buy_plan(u["id"], arg, u["currency"])
            core.log(u["username"], "subscribe", f"{arg} {u['currency']} (bot)")
            send(chat, T(u, "sub_bought", date=end[:10]))
        except Err as e:
            send(chat, err_text(u, e))
    elif act == "cur" and arg in C.CURRENCIES:
        x("UPDATE users SET currency=? WHERE id=?", (arg, u["id"]))
        show_wallet(chat, fresh(u))
    elif act == "lv":
        show_live_item(chat, u, num())
    elif act == "jn":
        do_join(chat, u, num())
    elif act == "sk":
        do_seat(chat, u, num())
    elif act == "tl" and u["role"] in ("teacher", "admin"):
        verb, _, lid = arg.partition(":")
        teacher_action(chat, u, verb, int(lid))
    elif act == "linkhelp":
        show_link(chat, u)
    elif act == "newpass":
        do_newpass(chat, u)
    elif act == "st":
        on_settings(cb, chat, u, arg)


def main():
    core.init()
    core.start_scheduler()   # напоминания за 15 минут и «урок начался» (идемпотентно, безопасно вместе с сайтом)
    print("Бот запущен. Остановить: Ctrl+C")
    offset = 0
    while True:
        res = call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        for up in res.get("result", []):
            offset = up["update_id"] + 1
            try:
                if "message" in up:
                    on_message(up["message"])
                elif "callback_query" in up:
                    on_callback(up["callback_query"])
            except Exception as e:
                print("handler error:", repr(e))


if __name__ == "__main__":
    main()
