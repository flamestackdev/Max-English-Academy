(() => {
  const $ = s => document.querySelector(s);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const TITLE = 'Max English Academy';
  const track = $('#introTrack'), stage = $('#introStage'), typed = $('#typed'), cursor = $('#cursor'), hint = $('#introHint'), bar = $('#bar');
  let complete = false;

  // ---------- 1. печать текста при прокрутке (механика из присланной анимации)
  const setHint = () => { hint.innerHTML = t(complete ? 'lp_hint2' : 'lp_hint1') + ' <span class="arrow">↓</span>'; };
  function updateTyping() {
    const scrollable = track.offsetHeight - innerHeight;
    const travelled = Math.min(Math.max(-track.getBoundingClientRect().top, 0), scrollable);
    const progress = scrollable > 0 ? travelled / scrollable : 0;
    const n = Math.min(TITLE.length, Math.floor(progress * (TITLE.length + 1)));
    typed.textContent = TITLE.slice(0, n); typed.appendChild(cursor);
    const done = n >= TITLE.length;
    stage.classList.toggle('complete', done);
    if (done !== complete || !hint.innerHTML) { complete = done; setHint(); }
  }

  // ---------- 3. карточки курсов: вертикальный свайп двигает ленту по горизонтали
  const ctrack = $('#courses'), rail = $('#rail'), cards = [...rail.children], cbar = $('#cardsBar');
  let maxShift = 0, pitch = 300, isStatic = false;
  function layoutCards() {
    ctrack.classList.remove('static'); ctrack.style.height = '';
    rail.style.transform = '';
    maxShift = rail.scrollWidth - innerWidth;
    isStatic = reduce.matches || maxShift < 120;
    ctrack.classList.toggle('static', isStatic);
    if (!isStatic) {
      ctrack.style.height = (innerHeight + maxShift) + 'px';
      pitch = cards[0].offsetWidth + (parseFloat(getComputedStyle(rail).columnGap) || 22);
    }
  }
  function updateCards() {
    if (isStatic) return;
    const scrollable = ctrack.offsetHeight - innerHeight;
    const p = Math.min(1, Math.max(0, -ctrack.getBoundingClientRect().top / scrollable));
    rail.style.transform = `translate3d(${-p * maxShift}px,0,0)`;
    cbar.style.width = (p * 100) + '%';
    const vc = innerWidth / 2;
    cards.forEach(c => {
      const r = c.getBoundingClientRect();
      const x = (r.left + r.width / 2 - vc) / pitch, a = Math.min(Math.abs(x), 2);
      c.style.transform = `perspective(1000px) rotateY(${(-x * 16).toFixed(2)}deg) scale(${(1 - a * 0.07).toFixed(3)}) translateY(${(a * 10).toFixed(1)}px)`;
      c.style.opacity = (1 - a * 0.25).toFixed(3);
    });
  }

  let ticking = false;
  const frame = () => { updateTyping(); updateCards(); bar.classList.toggle('solid', scrollY > 40); ticking = false; };
  const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(frame); } };
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', () => { layoutCards(); onScroll(); });
  reduce.addEventListener && reduce.addEventListener('change', () => { layoutCards(); onScroll(); });

  // ---------- появление блоков
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add(e.target.classList.contains('hero') ? 'is-visible' : 'in');
    if (e.target.id === 'lpStats') countUp();
    io.unobserve(e.target);
  }), { threshold: 0.15 }) : null;
  const watch = el => io ? io.observe(el) : el.classList.add('is-visible', 'in');
  watch($('.hero')); document.querySelectorAll('.rv').forEach(watch);

  // ---------- данные с сервера: цифры, соцсети, контакты
  let stats = {};
  function countUp() {
    document.querySelectorAll('#lpStats b').forEach(b => {
      const end = +(stats[b.dataset.n] || 0), t0 = performance.now();
      const step = now => { const k = Math.min(1, (now - t0) / 1200); b.textContent = Math.round(end * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    });
  }
  const ICONS = {
    instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor"/></svg>',
    telegram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 3 2 10.5l7 2.5 2.5 7L15 15l5 4z"/><path d="M9 13l7-5"/></svg>',
    youtube: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z" fill="currentColor"/></svg>',
    facebook: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 8h3V4h-3a4 4 0 0 0-4 4v3H7v4h3v6h4v-6h3l1-4h-4V8z"/></svg>',
    tiktok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 3c.4 2.6 2 4.2 5 4.5"/></svg>',
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safe = u => /^https?:\/\//.test(u) ? esc(u) : '#';
  fetch('/api/public').then(r => r.json()).then(d => {
    stats = d.stats || {};
    $('#socials').innerHTML = Object.keys(ICONS).filter(k => d['social_' + k]).map(k => `<a href="${safe(d['social_' + k])}" target="_blank" rel="noopener noreferrer" aria-label="${k[0].toUpperCase() + k.slice(1)}">${ICONS[k]}</a>`).join('');
    const sup = (d.support || '').trim(), supUrl = sup.startsWith('@') ? 'https://t.me/' + sup.slice(1) : (/^https?:/.test(sup) ? sup : '');
    $('#contacts').innerHTML = [d.contact_phone && `<a href="tel:${esc(d.contact_phone.replace(/[^+\d]/g, ''))}">📞 ${esc(d.contact_phone)}</a>`, d.contact_address && `<span>📍 ${esc(d.contact_address)}</span>`,
      sup && (supUrl ? `<a href="${esc(supUrl)}" target="_blank" rel="noopener noreferrer">💬 ${esc(sup)}</a>` : `<span>💬 ${esc(sup)}</span>`)].filter(Boolean).join('');
    if ($('#lpStats').classList.contains('in')) countUp();
  }).catch(() => { });

  // ---------- язык, вход, сессия
  const authFrame = $('#authFrame');
  function onLang() { setHint(); try { authFrame.contentWindow.location.reload(); } catch (e) { } layoutCards(); onScroll(); }
  applyI18n(); mountLangSwitch(document, onLang);
  if (localStorage.token) {   // уже вошли: вместо формы — кнопка «Открыть кабинет»
    $('#authWrap').hidden = true; $('#haveSession').hidden = false;
    const l = $('.lp-login'); l.href = '/app'; l.dataset.i18n = 'lp_open'; l.textContent = t('lp_open');
  }
  $('#yr').textContent = new Date().getFullYear();
  layoutCards(); updateTyping(); updateCards();
  addEventListener('load', () => { layoutCards(); onScroll(); });
})();
