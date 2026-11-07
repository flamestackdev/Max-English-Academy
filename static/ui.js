/* Общие элементы интерфейса: тема (светлая/тёмная) + анимированные переключатель и кнопка выхода */
const Theme = {
  sys: () => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  get: () => document.documentElement.dataset.theme || localStorage.theme || Theme.sys(),
  // th: 'light' | 'dark'; remote=true сообщает странице, что тему нужно сохранить в аккаунте
  set(th, remote) {
    document.documentElement.dataset.theme = th;
    localStorage.theme = th;
    const m = document.querySelector('meta[name=theme-color]');
    if (m) m.content = th === 'dark' ? '#1f2335' : '#ffffff';
    document.querySelectorAll('.dn').forEach(d => {
      d.classList.toggle('night', th === 'dark'); d.classList.toggle('on', th === 'dark');
      d.parentElement.setAttribute('aria-checked', th === 'dark');
    });
    if (remote && window.onTheme) window.onTheme(th);
  },
  toggle() {
    const h = document.documentElement; h.classList.add('theming');
    clearTimeout(Theme.t); Theme.t = setTimeout(() => h.classList.remove('theming'), 700);
    Theme.set(Theme.get() === 'dark' ? 'light' : 'dark', true);
  },
};

const dots = n => Array.from({ length: n }, () => `<span style="left:${(Math.random() * 100).toFixed(1)}%;top:${(Math.random() * 100).toFixed(1)}%"></span>`).join('');
const bird = c => `<svg class="dn-bird ${c}" viewBox="0 0 14 8" aria-hidden="true"><path class="dn-wing" d="M0 6 Q7 -2 14 6 Q7 3 0 6Z" fill="#eef6ff"/></svg>`;
const cloud = `<img src="/static/img/cloud.png" alt="" aria-hidden="true" draggable="false">`;

// Заполняет все <span data-dn data-s="0.3"></span> анимированным переключателем
function mountToggles(root = document) {
  root.querySelectorAll('[data-dn]').forEach(el => {
    if (el.firstElementChild) return;
    el.className = 'dn-btn'; el.setAttribute('role', 'switch');
    el.setAttribute('aria-label', typeof t === 'function' ? t('theme') : 'Theme'); el.style.setProperty('--s', el.dataset.s || '.3');
    el.innerHTML = `<span class="dn"><span class="dn-track"><span class="dn-stars">${dots(14)}</span>
      <span class="dn-shoots"><span class="dn-shoot s1"></span><span class="dn-shoot s2"></span><span class="dn-shoot s3"></span></span>
      <span class="dn-moon"><span class="dn-moon">🌙</span></span><span class="dn-sun"></span>
      <span class="dn-birds">${bird('b1')}${bird('b2')}${bird('b3')}</span>
      <span class="dn-clouds"><span class="dn-cloud-track">${cloud}${cloud}${cloud}${cloud}</span></span></span><span class="dn-knob"></span></span>`;
    el.onclick = () => Theme.toggle();
  });
  Theme.set(Theme.get(), false);
}

// ---------------- кнопка выхода: состояния анимации взяты из Logout_Button_Animation.zip
const LO_STATES = {
  default: { '--figure-duration': '100', '--transform-figure': 'none', '--walking-duration': '100', '--transform-arm1': 'none', '--transform-wrist1': 'none', '--transform-arm2': 'none', '--transform-wrist2': 'none', '--transform-leg1': 'none', '--transform-calf1': 'none', '--transform-leg2': 'none', '--transform-calf2': 'none' },
  hover: { '--figure-duration': '100', '--transform-figure': 'translateX(1.5px)', '--walking-duration': '100', '--transform-arm1': 'rotate(-5deg)', '--transform-wrist1': 'rotate(-15deg)', '--transform-arm2': 'rotate(5deg)', '--transform-wrist2': 'rotate(6deg)', '--transform-leg1': 'rotate(-10deg)', '--transform-calf1': 'rotate(5deg)', '--transform-leg2': 'rotate(20deg)', '--transform-calf2': 'rotate(-20deg)' },
  walking1: { '--figure-duration': '300', '--transform-figure': 'translateX(11px)', '--walking-duration': '300', '--transform-arm1': 'translateX(-4px) translateY(-2px) rotate(120deg)', '--transform-wrist1': 'rotate(-5deg)', '--transform-arm2': 'translateX(4px) rotate(-110deg)', '--transform-wrist2': 'rotate(-5deg)', '--transform-leg1': 'translateX(-3px) rotate(80deg)', '--transform-calf1': 'rotate(-30deg)', '--transform-leg2': 'translateX(4px) rotate(-60deg)', '--transform-calf2': 'rotate(20deg)' },
  walking2: { '--figure-duration': '400', '--transform-figure': 'translateX(17px)', '--walking-duration': '300', '--transform-arm1': 'rotate(60deg)', '--transform-wrist1': 'rotate(-15deg)', '--transform-arm2': 'rotate(-45deg)', '--transform-wrist2': 'rotate(6deg)', '--transform-leg1': 'rotate(-5deg)', '--transform-calf1': 'rotate(10deg)', '--transform-leg2': 'rotate(10deg)', '--transform-calf2': 'rotate(-20deg)' },
  falling1: { '--figure-duration': '1600', '--walking-duration': '400', '--transform-arm1': 'rotate(-60deg)', '--transform-wrist1': 'none', '--transform-arm2': 'rotate(30deg)', '--transform-wrist2': 'rotate(120deg)', '--transform-leg1': 'rotate(-30deg)', '--transform-calf1': 'rotate(-20deg)', '--transform-leg2': 'rotate(20deg)' },
  falling2: { '--walking-duration': '300', '--transform-arm1': 'rotate(-100deg)', '--transform-arm2': 'rotate(-60deg)', '--transform-wrist2': 'rotate(60deg)', '--transform-leg1': 'rotate(80deg)', '--transform-calf1': 'rotate(20deg)', '--transform-leg2': 'rotate(-60deg)' },
  falling3: { '--walking-duration': '500', '--transform-arm1': 'rotate(-30deg)', '--transform-wrist1': 'rotate(40deg)', '--transform-arm2': 'rotate(50deg)', '--transform-wrist2': 'none', '--transform-leg1': 'rotate(-30deg)', '--transform-leg2': 'rotate(20deg)', '--transform-calf2': 'none' },
};
const FIG = `<svg class="doorway" viewBox="0 0 100 100"><path d="M93.4 86.3H58.6c-1.9 0-3.4-1.5-3.4-3.4V17.1c0-1.9 1.5-3.4 3.4-3.4h34.8c1.9 0 3.4 1.5 3.4 3.4v65.8c0 1.9-1.5 3.4-3.4 3.4z"/><path class="bang" d="M40.5 43.7L26.6 31.4l-2.5 6.7zM41.9 50.4l-19.5-4-1.4 6.3zM40 57.4l-17.7 3.9 3.9 5.7z"/></svg>
<svg class="figure" viewBox="0 0 100 100"><circle cx="52.1" cy="32.4" r="6.4"/><path d="M50.7 62.8c-1.2 2.5-3.6 5-7.2 4-3.2-.9-4.9-3.5-4-7.8.7-3.4 3.1-13.8 4.1-15.8 1.7-3.4 1.6-4.6 7-3.7 4.3.7 4.6 2.5 4.3 5.4-.4 3.7-2.8 15.1-4.2 17.9z"/>
<g class="arm1"><path d="M55.5 56.5l-6-9.5c-1-1.5-.6-3.5.9-4.4 1.5-1 3.7-1.1 4.6.4l6.1 10c1 1.5.3 3.5-1.1 4.4-1.5.9-3.5.5-4.5-.9z"/><path class="wrist1" d="M69.4 59.9L58.1 58c-1.7-.3-2.9-1.9-2.6-3.7.3-1.7 1.9-2.9 3.7-2.6l11.4 1.9c1.7.3 2.9 1.9 2.6 3.7-.4 1.7-2 2.9-3.8 2.6z"/></g>
<g class="arm2"><path d="M34.2 43.6L45 40.3c1.7-.6 3.5.3 4 2 .6 1.7-.3 4-2 4.5l-10.8 2.8c-1.7.6-3.5-.3-4-2-.6-1.6.3-3.4 2-4z"/><path class="wrist2" d="M27.1 56.2L32 45.7c.7-1.6 2.6-2.3 4.2-1.6 1.6.7 2.3 2.6 1.6 4.2L33 58.8c-.7 1.6-2.6 2.3-4.2 1.6-1.7-.7-2.4-2.6-1.7-4.2z"/></g>
<g class="leg1"><path d="M52.1 73.2s-7-5.7-7.9-6.5c-.9-.9-1.2-3.5-.1-4.9 1.1-1.4 3.8-1.9 5.2-.9l7.9 7c1.4 1.1 1.7 3.5.7 4.9-1.1 1.4-4.4 1.5-5.8.4z"/><path class="calf1" d="M52.6 84.4l-1-12.8c-.1-1.9 1.5-3.6 3.5-3.7 2-.1 3.7 1.4 3.8 3.4l1 12.8c.1 1.9-1.5 3.6-3.5 3.7-2 0-3.7-1.5-3.8-3.4z"/></g>
<g class="leg2"><path d="M37.8 72.7s1.3-10.2 1.6-11.4 2.4-2.8 4.1-2.6c1.7.2 3.6 2.3 3.4 4l-1.8 11.1c-.2 1.7-1.7 3.3-3.4 3.1-1.8-.2-4.1-2.4-3.9-4.2z"/><path class="calf2" d="M29.5 82.3l9.6-10.9c1.3-1.4 3.6-1.5 5.1-.1 1.5 1.4.4 4.9-.9 6.3l-8.5 9.6c-1.3 1.4-3.6 1.5-5.1.1-1.4-1.3-1.5-3.5-.2-5z"/></g></svg>
<svg class="door" viewBox="0 0 100 100"><path d="M93.4 86.3H58.6c-1.9 0-3.4-1.5-3.4-3.4V17.1c0-1.9 1.5-3.4 3.4-3.4h34.8c1.9 0 3.4 1.5 3.4 3.4v65.8c0 1.9-1.5 3.4-3.4 3.4z"/><circle cx="66" cy="50" r="3.7"/></svg>`;

// Вставляет кнопку выхода в el. onDone вызывается, когда человечек «убежал» (~1.9 с после нажатия)
function mountLogout(el, onDone) {
  el.innerHTML = `<button type="button" class="logoutButton">${FIG}<span class="button-text">${typeof t === 'function' ? t('logout') : 'Log out'}</span></button>`;
  const b = el.firstElementChild;
  b.state = 'default';
  const set = s => { b.state = s; for (const k in LO_STATES[s]) b.style.setProperty(k, LO_STATES[s][k]); };
  const later = (ms, fn) => setTimeout(fn, ms);
  b.onmouseenter = () => { if (b.state === 'default') set('hover'); };
  b.onmouseleave = () => { if (b.state === 'hover') set('default'); };
  b.onclick = () => {
    if (b.state !== 'default' && b.state !== 'hover') return;
    document.documentElement.classList.add('logging-out');
    b.classList.add('clicked'); set('walking1');
    later(LO_STATES.walking1['--figure-duration'] * 1, () => {
      b.classList.add('door-slammed'); set('walking2');
      later(+LO_STATES.walking2['--figure-duration'], () => {
        b.classList.add('falling'); set('falling1');
        later(+LO_STATES.falling1['--walking-duration'], () => {
          set('falling2');
          later(+LO_STATES.falling2['--walking-duration'], () => {
            set('falling3');
            later(500, () => {
              onDone && onDone();
              later(1500, () => { b.classList.remove('clicked', 'door-slammed', 'falling'); set('default'); document.documentElement.classList.remove('logging-out'); });
            });
          });
        });
      });
    });
  };
}
