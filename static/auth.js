const $ = s => document.querySelector(s);
const embedded = self !== top;
const go = url => { (embedded ? top : window).location.href = url; };
if (localStorage.token && !embedded) go('/app');

function toast(m, bad) {
  const e = $('#toast'); e.textContent = m; e.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => e.className = '', 3500);
}
const errText = e => D['e_' + e.error] ? t('e_' + e.error) : t('e_x');
document.querySelectorAll('.soon').forEach(a => a.onclick = e => { e.preventDefault(); toast(t('soon')); });
$('#forgot').onclick = e => { e.preventDefault(); toast(t('forgot_hint')); };

async function submit(form, url, extra) {
  const btn = form.querySelector('button[type=submit]'); btn.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form)); Object.assign(body, extra);
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw d;
    localStorage.token = d.token; await syncPickedLang(d.token, d.user.lang);
    go(['admin', 'teacher'].includes(d.user.role) ? '/admin' : '/app');
  } catch (e) { toast(errText(e || {}), true); }
  btn.disabled = false;
}
$('#login-form').onsubmit = e => { e.preventDefault(); submit(e.target, '/api/login'); };
$('#reg-form').onsubmit = e => { e.preventDefault(); submit(e.target, '/api/register', { lang }); };
mountToggles(); mountLangSwitch(document); applyI18n();
