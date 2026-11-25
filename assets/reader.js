const body = document.body;
const app = document.querySelector('.app');
const rail = document.getElementById('rail');
const pop = document.getElementById('cite-pop');
const railSwitch = document.getElementById('rail-switch');
const wide = matchMedia('(min-width:1181px)');

/* scripts are an enhancement: the page works without them */
body.classList.add('js');
body.classList.remove('no-js');

/* ---------- reading size (radios do the work; this only remembers) ---------- */
const SIZE_KEY = 'paper-reader-size';
const sizeInputs = [...document.querySelectorAll('input[name="reading-size"]')];
try {
  const saved = localStorage.getItem(SIZE_KEY);
  const target = saved === null ? null : document.getElementById('size-' + saved);
  if (target) target.checked = true;
} catch (error) { /* file:// without storage */ }
for (const input of sizeInputs) {
  input.addEventListener('change', () => {
    if (!input.checked) return;
    try { localStorage.setItem(SIZE_KEY, input.id.replace('size-', '')); } catch (error) { /* ignore */ }
  });
}

/* ---------- rail text size, independent of the article ---------- */
const RAIL_SIZE_KEY = 'paper-reader-rail-size';
const railSizeInputs = [...document.querySelectorAll('input[name="rail-size"]')];
try {
  const saved = localStorage.getItem(RAIL_SIZE_KEY);
  const target = saved === null ? null : document.getElementById('rail-size-' + saved);
  if (target) target.checked = true;
} catch (error) { /* ignore */ }
for (const input of railSizeInputs) {
  input.addEventListener('change', () => {
    if (!input.checked) return;
    try { localStorage.setItem(RAIL_SIZE_KEY, input.id.replace('rail-size-', '')); } catch (error) { /* ignore */ }
  });
}

/* ---------- rail width: presets stay in CSS, dragging is an extra ---------- */
const RESIZE_KEY = 'paper-reader-rail-width';
const resizer = document.getElementById('rail-resizer');
const widthInputs = [...document.querySelectorAll('input[name="rail-width"]')];
function setDraggedWidth(px, persist) {
  const width = Math.max(260, Math.min(760, Math.round(px)));
  app.style.setProperty('--user-rail', width + 'px');
  if (persist) { try { localStorage.setItem(RESIZE_KEY, 'px:' + width); } catch (error) { /* ignore */ } }
}
try {
  const saved = localStorage.getItem(RESIZE_KEY);
  if (saved && saved.startsWith('px:')) setDraggedWidth(Number(saved.slice(3)), false);
  else if (saved && saved.startsWith('preset:')) {
    const input = document.getElementById('rail-w-' + saved.slice(7));
    if (input) input.checked = true;
  }
} catch (error) { /* ignore */ }
for (const input of widthInputs) {
  input.addEventListener('change', () => {
    if (!input.checked) return;
    app.style.removeProperty('--user-rail');
    try { localStorage.setItem(RESIZE_KEY, 'preset:' + input.id.replace('rail-w-', '')); } catch (error) { /* ignore */ }
  });
}

if (resizer) {
  const dragging = () => body.classList.contains('resizing');
  resizer.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    body.classList.add('resizing');
    resizer.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  resizer.addEventListener('pointermove', event => {
    if (dragging()) setDraggedWidth(window.innerWidth - event.clientX, false);
  });
  const stop = event => {
    if (!dragging()) return;
    body.classList.remove('resizing');
    try { resizer.releasePointerCapture(event.pointerId); } catch (error) { /* ignore */ }
    const box = rail ? rail.getBoundingClientRect().width : 0;
    setDraggedWidth(box, true);
  };
  resizer.addEventListener('pointerup', stop);
  resizer.addEventListener('pointercancel', stop);
  resizer.addEventListener('dblclick', () => {
    app.style.removeProperty('--user-rail');
    try { localStorage.removeItem(RESIZE_KEY); } catch (error) { /* ignore */ }
  });
  resizer.addEventListener('keydown', event => {
    const current = rail ? rail.getBoundingClientRect().width : 352;
    if (event.key === 'ArrowLeft') { setDraggedWidth(current + 24, true); event.preventDefault(); }
    if (event.key === 'ArrowRight') { setDraggedWidth(current - 24, true); event.preventDefault(); }
  });
}

/* ---------- figures: rail by default, section slot when narrow ---------- */
const slots = new Map();
for (const slot of document.querySelectorAll('.fig-slot')) slots.set(slot.dataset.fig, slot);
const plates = [...slots.keys()].map(id => document.getElementById(id)).filter(Boolean);

if (rail && !rail.querySelector('.rail-head')) {
  const head = document.createElement('div');
  head.className = 'rail-head';
  head.textContent = '图表 · FIGURES & TABLES';
  rail.prepend(head);
}

function docked() {
  return wide.matches && railSwitch && railSwitch.checked;
}

function syncRail() {
  if (!rail) return;
  const inRail = docked();
  for (const figure of plates) {
    const slot = slots.get(figure.id);
    if (inRail) { rail.append(figure); }
    else if (slot) { slot.append(figure); }
  }
}
syncRail();
wide.addEventListener('change', syncRail);
railSwitch?.addEventListener('change', syncRail);

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
  if (rail && rail.contains(figure) && docked()) {
    event.preventDefault();
    const tab = document.getElementById('fig-view-' + plates.indexOf(figure));
    if (tab && !tab.checked) tab.checked = true;
    figure.scrollIntoView({ block: 'start', behavior: 'smooth' });
    flash(figure);
  } else if (docked()) {
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
    const content = document.createElement('div');
    content.className = 'cite-body';
    content.textContent = entry.textContent.replace(/\s+/g, ' ').trim();
    pop.append(content);
    const doi = content.textContent.match(/10\.\d{4,9}\/[^\s"<>]+/);
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
