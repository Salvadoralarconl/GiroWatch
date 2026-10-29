(() => {
  /* ---------- Settings you may want to tweak ---------- */
  const CYCLE   = 56;    // seconds per full loop
  const T_DRIFT = 22;    // pieces float freely
  const T_IN    = 10;     // pieces drift together into the logo
  const T_HOLD  = 14;     // logo rests
  const T_OUT   = 10;     // logo gently comes apart
  const LOGO_SIZE = 0.44;   // assembled logo size, fraction of the shorter screen side
  const FLOAT_SCALE = 0.6;  // size of the logo pieces while floating

  /* ---------- Logo geometry (1250 x 1250 space) ---------- */
  const mirrorX = d => d.replace(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g, (_, x, y) => `${1250 - +x},${y}`);
  const CIRCLE = (cx, cy, r) => `M${cx + r},${cy}A${r},${r} 0 1,0 ${cx - r},${cy}A${r},${r} 0 1,0 ${cx + r},${cy}Z`;

  const CORE =
    'M625,52 L740,52 C830,52 905,125 908,215 C910,290 850,345 780,350 C740,356 712,388 712,420 ' +
    'C712,470 760,505 820,525 C870,542 900,580 900,627 C900,674 870,712 820,729 C760,749 712,784 712,834 ' +
    'C712,866 740,898 780,904 C850,909 910,964 908,1039 C905,1129 830,1202 740,1202 L510,1202 ' +
    'C420,1202 345,1129 342,1039 C340,964 400,909 470,904 C510,898 538,866 538,834 C538,784 490,749 430,729 ' +
    'C380,712 350,674 350,627 C350,580 380,542 430,525 C490,505 538,470 538,420 C538,388 510,356 470,350 ' +
    'C400,345 340,290 342,215 C345,125 420,52 510,52 Z ' + CIRCLE(625, 627, 167);
  const BEAN_L =
    'M45,520 C45,420 120,345 220,345 C290,345 340,395 362,428 C380,455 376,482 355,502 ' +
    'C320,536 297,577 297,627 C297,678 320,719 355,752 C376,772 380,800 362,826 ' +
    'C340,860 290,910 220,910 C120,910 45,835 45,735 Z';
  const BEAN_R = mirrorX(BEAN_L);
  const DISC = CIRCLE(625, 627, 127);
  const RING = CIRCLE(625, 627, 167) + ' ' + CIRCLE(625, 627, 122);

  /* ---------- Icons (24 x 24 line icons) ---------- */
  const ICONS = {
    eye:    '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    clock:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    bell:   '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    chart:  '<path d="M3 20h18M6 16v-5M11 16V7M16 16v-3M21 16V9"/>',
    pin:    '<path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    lock:   '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    pulse:  '<path d="M3 12h4l3-7 4 14 3-7h4"/>'
  };
  const SHOW_ICONS = false; // set to true to bring the icons back
  const icon = (name, cx, cy, size) => {
    if (!SHOW_ICONS) return '';
    const s = size / 24;
    return `<g transform="translate(${cx - size / 2},${cy - size / 2}) scale(${s})" stroke-width="1.5">${ICONS[name]}</g>`;
  };

  /* ---------- Shape templates ---------- */
  const TYPES = {
    bean: { vb: [40, 340, 340, 575], d: BEAN_L, ic: [205, 627, 120] },
    disc: { vb: [493, 495, 264, 264], d: DISC, ic: [625, 627, 120] },
    ring: { vb: [453, 455, 344, 344], d: RING, ic: [625, 627, 110] },
    mini: { vb: [40, 45, 1170, 1165], d: [CORE, BEAN_L, BEAN_R, DISC], ic: [625, 627, 100] }
  };

  const svgFor = (vb, paths, grad, iconsMarkup) =>
    `<svg viewBox="${vb.join(' ')}" xmlns="http://www.w3.org/2000/svg">` +
    paths.map(d => `<path d="${d}" fill="url(#${grad})" fill-rule="evenodd"/>`).join('') +
    `<g class="icons">${iconsMarkup}</g></svg>`;

  const stage = document.getElementById('login-animation');
  const items = [];

  /* Logo pieces: these fly together into the logo */
  const PIECES = [
    { d: CORE,   o: [0.5, 0.5],          home: [0.50, 0.31], r0: -14, grad: 'login-g-ink',
      icons: [['shield', 625, 200, 130], ['chart', 625, 1055, 130]] },
    { d: BEAN_L, o: [205 / 1250, 0.502], home: [0.31, 0.50], r0: 16,  grad: 'login-g-blue',
      icons: [['eye', 205, 627, 120]] },
    { d: BEAN_R, o: [1045 / 1250, 0.502], home: [0.69, 0.50], r0: -18, grad: 'login-g-ink',
      icons: [['bell', 1045, 627, 120]] },
    { d: DISC,   o: [0.5, 0.502],        home: [0.50, 0.69], r0: 0,   grad: 'login-g-blue',
      icons: [['clock', 625, 627, 120]] }
  ];

  PIECES.forEach((p, i) => {
    const el = document.createElement('div');
    el.className = 'shape piece';
    el.innerHTML = svgFor([0, 0, 1250, 1250], [p.d], p.grad, p.icons.map(a => icon(...a)).join(''));
    el.style.transformOrigin = `${p.o[0] * 100}% ${p.o[1] * 100}%`;
    stage.appendChild(el);
    items.push({ el, kind: 'piece', ...p, iconsEl: el.querySelector('.icons'),
      ax: 3, ay: 3, fx: 0.008, fy: 0.007,
      px: i * 1.7, py: i * 2.3, ar: 2, fr: 0.006, depth: 18 + i * 5 });
  });

  /* ---------- Motion ---------- */
  const ease = x => -(Math.cos(Math.PI * x) - 1) / 2; // soft sine ease
  const assembleK = t => {
    let c = t % CYCLE;
    if (c < T_DRIFT) return 0;
    c -= T_DRIFT; if (c < T_IN) return ease(c / T_IN);
    c -= T_IN;    if (c < T_HOLD) return 1;
    c -= T_HOLD;  if (c < T_OUT) return 1 - ease(c / T_OUT);
    return 0;
  };
  const lerp = (a, b, k) => a + (b - a) * k;

  let mx = 0, my = 0, tmx = 0, tmy = 0;
  addEventListener('pointermove', e => {
    if(e.pointerType==='touch')return;
    const bounds=stage.getBoundingClientRect();
    const dx=e.clientX-(bounds.left+bounds.width/2), dy=e.clientY-(bounds.top+bounds.height/2);
    const radius=Math.min(bounds.width,bounds.height)*0.38;
    const proximity=Math.max(0,1-Math.hypot(dx,dy)/Math.max(1,radius));
    const influence=proximity*proximity*(3-2*proximity);
    tmx=dx/Math.max(1,radius)*influence*2;
    tmy=dy/Math.max(1,radius)*influence*2;
  });
  document.addEventListener('pointerleave',()=>{tmx=0;tmy=0;});

  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  let reduced=motion.matches, frameId=null, started=performance.now();
  const screen=document.getElementById('account-screen');
  const T_OFFSET = 12; // first assembly begins about 10 seconds after load

  function frame(now) {
    frameId=null;
    if(screen.hidden || document.hidden)return;
    const t = reduced ? 0 : (now-started) / 1000 + T_OFFSET;
    const W = stage.clientWidth, H = stage.clientHeight, S = Math.min(W, H);
    const L = S * LOGO_SIZE;
    const k = reduced ? 0 : assembleK(t);
    mx += (tmx - mx) * 0.045; my += (tmy - my) * 0.045;
    const breathe = 1 + 0.01 * Math.sin(t * 0.5) * k;

    for (const it of items) {
      const amp = reduced ? 0 : 1;
      const orbit = reduced ? 0 : t * 0.025;
      const dx=(it.home[0]-0.5)*S, dy=(it.home[1]-0.5)*S;
      const homeX=W/2+dx*Math.cos(orbit)-dy*Math.sin(orbit);
      const homeY=H/2+dx*Math.sin(orbit)+dy*Math.cos(orbit);
      let x = homeX + amp * it.ax * Math.sin(t * it.fx * 6.283 + it.px) + (reduced ? 0 : mx * it.depth);
      let y = homeY + amp * it.ay * Math.sin(t * it.fy * 6.283 + it.py) + (reduced ? 0 : my * it.depth);
      const rot = it.r0 + amp * it.ar * Math.sin(t * it.fr * 6.283 + it.px);

      if (it.kind === 'piece') {
        it.el.style.width = it.el.style.height = L + 'px';
        const dX = x - it.o[0] * L, dY = y - it.o[1] * L;
        const aX = W / 2 - L / 2 + (reduced ? 0 : mx * 18),
              aY = H / 2 - L / 2 + (reduced ? 0 : my * 18);
        const tx = lerp(dX, aX, k), ty = lerp(dY, aY, k);
        const r = lerp(rot, 0, k);
        const s = lerp(FLOAT_SCALE, 1, k) * breathe;
        it.el.style.transform = `translate(${tx}px,${ty}px) rotate(${r}deg) scale(${s})`;
        it.iconsEl.style.opacity = 1 - k;
      } else {
        // push decor away from the centre while the logo forms
        const vx = x - W / 2, vy = y - H / 2, len = Math.hypot(vx, vy) || 1;
        x += (vx / len) * S * 0.03 * k;
        y += (vy / len) * S * 0.03 * k;
        const w = it.size * S, h = w * it.aspect;
        it.el.style.width = w + 'px';
        it.el.style.height = h + 'px';
        it.el.style.transform = `translate(${x - w / 2}px,${y - h / 2}px) rotate(${rot}deg)`;
        it.el.style.opacity = 1 - 0.6 * k;
      }
    }
    if (!reduced) frameId=requestAnimationFrame(frame);
  }
  function sync() {
    if(frameId!==null)cancelAnimationFrame(frameId);
    frameId=null;
    if(!screen.hidden && !document.hidden)frameId=requestAnimationFrame(frame);
  }
  new MutationObserver(sync).observe(screen,{attributes:true,attributeFilter:['hidden']});
  document.addEventListener('visibilitychange',sync);
  motion.addEventListener('change',()=>{reduced=motion.matches;sync();});
  new ResizeObserver(sync).observe(stage);
  sync();
})();
