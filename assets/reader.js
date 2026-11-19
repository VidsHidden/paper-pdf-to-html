const dialog = document.querySelector('dialog');
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
dialog.querySelector('.close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => {
  if (event.target === dialog) {
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right ||
        event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  }
});
dialog.addEventListener('close', () => enlarged.replaceChildren());
const languageMode = document.querySelector('#reading-language');
const validModes = new Set(['en', 'zh', 'both']);
function changeReadingMode(mode) {
  if (!validModes.has(mode)) return;
  const anchor = [...document.querySelectorAll('article .parallel')].find(block => block.getBoundingClientRect().bottom > 12);
  const before = anchor?.getBoundingClientRect().top;
  document.body.dataset.mode = mode;
  document.documentElement.lang = mode === 'en' ? 'en' : 'zh-Hans';
  languageMode.value = mode;
  if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - before);
}
languageMode?.addEventListener('change', () => changeReadingMode(languageMode.value));
