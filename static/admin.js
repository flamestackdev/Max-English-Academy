const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const v = h => $('#v').innerHTML = h;
const CUR = ['UZS', 'USD', 'KZT'];
const PLANS = ['lesson', 'm1', 'm3', 'm6', 'y1'];
const CATS = ['grammar', 'listening', 'reading', 'speaking', 'writing', 'vocabulary'];
let ME = null, TAB = 'dash', CACHE = {};

async function api(p, o = {}) {
  const r = await fetch('/api/' + p, {
    method: o.method || 'GET', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.token },
    body: o.body ? JSON.stringify(o.body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { localStorage.removeItem('token'); showLogin(); throw d; }
  if (!r.ok) throw d;
  return d;
}
function toast(m, bad) {
  const e = $('#toast'); e.textContent = m; e.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => e.className = '', 3400);
}
const fail = e => toast(e && D['e_' + e.error] ? t('e_' + e.error) : (e && e.error) || t('e_x'), 1);
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { if (e && e.error) fail(e); else console.error(e); } };
const fmt = (a, c) => (c === 'USD' ? '$' : '') + (+a).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + (c === 'USD' ? '' : ' ' + c);
const tbl = (heads, rows) => `<div class="scroll"><table><tr>${heads.map(h => `<th>${h}</th>`).join('')}</tr>${rows.join('') || `<tr><td colspan="${heads.length}" class="muted">${t('a_empty')}</td></tr>`}</table></div>`;
const dlg = $('#dlg');
dlg.onclick = e => { if (e.target === dlg) dlg.close(); };
const openDlg = h => { dlg.innerHTML = h; if (!dlg.open) dlg.showModal(); };
const download = async (path, name) => {
  const r = await fetch('/api/' + path, { headers: { Authorization: 'Bearer ' + localStorage.token } });
  if (!r.ok) throw await r.json();
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click();
};
const roleName = r => t('role_' + r);
const fld = (id, label, inner) => `<label class="f" for="${id}">${label}</label>${inner}`;

// ------------------------------------------------------------ вход и загрузка
function showLogin(msg) {
  $('#panel').hidden = true; $('#login').hidden = false; applyI18n();
  if (msg) toast(msg, 1);
}
$('#lf').onsubmit = async e => {
  e.preventDefault();
  try {
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: $('#lu').value, password: $('#lp').value }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw d;
    if (!['admin', 'teacher'].includes(d.user.role)) return toast(t('a_need_staff'), 1);
    localStorage.token = d.token; await syncPickedLang(d.token, d.user.lang); boot();
  } catch (err) { fail(err); }
};
async function logoutNow() { try { await api('logout', { method: 'POST' }); } catch (e) { } localStorage.removeItem('token'); location.reload(); }
window.onTheme = th => { if (localStorage.token) api('me', { method: 'PATCH', body: { theme: th } }).catch(() => { }); };

function setHeader() {
  $('#ptitle').textContent = t(ME.role === 'admin' ? 'a_panel' : 'a_panel_t'); $('#hav').textContent = initials(ME); applyI18n();
}
async function boot() {
  if (!localStorage.token) return showLogin();
  try { ME = await api('me'); } catch (e) { return; }
  if (!['admin', 'teacher'].includes(ME.role)) return showLogin(t('a_need_staff'));
  if (ME.theme && ME.theme !== Theme.get()) Theme.set(ME.theme, false);
  if (LANGS.includes(ME.lang)) setLang(ME.lang);
  $('#login').hidden = true; $('#panel').hidden = false; setHeader();
  go(ME.role === 'admin' ? 'dash' : 'live');
}
function go(k) {
  TAB = k;
  const all = [['dash', 'a_dash'], ['live', ME.role === 'admin' ? 'a_live_all' : 'a_live_my'], ['users', 'a_users'], ['topups', 'a_topups'], ['prices', 'a_prices'],
    ['content', 'a_content'], ['logs', 'a_logs'], ['tx', 'a_tx'], ['tools', 'a_tools'], ['profile', 'a_profile']];
  const tabs = ME.role === 'admin' ? all : all.filter(x => ['live', 'content', 'profile'].includes(x[0]));
  $('#tabs').innerHTML = tabs.map(([id, key]) => `<button class="${id === k ? 'on' : ''}" onclick="go('${id}')">${t(key)}</button>`).join('');
  v('<p class="muted">…</p>');
  guard(VIEWS[k])();
}

// ------------------------------------------------------------ обзор
async function dash() {
  const s = await api('admin/stats');
  const mx = Math.max(1, ...s.signups.map(x => x.c));
  const rev = Object.entries(s.revenue).map(([c, a]) => fmt(a, c)).join(' · ') || '—';
  v(`<h1>${t('a_dash')}</h1><div class="list">
    <div class="stat"><span>${t('a_st_users')}</span><b>${s.users} (+${s.new7} ${t('a_last7')})</b></div>
    <div class="stat"><span>${t('a_st_subs')}</span><b>${s.subs}</b></div>
    <div class="stat"><span>${t('a_st_pending')}</span><b>${s.pending}</b></div>
    <div class="stat"><span>${t('a_st_live')}</span><b>${s.live_now} / ${s.live_up}</b></div>
    <div class="stat"><span>${t('a_st_teachers')}</span><b>${s.teachers}</b></div>
    <div class="stat"><span>${t('a_st_tg')}</span><b>${s.tg}</b></div>
    <div class="stat"><span>${t('a_st_lessons')}</span><b>${s.lessons}</b></div>
    <div class="stat"><span>${t('a_st_rev')}</span><b>${rev}</b></div></div>
    <h2>${t('a_signups')}</h2><div class="box"><div class="spark" role="img" aria-label="${t('a_signups')}">${s.signups.map(x => `<i title="${x.d}: ${x.c}" style="height:${Math.max(5, x.c / mx * 100)}%"></i>`).join('')}</div>
    <p class="muted" style="margin-top:6px">${t('a_total_period')}: ${s.signups.reduce((a, x) => a + x.c, 0)} · ${s.signups[0].d} — ${s.signups[13].d}</p></div>`);
}

// ------------------------------------------------------------ онлайн-уроки (учитель: свои, админ: все)
const stTag = st => `<span class="tag ${st === 'live' ? 'bad' : st === 'ended' ? '' : st === 'cancelled' ? 'warn' : 'ok'}">${st === 'live' ? '● ' : ''}${t('ls_' + st)}</span>`;
async function live(st = '') {
  const [r, courses] = await Promise.all([api('tlive' + (st ? '?status=' + st : '')), api('staff/courses')]);
  CACHE.live = r.rows; CACHE.meta = r; CACHE.courses = courses; CACHE.lst = st;
  const cnt = k => r.rows.filter(x => x.status === k).length;
  const seg = [['', 'a_all'], ['scheduled', 'ls_scheduled'], ['live', 'ls_live'], ['ended', 'ls_ended'], ['cancelled', 'ls_cancelled']];
  v(`<h1>${t(ME.role === 'admin' ? 'a_live_all' : 'a_live_my')}</h1><p class="muted" style="margin-bottom:10px">${t(ME.role === 'admin' ? 'a_live_hint_admin' : 'a_live_hint_teacher')}</p>
    <div class="gap">${r.can_create ? `<button class="btn sm" onclick="liveForm(0)">${t('a_new_live')}</button>` : ''}</div>
    <div class="seg">${seg.map(([k, key]) => `<button class="${k === st ? 'on' : ''}" onclick="guard(live)('${k}')">${t(key)}</button>`).join('')}</div>
    <div class="cg2">` + (r.rows.map(l => `<div class="box lv${l.status === 'live' ? ' now' : ''}" style="margin:0">
      <div class="gap" style="justify-content:space-between"><b>${esc(l.title)}</b>${stTag(l.status)}</div>
      <p class="muted">🗓 ${t('lv_planned')}: ${esc(l.starts_at)} · ${l.duration} ${t('min')}${l.course ? ' · ' + esc(l.course) : ''}</p>
      ${ME.role === 'admin' ? `<p class="muted">👩‍🏫 ${t('lv_teacher')}: ${esc(l.full_name || l.username)}</p>` : ''}
      <p class="muted">▶ ${t('lv_started')}: <b>${esc(l.started_at ? l.started_at.slice(0, 16) : '—')}</b> · ⏹ ${t('lv_ended')}: <b>${esc(l.status === 'ended' && l.ended_at ? l.ended_at.slice(0, 16) : '—')}</b></p>
      <p class="muted">👥 ${t('lv_joined')}: <b>${l.joined}</b> · 🎫 ${t('lv_seats')}: <b>${l.seats}</b> · ${l.zoom_url ? `<a href="${esc(l.zoom_url)}" target="_blank" rel="noopener">Zoom</a>` : `<span class="tag warn">${t('lv_no_link')}</span>`}</p>
      <div class="gap" style="margin-top:10px">
        ${l.status === 'scheduled' ? `<button class="btn sm" onclick="guard(liveAct)(${l.id},'start')">${t('lv_start')}</button>` : ''}
        ${l.status === 'live' ? `<button class="btn sm" onclick="guard(liveAct)(${l.id},'end')">${t('lv_end')}</button>` : ''}
        ${['scheduled', 'live'].includes(l.status) ? `<button class="btn sm ghost red" onclick="guard(liveAct)(${l.id},'cancel')">${t('lv_cancel')}</button>` : ''}
        <button class="btn sm ghost" onclick="guard(liveAtt)(${l.id})">${t('lv_attendees')}</button>
        <button class="btn sm ghost" onclick="liveForm(${l.id})">${t('a_edit')}</button>
        <button class="btn sm ghost red" onclick="guard(liveAct)(${l.id},'delete')">${t('a_delete')}</button></div></div>`).join('') || `<p class="muted">${t('a_empty')}</p>`) + `</div>`);
}
function liveForm(id) {
  const l = CACHE.live.find(x => x.id === id) || { duration: 60, course_id: 0 };
  const dtv = (l.starts_at || '').replace(' ', 'T');
  openDlg(`<h2 style="margin-top:0">${t(id ? 'a_edit_live_t' : 'a_new_live_t')}</h2>
    ${fld('lv-title', t('lv_title'), `<input id="lv-title" maxlength="120" value="${esc(l.title || '')}">`)}
    ${fld('lv-descr', t('lv_descr'), `<textarea id="lv-descr" style="min-height:60px">${esc(l.descr || '')}</textarea>`)}
    ${fld('lv-course', t('lv_course'), `<select id="lv-course"><option value="0">—</option>${CACHE.courses.map(c => `<option value="${c.id}" ${c.id === l.course_id ? 'selected' : ''}>${esc(c.title)}</option>`).join('')}</select>`)}
    <div class="grid2"><div>${fld('lv-when', t('lv_when'), `<input id="lv-when" type="datetime-local" value="${esc(dtv)}">`)}</div><div>${fld('lv-dur', t('lv_dur'), `<input id="lv-dur" type="number" min="10" max="300" value="${l.duration}">`)}</div></div>
    ${fld('lv-zoom', t('lv_zoom'), `<input id="lv-zoom" type="url" placeholder="https://zoom.us/j/..." value="${esc(l.zoom_url || '')}">`)}
    ${CACHE.meta.can_create ? `<button class="btn ghost sm" style="margin:2px 0 8px" onclick="guard(makeZoom)()">${t('lv_zoom_api')}</button>` : ''}
    ${fld('lv-rec', t('lv_rec'), `<input id="lv-rec" type="url" value="${esc(l.recording_url || '')}">`)}
    <p class="muted" style="margin:6px 0">${t('a_live_hint_teacher')}</p>
    <div class="gap" style="margin-top:10px"><button class="btn" onclick="guard(saveLive)(${id})">${t('save')}</button><button class="btn ghost" onclick="dlg.close()">${t('a_close')}</button></div>`);
}
async function saveLive(id) {
  const body = { title: $('#lv-title').value, descr: $('#lv-descr').value, course_id: +$('#lv-course').value, starts_at: $('#lv-when').value.replace('T', ' '), duration: +$('#lv-dur').value, zoom_url: $('#lv-zoom').value, recording_url: $('#lv-rec').value };
  if (id) body.id = id;
  await api('tlive', { method: 'POST', body }); dlg.close(); toast(t(id ? 'saved' : 'lv_created')); live(CACHE.lst);
}
async function makeZoom() {
  const r = await api('tlive/zoom', { method: 'POST', body: { topic: $('#lv-title').value, start: $('#lv-when').value, duration: +$('#lv-dur').value } });
  $('#lv-zoom').value = r.url; toast(t('lv_zoom_ok'));
}
async function liveAct(id, action) {
  const conf = { cancel: 'lv_confirm_cancel', end: 'lv_confirm_end', delete: 'a_confirm_del' }[action];
  if (conf && !confirm(t(conf))) return;
  await api(`tlive/${id}/action`, { method: 'POST', body: { action } }); toast(t('done')); live(CACHE.lst);
}
async function liveAtt(id) {
  const r = await api(`tlive/${id}/attendees`), l = CACHE.live.find(x => x.id === id);
  openDlg(`<h2 style="margin-top:0">${t('lv_attendance_h')}</h2><p class="muted" style="margin-bottom:8px">${esc(l.title)} · ${t('lv_started')}: ${esc(l.started_at ? l.started_at.slice(0, 16) : '—')}</p>` +
    (r.length ? tbl(['#', t('username'), t('lv_first'), '×'], r.map((a, i) => `<tr><td>${i + 1}</td><td>${esc(a.full_name || a.username)}</td><td>${esc(a.first.slice(0, 16))}</td><td>${a.n}</td></tr>`)) : `<p class="muted">${t('lv_none')}</p>`) +
    `<button class="btn ghost block" style="margin-top:12px" onclick="dlg.close()">${t('a_close')}</button>`);
}
setInterval(() => { if (TAB === 'live' && !dlg.open && !document.hidden && ME) guard(live)(CACHE.lst || ''); }, 30000);

// ------------------------------------------------------------ пользователи
async function users(q = '') {
  const r = await api('admin/users?q=' + encodeURIComponent(q)); CACHE.users = r;
  v(`<h1>${t('a_users')}</h1><button class="btn ghost sm" style="margin-bottom:10px" onclick="guard(download)('admin/users.csv','users.csv')">${t('a_csv')}</button>
    <input id="uq" placeholder="${t('a_search_users')}" value="${esc(q)}" onkeydown="if(event.key==='Enter')guard(users)(this.value)">
    <div class="list">` + r.map(u => `<div class="row" onclick="userDlg(${u.id})"><div class="grow"><b>${esc(u.username)} <span class="tag ${u.role === 'admin' ? 'bad' : u.role === 'teacher' ? 'ok' : ''}">${roleName(u.role)}</span> ${u.blocked ? `<span class="tag bad">${t('a_blocked')}</span>` : ''}</b>
      <span class="muted">${esc(u.email || '—')}${u.tg_id ? ' · TG ' + u.tg_id : ''} · ${u.lang.toUpperCase()}</span></div>
      <span class="muted right">${CUR.map(c => u.bal[c] ? fmt(u.bal[c], c) : '').filter(Boolean).join('<br>') || '0'}${u.sub ? `<br><span class="tag ok">${t('a_until')} ${u.sub.slice(0, 10)}</span>` : ''}</span></div>`).join('') + `</div>`);
}
function userDlg(id) {
  const u = CACHE.users.find(x => x.id === id); if (!u) return;
  openDlg(`<h2 style="margin-top:0">${esc(u.username)}</h2><p class="muted">${esc(u.email || '—')} · ${u.lang.toUpperCase()} · TG: ${u.tg_id || '—'} · ${esc(u.created.slice(0, 10))} · ${t('a_free_used')}: ${u.free_used}</p>
    <div class="gap" style="margin:8px 0">${CUR.map(c => `<span class="tag">${fmt(u.bal[c], c)}</span>`).join('')}${u.sub ? `<span class="tag ok">${t('a_until')} ${u.sub.slice(0, 16)}</span>` : ''}</div>
    <h2>${t('a_bal_h')}</h2><div class="grid2"><select id="b-cur">${CUR.map(c => `<option>${c}</option>`).join('')}</select>
      <select id="b-mode"><option value="add">${t('a_add')}</option><option value="sub">${t('a_sub')}</option><option value="set">${t('a_set')}</option></select></div>
    <input id="b-amt" type="number" min="0" step="any" placeholder="${t('a_amount_ph')}" inputmode="decimal"><input id="b-reason" placeholder="${t('a_reason')}">
    <button class="btn block" onclick="guard(doBalance)(${id})">${t('a_apply')}</button>
    <h2>${t('a_grant_h')}</h2><div class="grid2"><select id="g-plan">${['m1', 'm3', 'm6', 'y1'].map(p => `<option value="${p}">${t('p_' + p)}</option>`).join('')}</select><button class="btn" onclick="guard(doGrant)(${id})">${t('a_grant_btn')}</button></div>
    <h2>${t('a_acc_h')}</h2><div class="grid2"><select id="u-role">${['student', 'teacher', 'admin'].map(r => `<option value="${r}" ${u.role === r ? 'selected' : ''}>${roleName(r)}</option>`).join('')}</select><button class="btn ghost" onclick="guard(doPatch)(${id},'role')">${t('a_role_btn')}</button></div>
    <p class="muted" style="margin:-4px 0 10px">${t('a_role_hint')}</p>
    <div class="grid2"><input id="u-pw" type="text" placeholder="${t('a_newpw_ph')}"><button class="btn ghost" onclick="guard(doPatch)(${id},'password')">${t('a_reset_pw')}</button></div>
    <div class="grid2"><input id="u-free" type="number" min="0" value="${u.free_used}"><button class="btn ghost" onclick="guard(doPatch)(${id},'free_used')">${t('a_free_btn')}</button></div>
    <button class="btn ${u.blocked ? '' : 'red'} block" style="margin-top:8px" onclick="guard(doPatch)(${id},'blocked')">${u.blocked ? t('a_unblock') : t('a_block')}</button>
    <button class="btn ghost block" style="margin-top:8px" onclick="dlg.close()">${t('a_close')}</button>`);
}
async function refreshUser(id) { await users($('#uq') ? $('#uq').value : ''); userDlg(id); }
async function doBalance(id) {
  const r = await api(`admin/users/${id}/balance`, { method: 'POST', body: { cur: $('#b-cur').value, mode: $('#b-mode').value, amount: $('#b-amt').value, reason: $('#b-reason').value } });
  toast(t('balance') + ': ' + fmt(r.balance, $('#b-cur').value)); refreshUser(id);
}
async function doGrant(id) { const r = await api(`admin/users/${id}/grant`, { method: 'POST', body: { plan: $('#g-plan').value } }); toast(t('sub_till') + ' ' + r.ends.slice(0, 10)); refreshUser(id); }
async function doPatch(id, what) {
  const u = CACHE.users.find(x => x.id === id);
  const body = what === 'role' ? { role: $('#u-role').value } : what === 'password' ? { password: $('#u-pw').value } : what === 'free_used' ? { free_used: $('#u-free').value } : { blocked: !u.blocked };
  await api('admin/users/' + id, { method: 'PATCH', body }); toast(t('saved')); refreshUser(id);
}

// ------------------------------------------------------------ пополнения и цены
async function topups(st = 'pending') {
  const r = await api('admin/topups?status=' + st);
  v(`<h1>${t('a_topups_h')}</h1><div class="seg"><button class="${st === 'pending' ? 'on' : ''}" onclick="guard(topups)('pending')">${t('a_pending')}</button><button class="${st === '' ? 'on' : ''}" onclick="guard(topups)('')">${t('a_all')}</button></div>` +
    tbl(['#', t('a_who'), t('a_sum'), t('a_comment'), t('a_date'), ''], r.map(x => `<tr><td>${x.id}</td><td>${esc(x.username)}</td><td><b>${fmt(x.amount, x.cur)}</b></td><td>${esc(x.note)}</td><td>${esc(x.created.slice(0, 16))}</td>
      <td>${x.status === 'pending' ? `<button class="btn sm" onclick="guard(doTopup)(${x.id},'approve','${st}')">${t('a_credit')}</button> <button class="btn sm red" onclick="guard(doTopup)(${x.id},'reject','${st}')">${t('a_reject')}</button>` : `<span class="tag ${x.status === 'approved' ? 'ok' : 'bad'}">${t(x.status)}</span> <span class="muted">${esc(x.handled_by || '')}</span>`}</td></tr>`)));
}
async function doTopup(id, action, st) { await api('admin/topups/' + id, { method: 'POST', body: { action } }); toast(t('done')); topups(st); }
async function prices() {
  const p = await api('admin/prices');
  v(`<h1>${t('a_prices_h')}</h1><p class="muted" style="margin-bottom:10px">${t('a_prices_hint')}</p>` +
    tbl([t('a_plan'), ...CUR], PLANS.map(k => `<tr><td><b>${t('p_' + k)}</b></td>${CUR.map(c => `<td><input style="margin:0;min-width:110px" type="number" min="0" step="any" id="p-${k}-${c}" value="${(p[k] || {})[c] ?? ''}"></td>`).join('')}</tr>`)) +
    `<button class="btn block" style="margin-top:12px" onclick="guard(savePrices)()">${t('a_prices_save')}</button>`);
}
async function savePrices() {
  const body = {}; PLANS.forEach(k => { body[k] = {}; CUR.forEach(c => { const val = $(`#p-${k}-${c}`).value; if (val !== '') body[k][c] = val; }); });
  await api('admin/prices', { method: 'PUT', body }); toast(t('a_prices_saved'));
}

// ------------------------------------------------------------ контент (курсы, уроки, объявления, слова)
const ENT = () => ({
  courses: { n: 'a_e_courses', f: [['cat', 'f_cat', 'cat'], ['title', 'f_title'], ['level', 'f_level'], ['descr', 'f_descr', 'ta'], ['position', 'f_pos', 'num']], row: r => `${r.title} · ${r.level} · ${r.cat}` },
  lessons: { n: 'a_e_lessons', f: [['course_id', 'f_course', 'course'], ['title', 'f_title'], ['content_ru', 'f_content', 'ta', 'RU'], ['content_en', 'f_content', 'ta', 'EN'], ['content_uz', 'f_content', 'ta', 'UZ'], ['content_qq', 'f_content', 'ta', 'QQ'],
    ['video_url', 'f_video'], ['homework', 'f_hw', 'ta'], ['quiz', 'f_quiz', 'ta'], ['position', 'f_pos', 'num']], row: r => `${(CACHE.courses.find(c => c.id === r.course_id) || {}).title || '?'} → ${r.title}` },
  announcements: { n: 'a_e_ann', f: [['title', 'f_title'], ['body', 'f_body', 'ta'], ['push', 'f_push', 'chk']], row: r => `${r.title} · ${r.ts.slice(0, 10)}` },
  words: { n: 'a_e_words', f: [['en', 'English'], ['ru', 'Русский'], ['uz', "O'zbekcha"], ['qq', 'Qaraqalpaqsha']], row: r => `${r.en} — ${r.ru} / ${r.uz} / ${r.qq || ''}` },
});
async function content(tn = 'lessons') {
  CACHE.courses = await api('staff/courses'); CACHE.rows = await api('staff/' + tn); CACHE.t = tn;
  const E = ENT();
  v(`<h1>${t('a_content_h')}</h1><div class="seg">${Object.entries(E).map(([k, e]) => `<button class="${k === tn ? 'on' : ''}" onclick="guard(content)('${k}')">${t(e.n)}</button>`).join('')}</div>
    <button class="btn sm" onclick="editRow(0)">${t('a_add_btn')}</button><div class="list" style="margin-top:12px">` +
    (CACHE.rows.map(r => `<div class="row" onclick="editRow(${r.id})"><div class="grow"><b>${esc(E[tn].row(r))}</b></div><span class="muted">›</span></div>`).join('') || `<div class="row muted">${t('a_empty')}</div>`) + `</div>`);
}
function editRow(id) {
  const tn = CACHE.t, E = ENT()[tn], r = CACHE.rows.find(x => x.id === id) || {};
  const field = ([k, key, type, tag]) => {
    const val = r[k] ?? '', label = (D[key] ? t(key) : key) + (tag ? ' (' + tag + ')' : ''), lab = `<label class="f" for="f-${k}">${esc(label)}</label>`;
    if (type === 'ta') return lab + `<textarea id="f-${k}">${esc(val)}</textarea>`;
    if (type === 'num') return lab + `<input id="f-${k}" type="number" value="${esc(val || 0)}">`;
    if (type === 'chk') return `<label class="f"><input type="checkbox" id="f-${k}"> ${esc(label)}</label>`;
    if (type === 'cat') return lab + `<input id="f-${k}" list="cats" value="${esc(val)}"><datalist id="cats">${CATS.map(c => `<option>${c}</option>`).join('')}</datalist>`;
    if (type === 'course') return lab + `<select id="f-${k}">${CACHE.courses.map(c => `<option value="${c.id}" ${c.id === r.course_id ? 'selected' : ''}>${esc(c.title)}</option>`).join('')}</select>`;
    return lab + `<input id="f-${k}" value="${esc(val)}">`;
  };
  openDlg(`<h2 style="margin-top:0">${t(id ? 'a_edit' : 'a_add_t')}: ${t(E.n)}</h2>` + E.f.map(field).join('') +
    `<div class="gap" style="margin-top:12px"><button class="btn" onclick="guard(saveRow)(${id})">${t('save')}</button>${id && !(tn === 'courses' && ME.role !== 'admin') ? `<button class="btn red" onclick="guard(delRow)(${id})">${t('a_delete')}</button>` : ''}<button class="btn ghost" onclick="dlg.close()">${t('a_close')}</button></div>`);
}
async function saveRow(id) {
  const body = id ? { id } : {};
  ENT()[CACHE.t].f.forEach(([k, , type]) => { const el = $('#f-' + k); body[k] = type === 'chk' ? el.checked : el.value; });
  await api('staff/' + CACHE.t, { method: 'POST', body }); dlg.close(); toast(t('saved')); content(CACHE.t);
}
async function delRow(id) {
  if (!confirm(t('a_confirm_del'))) return;
  await api(`staff/${CACHE.t}/${id}`, { method: 'DELETE' }); dlg.close(); content(CACHE.t);
}

// ------------------------------------------------------------ логи и транзакции
async function logs(q = '', off = 0) {
  const r = await api(`admin/logs?q=${encodeURIComponent(q)}&offset=${off}`);
  v(`<h1>${t('a_logs_h')}</h1><input id="lq" placeholder="${t('a_logs_ph')}" value="${esc(q)}" onkeydown="if(event.key==='Enter')guard(logs)(this.value)">` +
    tbl([t('a_time'), t('a_actor'), t('a_action'), t('a_details'), 'IP'], r.map(l => `<tr><td>${esc(l.ts)}</td><td>${esc(l.actor)}</td><td><b>${esc(l.action)}</b></td><td>${esc(l.detail)}</td><td>${esc(l.ip)}</td></tr>`)) +
    `<div class="gap" style="margin-top:10px">${off ? `<button class="btn sm ghost" onclick="guard(logs)('${esc(q)}',${off - 100})">${t('a_newer')}</button>` : ''}${r.length === 100 ? `<button class="btn sm ghost" onclick="guard(logs)('${esc(q)}',${off + 100})">${t('a_older')}</button>` : ''}</div>`);
}
async function tx(q = '') {
  const r = await api('admin/tx?q=' + encodeURIComponent(q));
  v(`<h1>${t('a_tx_h')}</h1><input placeholder="${t('a_tx_ph')}" value="${esc(q)}" onkeydown="if(event.key==='Enter')guard(tx)(this.value)">` +
    tbl([t('a_time'), t('a_who'), t('a_change'), t('a_bal_after'), t('a_reason_h'), t('a_by')], r.map(x => `<tr><td>${esc(x.ts.slice(0, 16))}</td><td>${esc(x.username)}</td><td style="color:${x.delta < 0 ? 'var(--bad)' : 'var(--ok)'}"><b>${x.delta > 0 ? '+' : ''}${fmt(x.delta, x.cur)}</b></td><td>${fmt(x.bal, x.cur)}</td><td>${esc(x.reason)}</td><td>${esc(x.actor)}</td></tr>`)));
}

// ------------------------------------------------------------ рассылка, настройки, соцсети, бэкап
async function tools() {
  const s = await api('admin/settings');
  const inp = (k, key, type = 'text') => fld('s-' + k, t(key), `<input id="s-${k}" type="${type}" value="${esc(s[k])}">`);
  v(`<h1>${t('a_bc_h')}</h1><div class="box"><textarea id="bc" placeholder="${t('a_bc_ph')}"></textarea><button class="btn block" onclick="guard(sendBc)()">${t('a_send')}</button></div>
    <h1 style="margin-top:22px">${t('a_settings_h')}</h1><div class="box">${inp('free_lessons', 'a_free_lessons', 'number')}
    ${fld('s-pay_info', t('a_payinfo'), `<textarea id="s-pay_info">${esc(s.pay_info)}</textarea>`)}${inp('support', 'a_support')}
    <h2>${t('a_social_h')}</h2>${['instagram', 'telegram', 'youtube', 'facebook', 'tiktok'].map(k => fld('s-social_' + k, k[0].toUpperCase() + k.slice(1), `<input id="s-social_${k}" type="url" value="${esc(s['social_' + k])}">`)).join('')}
    ${inp('contact_phone', 'a_phone')}${inp('contact_address', 'a_address')}<button class="btn block" style="margin-top:10px" onclick="guard(saveSettings)()">${t('save')}</button></div>
    <h1 style="margin-top:22px">${t('a_backup_h')}</h1><div class="box"><p class="muted" style="margin-bottom:8px">${t('a_backup_hint')}</p><button class="btn ghost block" onclick="guard(download)('admin/backup','academy-backup.db')">${t('a_backup_btn')}</button></div>`);
}
async function sendBc() {
  if (!confirm(t('a_bc_confirm'))) return;
  const r = await api('admin/broadcast', { method: 'POST', body: { text: $('#bc').value } });
  toast(r.bot ? `${t('a_bc_sending')}: ${r.sent}` : t('a_bc_nobot'), !r.bot); $('#bc').value = '';
}
async function saveSettings() {
  const keys = ['free_lessons', 'pay_info', 'support', 'social_instagram', 'social_telegram', 'social_youtube', 'social_facebook', 'social_tiktok', 'contact_phone', 'contact_address'];
  const body = {}; keys.forEach(k => body[k] = $('#s-' + k).value);
  await api('admin/settings', { method: 'PUT', body }); toast(t('saved'));
}

// ------------------------------------------------------------ профиль (личный кабинет админа / учителя)
async function profile() {
  v('<div id="pf"></div><div id="myact"></div>');
  await renderProfile($('#pf'), { showCurrency: false, onLogout: logoutNow,
    onLang: () => { setHeader(); go('profile'); }, onUser: u => { ME = u; setHeader(); } });
  if (ME.role === 'admin') {
    const r = await api('admin/logs?q=' + encodeURIComponent(ME.username));
    $('#myact').innerHTML = `<h2 style="margin-top:8px">${t('a_myact')}</h2>` + tbl([t('a_time'), t('a_action'), t('a_details')], r.slice(0, 20).map(l => `<tr><td>${esc(l.ts)}</td><td><b>${esc(l.action)}</b></td><td>${esc(l.detail)}</td></tr>`));
  }
}

const VIEWS = { dash, live, users, topups, prices, content, logs, tx, tools, profile };
mountToggles(); mountLangSwitch(document, () => { applyI18n(); });
applyI18n(); boot();
