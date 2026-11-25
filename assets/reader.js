const body = document.body;
const rail = document.getElementById('rail');
const pop = document.getElementById('cite-pop');
body.classList.add('js');
body.classList.remove('no-js');

/* ---------- outline / rail toggles ---------- */
for (const [id, key] of [['outline-toggle', 'outline'], ['rail-toggle', 'rail']]) {
  const button = document.getElementById(id);
  if (!button) continue;
  button.addEventListener('click', () => {
    const open = body.dataset[key] !== 'closed';
    body.dataset[key] = open ? 'closed' : 'open';
    button.setAttribute('aria-expanded', String(!open));
    if (key === 'rail') syncRail();
  });
}

/* ---------- reading size ---------- */
const SIZE_KEY = 'paper-reader-size';
function setSize(value) {
  const level = Math.max(0, Math.min(4, Number(value) || 0));
  document.documentElement.dataset.font = String(level);
  try { localStorage.setItem(SIZE_KEY, String(level)); } catch (error) { /* file:// without storage */ }
}
try {
  const saved = localStorage.getItem(SIZE_KEY);
  if (saved !== null) setSize(saved);
} catch (error) { /* ignore */ }
for (const button of document.querySelectorAll('[data-step]')) {
  button.addEventListener('click', () => setSize(Number(document.documentElement.dataset.font || 0) + Number(button.dataset.step)));
}

/* ---------- rail width ---------- */
const RESIZE_KEY = 'paper-reader-rail-width';
const resizer = document.getElementById('rail-resizer');
function railWidth(px, persist) {
  const width = Math.max(280, Math.min(760, Math.round(px)));
  body.style.setProperty('--user-rail', width + 'px');
  if (persist) { try { localStorage.setItem(RESIZE_KEY, String(width)); } catch (error) { /* ignore */ } }
}
try {
  const saved = localStorage.getItem(RESIZE_KEY);
  if (saved) railWidth(Number(saved), false);
} catch (error) { /* ignore */ }

if (resizer) {
  const dragging = () => body.classList.contains('resizing');
  resizer.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    body.classList.add('resizing');
    resizer.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  resizer.addEventListener('pointermove', event => {
    if (dragging()) railWidth(window.innerWidth - event.clientX, false);
  });
  const stop = event => {
    if (!dragging()) return;
    body.classList.remove('resizing');
    try { resizer.releasePointerCapture(event.pointerId); } catch (error) { /* ignore */ }
    const railBox = rail ? rail.getBoundingClientRect().width : 0;
    railWidth(railBox, true);
  };
  resizer.addEventListener('pointerup', stop);
  resizer.addEventListener('pointercancel', stop);
  resizer.addEventListener('dblclick', () => railWidth(352, true));
  resizer.addEventListener('keydown', event => {
    const current = rail ? rail.getBoundingClientRect().width : 352;
    if (event.key === 'ArrowLeft') { railWidth(current + 24, true); event.preventDefault(); }
    if (event.key === 'ArrowRight') { railWidth(current - 24, true); event.preventDefault(); }
  });
}

/* ---------- figures move between the rail and their section slot ---------- */
const wide = matchMedia('(min-width:1180px)');
const slots = new Map();
for (const slot of document.querySelectorAll('.fig-slot')) slots.set(slot.dataset.fig, slot);
const plates = [...slots.keys()].map(id => document.getElementById(id)).filter(Boolean);

if (rail && !rail.querySelector('.rail-head')) {
  const head = document.createElement('div');
  head.className = 'rail-head';
  head.textContent = '图表 · Figures & Tables';
  rail.append(head);
}

function syncRail() {
  if (!rail) return;
  const docked = wide.matches && body.dataset.rail !== 'closed';
  for (const figure of plates) {
    const slot = slots.get(figure.id);
    if (docked) { rail.append(figure); }
    else if (slot) { slot.append(figure); }
  }
  rail.hidden = !docked || plates.length === 0;
}
syncRail();
wide.addEventListener('change', syncRail);

/* ---------- clicking a figure mention ---------- */
function flash(node) {
  if (!node) return;
  node.classList.remove('flash');
  void node.offsetWidth;
  node.classList.add('flash');
}

document.addEventListener('click', event => {
  const link = event.target.closest('a.figref');
  if (!link) return;
  const figure = document.getElementById(link.getAttribute('href').slice(1));
  if (!figure) return;
  if (rail && !rail.hidden && rail.contains(figure)) {
    event.preventDefault();
    figure.scrollIntoView({ block: 'start', behavior: 'smooth' });
    flash(figure);
  } else {
    setTimeout(() => flash(figure), 0);
  }
});

/* ---------- reference popover ---------- */
function closePop() { if (pop) pop.hidden = true; }

function openPop(anchor) {
  if (!pop) return;
  const id = (anchor.getAttribute('href') || '').slice(1);
  const entry = id && document.getElementById(id);
  pop.replaceChildren();
  const head = document.createElement('div');
  head.className = 'cite-head';
  const label = document.createElement('b');
  label.textContent = '参考文献';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'cite-close';
  close.setAttribute('aria-label', '关闭');
  close.textContent = '×';
  close.addEventListener('click', closePop);
  head.append(label, close);
  pop.append(head);

  if (!entry) {
    const empty = document.createElement('p');
    empty.className = 'cite-empty';
    empty.textContent = '没有找到对应的参考文献条目。';
    pop.append(empty);
  } else {
    const body = document.createElement('div');
    body.className = 'cite-body';
    body.textContent = entry.textContent.replace(/\s+/g, ' ').trim();
    pop.append(body);
    const doi = body.textContent.match(/10\.\d{4,9}\/[^\s"<>]+/);
    if (doi) {
      const link = document.createElement('a');
      link.className = 'cite-doi';
      link.href = 'https://doi.org/' + doi[0].replace(/[.,;]$/, '');
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = 'DOI: ' + link.href.slice(16);
      pop.append(link);
    }
  }
  pop.hidden = false;
}

document.addEventListener('click', event => {
  const link = event.target.closest('a.cite, a.ref');
  if (link) {
    event.preventDefault();
    openPop(link);
    return;
  }
  if (pop && !pop.hidden && !event.target.closest('#cite-pop')) closePop();
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') closePop(); });

/* ---------- image zoom ---------- */
const dialog = document.querySelector('dialog[aria-label="Enlarged figure"], dialog.screen');
if (dialog) {
  const enlarged = dialog.querySelector('.enlarged');
  for (const button of document.querySelectorAll('.zoom')) {
    button.addEventListener('click', () => {
      const source = button.querySelector('img');
      const image = new Image();
      image.alt = source.alt;
      image.src = source.src;
      image.style.setProperty('--natural-width', source.getAttribute('width') + 'px');
      enlarged.replaceChildren(image);
      dialog.showModal();
      enlarged.scrollTop = 0;
      enlarged.scrollLeft = 0;
    });
  }
  dialog.querySelector('.close')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right ||
          event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    }
  });
  dialog.addEventListener('close', () => enlarged.replaceChildren());
}

/* ---------- reading language ---------- */
const languageMode = document.querySelector('#reading-language');
const validModes = new Set(['en', 'zh', 'both']);
function changeReadingMode(mode) {
  if (!validModes.has(mode)) return;
  const anchor = [...document.querySelectorAll('article .parallel')].find(block => block.getBoundingClientRect().bottom > 12);
  const before = anchor?.getBoundingClientRect().top;
  body.dataset.mode = mode;
  document.documentElement.lang = mode === 'en' ? 'en' : 'zh-Hans';
  languageMode.value = mode;
  if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - before);
}
languageMode?.addEventListener('change', () => changeReadingMode(languageMode.value));
