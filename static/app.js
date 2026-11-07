if (!localStorage.token) location.href = '/';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = u => /^https?:\/\//.test(u) ? esc(u) : '#';
const CAT = { grammar: '#7494ec', listening: '#e8a23a', reading: '#2f9e6e', speaking: '#d9608a', writing: '#8a6fe0', vocabulary: '#1fa5b8' };
const catName = c => D['cat_' + c] ? t('cat_' + c) : c;
let ME = null;

async function api(p, o = {}) {
  const r = await fetch('/api/' + p, {
    method: o.method || 'GET',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.token },
    body: o.body ? JSON.stringify(o.body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { localStorage.removeItem('token'); location.href = '/'; throw d; }
  if (!r.ok) throw d;
  return d;
}
function toast(m, bad) {
  const e = $('#toast'); e.textContent = m; e.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => e.className = '', 3200);
}
const fail = e => toast(D['e_' + e.error] ? t('e_' + e.error) : (e.error || t('e_x')), 1);
const money = (a, c) => {
  const s = a < 0 ? '-' : ''; a = Math.abs(+a);
  return s + (c === 'USD' ? '$' + a.toLocaleString('en-US', { maximumFractionDigits: 2 }) : a.toLocaleString('ru-RU') + ' ' + (c === 'KZT' ? '₸' : t('sum')));
};
const v = h => $('#v').innerHTML = h;

function chrome(name) {
  const staff = ME && (ME.role === 'admin' || ME.role === 'teacher');
  $('#hdr').innerHTML = `<b>Max English</b>` + (staff ? `<a class="pill" href="/admin">${t(ME.role === 'admin' ? 'a_panel' : 'a_panel_t')}</a>` : '') +
    `<button type="button" data-dn data-s=".3"></button><a class="avatar sm" href="#/profile" aria-label="${t('profile')}">${esc(initials(ME))}</a>`;
  mountToggles($('#hdr'));
  const tabs = [['home', 'bx-home'], ['courses', 'bx-book-open'], ['live', 'bx-video'], ['wallet', 'bx-wallet'], ['top', 'bx-trophy']];
  const cur = ['course', 'lesson'].includes(name) ? 'courses' : name;
  $('#nav').innerHTML = tabs.map(([k, i]) => `<a href="#/${k}" class="${k === cur ? 'on' : ''}"><i class="bx ${i}"></i>${t(k)}</a>`).join('');
  document.documentElement.lang = lang;
}

// ---- онлайн-уроки (Zoom)
let LIVE = {};
const pad = n => String(n).padStart(2, '0');
const localISO = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dayLabel = s => { const td = new Date(), tm = new Date(Date.now() + 864e5), d = s.slice(0, 10); return d === localISO(td) ? t('today') : d === localISO(tm) ? t('tomorrow') : d; };
const eta = s => {
  const m = Math.round((new Date(s.replace(' ', 'T') + ':00') - Date.now()) / 6e4);
  if (m <= 0) return ''; const d = Math.floor(m / 1440), h = Math.floor(m % 1440 / 60);
  return `${t('starts_in')} ` + (d ? `${d} ${t('days')} ${h} h` : h ? `${h} h ${m % 60} ${t('min')}` : `${m} ${t('min')}`);
};
const lvTag = st => `<span class="tag ${st === 'live' ? 'bad' : st === 'ended' ? '' : 'ok'}">${st === 'live' ? '● ' : ''}${t('ls_' + st)}</span>`;
function liveCard(l, o) {
  LIVE[l.id] = l;
  let act = '';
  if (l.status === 'ended') act = l.joined ? `<span class="tag ok">${t('was_there')}</span>` : '';
  else if (l.open) act = l.has_link ? `<button class="btn sm" data-a="join" data-id="${l.id}">🎥 ${t('join')}</button>` : `<span class="tag warn">${t('soon_link')}</span>`;
  else act = (o.free_left > 0 ? `<button class="btn sm" data-a="seat" data-id="${l.id}">🎁 ${t('seat_free')}</button>`
      : (o.price != null ? `<button class="btn sm" data-a="seat" data-id="${l.id}">${t('seat_pay')} — ${money(o.price, ME.currency)}</button>` : '')) + ` <a class="btn sm ghost" href="#/wallet">${t('to_plans')}</a>`;
  return `<div class="box lv${l.status === 'live' ? ' now' : ''}"><div class="gap" style="justify-content:space-between">${lvTag(l.status)}<span class="muted">${esc(dayLabel(l.starts_at))} ${esc(l.starts_at.slice(11, 16))} · ${l.duration} ${t('min')}</span></div>
    <h3 style="margin:8px 0 2px;font-size:17px">${esc(l.title)}</h3><p class="muted">👩‍🏫 ${esc(l.teacher)}${l.course ? ' · ' + esc(l.course) : ''}</p>${l.descr ? `<p class="muted" style="margin-top:4px">${esc(l.descr)}</p>` : ''}
    ${l.status === 'scheduled' ? `<p class="muted" style="margin-top:4px">⏳ ${esc(eta(l.starts_at))}</p>` : ''}
    <div class="gap" style="margin-top:10px">${act}${l.status !== 'ended' ? `<button class="btn sm ghost" data-a="cal" data-id="${l.id}">📅 ${t('add_cal')}</button>` : ''}</div></div>`;
}

// ------------------------------------------------------------ экраны
async function home() {
  const [me, lv, news, ws] = await Promise.all([api('me'), api('live'), api('announcements'), api('words')]);
  ME = me;
  const nx = lv.live.find(x => x.status !== 'ended');
  let last = null; try { last = JSON.parse(localStorage.last || 'null'); } catch (e) { }
  v(`<div class="hero"><h1>${t('hi')}, ${esc(me.username)}!</h1>
    <p>${me.sub ? t('sub_till') + ' ' + me.sub.ends.slice(0, 10) : t('no_sub')}</p>
    ${me.free_left ? `<p>🎁 ${t('free_note')} · ${t('free_left')}: ${me.free_left}</p>` : ''}
    <div class="chips">${me.streak ? `<span class="chip">🔥 ${me.streak} ${t('days')}</span>` : ''}${Object.entries(me.bal).map(([c, a]) => `<span class="chip">${money(a, c)}</span>`).join('')}</div>
    <p style="margin-top:12px">${t('progress')}: ${me.progress.done}/${me.progress.total}</p><div class="bar"><i style="width:${me.progress.total ? Math.round(me.progress.done / me.progress.total * 100) : 0}%"></i></div></div>
    ${last ? `<a class="btn block" style="margin-top:12px" href="#/lesson/${last.id}">▶ ${t('cont')}: ${esc(last.title)}</a>` : ''}
    <div class="cols"><div><h2>${t('next_live')}</h2>` + (nx ? liveCard(nx, lv) : `<p class="muted">${t('no_live')}</p>`) +
    (news.length ? `<h2>${t('news')}</h2><div class="list">${news.map(n => `<div class="row"><div class="grow"><b>${esc(n.title)}</b><span class="muted">${esc(n.body)}</span></div></div>`).join('')}</div>` : '') + `</div><div>` +
    `<h2>${t('words')}</h2><div class="box words">${ws.map(w => `<div><b>${esc(w.en)}</b> — ${esc(lang === 'en' ? w.ru + ' / ' + w.uz : (w[lang] || w.en))}</div>`).join('')}</div>` + `</div></div>`);
}

async function courses() {
  const cs = await api('courses');
  const draw = q => {
    const f = cs.filter(c => (c.title + ' ' + c.descr + ' ' + c.level + ' ' + c.cat).toLowerCase().includes(q.toLowerCase()));
    const cats = [...new Set(f.map(c => c.cat))];
    return cats.map(cat => `<h2>${esc(catName(cat))}</h2><div class="cg">` + f.filter(c => c.cat === cat).map(c => {
      const done = c.lessons.filter(l => l.done).length, pc = c.lessons.length ? Math.round(done / c.lessons.length * 100) : 0;
      return `<a class="row" href="#/course/${c.id}"><span class="dot" style="background:${CAT[cat] || '#7494ec'}"></span>
        <div class="grow"><b>${esc(c.title)}</b><span class="muted">${esc(c.descr)}</span><div class="bar"><i style="width:${pc}%"></i></div></div><span class="tag">${esc(c.level)}</span>
        <span class="muted">${done}/${c.lessons.length}</span></a>`;
    }).join('') + `</div>`).join('') || `<p class="muted">${t('empty')}</p>`;
  };
  v(`<h1>${t('courses')}</h1><input class="search" type="search" id="cq" placeholder="${t('search_courses')}" aria-label="${t('search_courses')}"><div id="clist">${draw('')}</div>`);
  $('#cq').oninput = e => { $('#clist').innerHTML = draw(e.target.value.trim()); };
}

async function course(id) {
  const c = (await api('courses')).find(x => x.id == id);
  if (!c) return location.hash = '#/courses';
  v(`<a class="muted" href="#/courses">← ${t('courses')}</a><h1 style="margin-top:6px">${esc(c.title)} <span class="tag">${esc(c.level)}</span></h1><p class="muted" style="margin-bottom:12px">${esc(c.descr)}</p>
    <div class="list">` + (c.lessons.map((l, i) => `<a class="row" href="#/lesson/${l.id}"><i class="bx ${l.open ? 'bx-lock-open-alt ok' : 'bx-lock-alt lock'}"></i>
      <div class="grow"><b>${i + 1}. ${esc(l.title)}</b></div>${l.zoom ? '<i class="bx bx-video"></i>' : ''}${l.done ? '<span class="tag ok">✓</span>' : ''}</a>`).join('') || `<div class="row muted">${t('empty')}</div>`) + `</div>`);
}

async function lesson(id) {
  const [l, me] = await Promise.all([api('lessons/' + id), api('me')]); ME = me;
  const head = `<a class="muted" href="#/course/${l.course_id}">← ${esc(l.course)}</a><h1 style="margin-top:6px">${esc(l.title)}</h1>`;
  if (!l.access) {
    return v(head + `<div class="box"><p><i class="bx bx-lock-alt"></i> ${t('locked_t')}</p>` +
      (me.free_left > 0 ? `<p class="muted" style="margin:8px 0">🎁 ${t('free_note')} (${t('free_left')}: ${me.free_left})</p><button class="btn block" data-a="unlock" data-id="${id}">${t('unlock_free')}</button>`
        : (l.price != null ? `<button class="btn block" style="margin-top:10px" data-a="unlock" data-id="${id}">${t('unlock_pay')} — ${money(l.price, me.currency)}</button>` : '')) +
      `<p class="muted" style="margin:14px 0 8px">${t('or_sub')}</p><a class="btn ghost block" href="#/wallet">${t('to_plans')}</a></div>`);
  }
  localStorage.last = JSON.stringify({ id, title: l.title });
  v(head +
    (l.zoom_url ? `<div class="box"><b>${esc(l.starts_at)}</b><div class="gap" style="margin-top:8px"><a class="btn" target="_blank" rel="noopener" href="${safeUrl(l.zoom_url)}"><i class="bx bx-video"></i> ${t('join')}</a></div></div>` : '') +
    `<div class="box content">${esc(l.content)}</div>` +
    ((l.video_url || l.recording_url) ? `<div class="gap">${l.video_url ? `<a class="btn ghost sm" target="_blank" rel="noopener" href="${safeUrl(l.video_url)}">▶ ${t('video')}</a>` : ''}${l.recording_url ? `<a class="btn ghost sm" target="_blank" rel="noopener" href="${safeUrl(l.recording_url)}">⏺ ${t('record')}</a>` : ''}</div>` : '') +
    (l.homework ? `<h2>${t('homework')}</h2><div class="box content">${esc(l.homework)}</div>` : '') +
    (l.quiz.length ? `<h2>${t('quiz')}</h2><div class="box" id="quiz">` + l.quiz.map((x, i) => `<fieldset><legend>${i + 1}. ${esc(x.q)}</legend>` +
      x.opts.map((o, j) => `<label><input type="radio" name="q${i}" value="${j}">${esc(o)}</label>`).join('') + `</fieldset>`).join('') +
      `<button class="btn" data-a="quiz" data-id="${id}" style="margin-top:8px">${t('check')}</button><p id="qres" class="muted" style="margin-top:8px">${l.best ? t('best') + ': ' + l.best[0] + '/' + l.best[1] : ''}</p></div>` : '') + lessonNav(l));
}

const lessonNav = l => `<div class="gap" style="margin-top:16px;justify-content:space-between">${l.prev ? `<a class="btn ghost sm" href="#/lesson/${l.prev}">← ${t('prev')}</a>` : '<span></span>'}${l.next ? `<a class="btn sm" href="#/lesson/${l.next}">${t('next')} →</a>` : ''}</div>`;

async function live() {
  const r = await api('live'); ME = await api('me');
  const now = r.live.filter(x => x.status === 'live'), up = r.live.filter(x => x.status === 'scheduled'), end = r.live.filter(x => x.status === 'ended');
  const grid = a => `<div class="cg2">${a.map(l => liveCard(l, r)).join('')}</div>`;
  v(`<h1>${t('live')}</h1>` + (now.length ? `<h2>🔴 ${t('ls_live')}</h2>${grid(now)}` : '') + `<h2>${t('upcoming')}</h2>` + (up.length ? grid(up) : `<p class="muted">${t('no_live')}</p>`) +
    (end.length ? `<h2>${t('ls_ended')}</h2>${grid(end)}` : '') + `<h2>${t('recordings')}</h2>` + (r.recordings.length ? `<div class="list">` + r.recordings.map(x => `<div class="row"><i class="bx bx-play-circle ${x.open ? 'ok' : 'lock'}"></i>
      <div class="grow"><b>${esc(x.title)}</b><span class="muted">${esc(x.course || '')}</span></div>` +
      (x.open ? `<a class="btn sm" target="_blank" rel="noopener" href="${safeUrl(x.url)}">${t('record')}</a>` : `<span class="tag warn">${t('sub_free')}</span>`) + `</div>`).join('') + `</div>` : `<p class="muted">${t('no_recs')}</p>`));
}

async function wallet() {
  const [me, w, p] = await Promise.all([api('me'), api('wallet'), api('prices')]); ME = me;
  const c = me.currency, pr = p.prices;
  v(`<h1>${t('wallet')}</h1><div class="seg" aria-label="${t('currency')}">${['UZS', 'USD', 'KZT'].map(k => `<button data-a="cur" data-c="${k}" class="${k === c ? 'on' : ''}">${k}</button>`).join('')}</div>
    <div class="hero"><p>${t('balance')}</p><h1>${money(me.bal[c], c)}</h1><div class="chips">${Object.entries(me.bal).filter(([k]) => k !== c).map(([k, a]) => `<span class="chip">${money(a, k)}</span>`).join('')}</div></div>
    <h2>${t('plans')}</h2><div class="list">` +
    ['m1', 'm3', 'm6', 'y1'].map(k => pr[k] && pr[k][c] != null ? `<div class="row"><div class="grow"><b>${t('p_' + k)}</b></div><b>${money(pr[k][c], c)}</b><button class="btn sm" data-a="buy" data-p="${k}">${t('buy')}</button></div>` : '').join('') +
    `<div class="row"><div class="grow"><b>${t('per_lesson')}</b></div><b>${pr.lesson && pr.lesson[c] != null ? money(pr.lesson[c], c) : '—'}</b></div></div>` +
    (me.sub ? `<p class="muted" style="margin-top:8px">${t('sub_till')} ${me.sub.ends.slice(0, 16)}</p>` : '') +
    `<h2>${t('topup')}</h2><div class="box"><p class="muted" style="white-space:pre-wrap">${esc(p.pay_info)}</p>
    <label class="f">${t('amount')} (${c})</label><input id="tu-amt" type="number" min="1" inputmode="decimal"><label class="f">${t('note')}</label><input id="tu-note" maxlength="150">
    <button class="btn block" data-a="topup">${t('send')}</button>` +
    (w.topups.length ? `<div style="margin-top:12px">` + w.topups.map(x => `<div class="gap muted" style="margin:4px 0"><span>#${x.id} ${money(x.amount, x.cur)}</span><span class="tag ${x.status === 'approved' ? 'ok' : x.status === 'rejected' ? 'bad' : 'warn'}">${t(x.status)}</span></div>`).join('') + `</div>` : '') + `</div>
    <h2>${t('history')}</h2>` + (w.tx.length ? `<div class="list">` + w.tx.map(x => `<div class="row"><div class="grow"><b>${esc(x.reason)}</b><span class="muted">${esc(x.ts.slice(0, 16))}</span></div>
      <b style="color:${x.delta < 0 ? 'var(--bad)' : 'var(--ok)'}">${x.delta > 0 ? '+' : ''}${money(x.delta, x.cur)}</b></div>`).join('') + `</div>` : `<p class="muted">${t('empty')}</p>`) +
    `<p class="muted" style="margin-top:14px">${t('support')}: ${esc(p.support)}</p>`);
}

async function profileView() {
  v('<div id="pf"></div>');
  await renderProfile($('#pf'), {
    onLogout: doLogout, onLang: async () => { ME = await api('me'); route(); },
    onUser: u => { ME = u; chrome('profile'); },
  });
}
async function doLogout() { try { await api('logout', { method: 'POST' }); } catch (e) { } localStorage.removeItem('token'); location.href = '/'; }
window.onTheme = th => api('me', { method: 'PATCH', body: { theme: th } }).catch(() => { });

async function board() {
  const r = await api('leaderboard');
  v(`<h1>${t('top')}</h1>` + (r.length ? `<div class="list">` + r.map((x, i) => `<div class="row"><b style="width:28px">${i + 1}</b><div class="grow"><b>${esc(x.username)}${x.username === ME.username ? ' ★' : ''}</b></div><span class="tag">${x.pts} ${t('pts')}</span></div>`).join('') + `</div>` : `<p class="muted">${t('empty')}</p>`));
}

// ------------------------------------------------------------ действия
const A = {
  async join(d) {
    const w = window.open('', '_blank');
    try { const r = await api(`live/${d.id}/join`, { method: 'POST' }); if (w) w.location.href = r.url; else location.href = r.url; }
    catch (e) { if (w) w.close(); throw e; }
  },
  async seat(d) { await api(`live/${d.id}/seat`, { method: 'POST' }); toast(t('seat_ok')); route(); },
  cal(d) {
    const l = LIVE[d.id], st = new Date(l.starts_at.replace(' ', 'T') + ':00'), en = new Date(+st + l.duration * 6e4);
    const f = x => `${x.getFullYear()}${pad(x.getMonth() + 1)}${pad(x.getDate())}T${pad(x.getHours())}${pad(x.getMinutes())}00`;
    const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Max English Academy//EN', 'BEGIN:VEVENT', `UID:live-${l.id}@maxenglish`, `DTSTAMP:${f(new Date())}`, `DTSTART:${f(st)}`, `DTEND:${f(en)}`,
      `SUMMARY:${l.title.replace(/[,;\n]/g, ' ')}`, `DESCRIPTION:${(l.teacher || '').replace(/[,;\n]/g, ' ')}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar' })); a.download = 'lesson.ics'; a.click();
  },
  async unlock(d) { await api(`lessons/${d.id}/unlock`, { method: 'POST' }); toast(t('bought')); route(); },
  async cur(d) { await api('me', { method: 'PATCH', body: { currency: d.c } }); route(); },
  async buy(d) {
    if (!confirm(t('p_' + d.p) + ' — ' + money(((await api('prices')).prices[d.p] || {})[ME.currency], ME.currency) + '?')) return;
    await api('subscribe', { method: 'POST', body: { plan: d.p } }); toast(t('subbed')); route();
  },
  async topup() {
    await api('topup', { method: 'POST', body: { amount: $('#tu-amt').value, currency: ME.currency, note: $('#tu-note').value } });
    toast(t('sent')); route();
  },
  async linkcode() {
    const r = await api('linkcode', { method: 'POST' });
    $('#lc').innerHTML = `${t('link_hint')}${r.bot ? ' @' + esc(r.bot) : ''}: <b>/link ${esc(r.code)}</b> (10 min)`;
  },
  async quiz(d) {
    const fs = document.querySelectorAll('#quiz fieldset');
    const answers = [...fs].map((_, i) => { const c = document.querySelector(`input[name=q${i}]:checked`); return c ? +c.value : -1; });
    const r = await api(`lessons/${d.id}/quiz`, { method: 'POST', body: { answers } });
    fs.forEach((f, i) => f.querySelectorAll('label').forEach((lb, j) => { lb.classList.toggle('ok', j === r.correct[i]); lb.classList.toggle('bad', answers[i] === j && j !== r.correct[i]); }));
    $('#qres').textContent = `${t('score')}: ${r.score}/${r.total} (+${r.score * 10} ${t('pts')})`;
  },
};
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-a]'); if (!b || !A[b.dataset.a]) return;
  b.disabled = true;
  try { await A[b.dataset.a](b.dataset); } catch (err) { if (err && err.error) fail(err); else console.error(err); }
  b.disabled = false;
});

// ------------------------------------------------------------ роутер
const VIEWS = { home, courses, course, lesson, live, wallet, top: board, profile: profileView };
async function route() {
  const [, name = 'home', id] = location.hash.split('/');
  try {
    if (!ME) { ME = await api('me'); setLang(ME.lang); if (ME.theme && ME.theme !== Theme.get()) Theme.set(ME.theme, false); }
    chrome(name in VIEWS ? name : 'home');
    v('<p class="muted">…</p>');
    await (VIEWS[name] || home)(id);
  } catch (e) { if (e && e.error) { fail(e); v(''); } else console.error(e); }
  window.scrollTo(0, 0);
}
addEventListener('hashchange', route);
route();
