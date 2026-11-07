/* Личный кабинет: общий для сайта (/app) и админ-панели (/admin).
   Использует глобальные api, toast, fail, esc, t, lang, setLang (определены в app.js / admin.js / i18n.js) */
const EYE = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
const pwField = (id, label, auto) => `<label class="f" for="${id}">${label}</label><div class="pw"><input id="${id}" type="password" autocomplete="${auto}" maxlength="100"><button type="button" data-p="eye" data-for="${id}" aria-label="${t('show_pw')}">${EYE}</button></div>`;
const initials = u => (u.full_name || u.username || '?').trim().slice(0, 2);
function pwScore(p) {
  if (p.length < 6) return 0;
  return Math.min(4, (p.length >= 8) + (p.length >= 12) + (/[a-z]/.test(p) && /[A-Z]/.test(p)) + /\d/.test(p) + /[^A-Za-z0-9]/.test(p));
}

async function renderProfile(el, o = {}) {
  const P = await api('profile'), U = P.user, S = P.stats;
  const showLang = o.showLang !== false, showCur = o.showCurrency !== false;
  const pct = U.progress.total ? Math.round(U.progress.done / U.progress.total * 100) : 0;
  const seg = (items, cur, act, cls = '') => `<div class="seg ${cls}">${items.map(([v, l]) => `<button type="button" data-p="${act}" data-v="${v}" class="${v === cur ? 'on' : ''}" aria-pressed="${v === cur}">${l}</button>`).join('')}</div>`;
  el.innerHTML = `
    <div class="hero"><div class="prof"><span class="avatar xl">${esc(initials(U))}</span><div style="min-width:0">
      <h1>${esc(U.full_name || U.username)}</h1><p>@${esc(U.username)} · <span class="chip" style="padding:1px 9px">${esc(t('role_' + U.role))}</span></p>
      <p>${esc(U.email || '—')}</p></div></div>
      <p style="margin-top:12px">${t('member_since')} ${esc((U.created || '').slice(0, 10))} · ${t('last_login')}: ${esc((U.last_login || '—').slice(0, 16))}</p>
      <p>${t('progress')}: ${U.progress.done}/${U.progress.total}</p><div class="bar"><i style="width:${pct}%"></i></div></div>
    <div class="stats"><div><b>🔥 ${U.streak}</b><span>${t('streak')} (${t('days')})</span></div><div><b>⭐ ${S.points}</b><span>${t('points')}</span></div><div><b>${S.rank ? '#' + S.rank : '—'}</b><span>${t('rank')}</span></div></div>

    <h2>${t('settings')}</h2><div class="box" style="padding:4px 16px">
      ${showLang ? `<div class="srow col"><span>${t('language')}<small>${t('lang_hint')}</small></span>${seg(LANGS.map(l => [l, LANG_NAMES[l]]), U.lang, 'lang', 'g2')}</div>` : ''}
      <div class="srow"><span>${t('theme')}<small>${t('theme_hint')}</small></span><button type="button" data-dn data-s=".42"></button></div>
      ${showCur ? `<div class="srow"><span>${t('currency')}<small>${t('currency_hint')}</small></span>${seg(['UZS', 'USD', 'KZT'].map(c => [c, c]), U.currency, 'cur')}</div>` : ''}
      <div class="srow"><span>${t('notify')}<small>${t('notify_hint')}</small></span><input type="checkbox" class="sw" id="pf-notify" role="switch" aria-label="${t('notify')}" ${U.notify_tg ? 'checked' : ''}></div>
    </div>

    <h2>${t('account')}</h2><div class="box">
      <label class="f" for="pf-name">${t('full_name')}</label><input id="pf-name" maxlength="60" value="${esc(U.full_name)}" autocomplete="name">
      <label class="f" for="pf-user">${t('username')}</label><input id="pf-user" maxlength="24" value="${esc(U.username)}" autocomplete="username">
      <label class="f" for="pf-mail">${t('email')}</label><input id="pf-mail" type="email" maxlength="100" value="${esc(U.email)}" autocomplete="email">
      ${pwField('pf-cur1', t('cur_pass'), 'current-password')}<p class="muted" style="margin:-4px 0 10px">${t('pass_need')}</p>
      <button type="button" class="btn block" data-p="account">${t('save')}</button></div>

    <h2>${t('pass_change')}</h2><div class="box">
      ${pwField('pf-cur2', t('cur_pass'), 'current-password')}${pwField('pf-new', t('new_pass'), 'new-password')}
      <div class="strength" id="pf-str"><i></i><i></i><i></i><i></i></div><p class="muted" id="pf-strl" style="margin:0 0 6px">&nbsp;</p>
      ${pwField('pf-rep', t('rep_pass'), 'new-password')}
      <button type="button" class="btn block" style="margin-top:6px" data-p="password">${t('pass_change')}</button></div>

    <h2>Telegram</h2><div class="box"><div class="gap"><span class="tag ${U.tg ? 'ok' : 'warn'}">${U.tg ? t('tg_linked') : t('tg_not')}</span></div>
      ${U.tg ? `<button type="button" class="btn ghost red sm" style="margin-top:12px" data-p="unlink">${t('tg_unlink')}</button>`
             : `<button type="button" class="btn ghost block" style="margin-top:12px" data-p="code">${t('get_code')}</button><p id="pf-code" class="muted" style="margin-top:8px"></p>`}</div>

    <h2>${t('devices')}</h2><div class="box" style="padding:4px 16px">${P.sessions.map(s => `<div class="sess"><div class="grow"><b style="font-weight:500">${esc(s.ua || '—')}</b><br><span class="muted">${esc(s.ip)} · ${esc(s.ts.slice(0, 16))}</span></div>
        ${s.current ? `<span class="tag ok">${t('this_device')}</span>` : `<button type="button" class="btn ghost sm" data-p="end" data-id="${s.id}">${t('end_session')}</button>`}</div>`).join('')}</div>
      ${P.sessions.length > 1 ? `<button type="button" class="btn ghost block" data-p="others">${t('logout_others')}</button>` : ''}

    ${U.role !== 'admin' ? `<h2>${t('danger')}</h2><div class="box danger"><p class="muted" style="margin-bottom:8px">${t('delete_hint')}</p>${pwField('pf-del', t('cur_pass'), 'current-password')}
      <button type="button" class="btn ghost red block" data-p="delete">${t('delete_acc')}</button></div>` : ''}
    <div class="lo-wrap" id="pf-lo"></div>`;

  mountToggles(el);
  mountLogout(el.querySelector('#pf-lo'), o.onLogout);
  const val = id => el.querySelector('#' + id).value;
  const again = () => renderProfile(el, o);
  const call = async (path, body, ok) => { try { const r = await api(path, { method: 'POST', body }); if (ok) toast(ok); return r; } catch (e) { fail(e); return null; } };

  el.querySelector('#pf-new').oninput = e => {
    const sc = pwScore(e.target.value), box = el.querySelector('#pf-str');
    box.className = 'strength s' + sc; box.querySelectorAll('i').forEach((i, n) => i.classList.toggle('on', n < sc));
    el.querySelector('#pf-strl').textContent = e.target.value ? t('str' + sc) : '\u00a0';
  };
  el.querySelector('#pf-notify').onchange = async e => {
    try { await api('me', { method: 'PATCH', body: { notify_tg: e.target.checked } }); toast(t('saved')); } catch (err) { fail(err); e.target.checked = !e.target.checked; }
  };
  el.onclick = async e => {
    const b = e.target.closest('[data-p]'); if (!b) return;
    const a = b.dataset.p;
    if (a === 'eye') { const i = el.querySelector('#' + b.dataset.for); i.type = i.type === 'password' ? 'text' : 'password'; return; }
    b.disabled = true;
    try {
      if (a === 'lang') { await api('me', { method: 'PATCH', body: { lang: b.dataset.v } }); setLang(b.dataset.v); return o.onLang ? o.onLang() : again(); }
      if (a === 'cur') { await api('me', { method: 'PATCH', body: { currency: b.dataset.v } }); return again(); }
      if (a === 'account') {
        const r = await call('me/account', { full_name: val('pf-name'), username: val('pf-user'), email: val('pf-mail'), current_password: val('pf-cur1') }, t('saved'));
        if (r) { o.onUser && o.onUser(r); return again(); }
      }
      if (a === 'password') {
        if (val('pf-new') !== val('pf-rep')) return toast(t('pass_mismatch'), 1);
        const r = await call('me/password', { current: val('pf-cur2'), new: val('pf-new') }, t('pass_changed'));
        if (r) return again();
      }
      if (a === 'code') { const r = await call('linkcode', {}); if (r) el.querySelector('#pf-code').innerHTML = `${t('link_hint')}${r.bot ? ' @' + esc(r.bot) : ''}: <b>/link ${esc(r.code)}</b> (10 min)`; }
      if (a === 'unlink') { if (confirm(t('tg_unlink') + '?') && await call('me/unlink_tg', {}, t('tg_unlinked'))) return again(); }
      if (a === 'end') { if (await call('me/sessions/revoke', { id: +b.dataset.id })) return again(); }
      if (a === 'others') { if (await call('me/sessions/revoke', { id: 'others' }, t('others_closed'))) return again(); }
      if (a === 'delete') {
        if (!confirm(t('delete_confirm'))) return;
        if (await call('me/delete', { password: val('pf-del') })) { localStorage.removeItem('token'); location.href = '/'; }
      }
    } catch (err) { fail(err); }
    b.disabled = false;
  };
}
