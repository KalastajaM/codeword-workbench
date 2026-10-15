/* Action tooltips preserve clicks; separate text-help icons can be pinned. */
(function () {
 'use strict';
 function installHelp(doc, win) {
  let active = null, pinned = false, closeTimer = null;
  const cancelClose = () => { win.clearTimeout(closeTimer); closeTimer = null; };
  function close() {
   cancelClose();
   if (active) { active.panel.hidden = true; if (active.interactive) active.button.setAttribute('aria-expanded', 'false'); }
   active = null; pinned = false;
  }
  function position() {
   if (!active) return;
   const {button, panel} = active, anchor = button.getBoundingClientRect();
   const width = doc.documentElement?.clientWidth || win.innerWidth;
   const height = doc.documentElement?.clientHeight || win.innerHeight, gap = 8;
   panel.style.maxWidth = Math.min(320, width - gap * 2) + 'px';
   panel.style.maxHeight = (height - gap * 2) + 'px';
   const bounds = panel.getBoundingClientRect();
   panel.style.left = Math.max(gap, Math.min(anchor.left, width - bounds.width - gap)) + 'px';
   panel.style.top = Math.max(gap, anchor.bottom + bounds.height + gap < height
    ? anchor.bottom + gap : anchor.top - bounds.height - gap) + 'px';
  }
  function open(item) {
   if (active !== item) { close(); active = item; }
   cancelClose(); item.panel.hidden = false; if (item.interactive) item.button.setAttribute('aria-expanded', 'true'); position();
  }
  const contains = target => active && (active.button.contains(target) || active.panel.contains(target));
  function scheduleClose() {
   cancelClose();
   if (!pinned) closeTimer = win.setTimeout(() => {
    if (active && doc.activeElement !== active.button) close();
   }, 180);
  }
  doc.querySelectorAll('[data-help]').forEach((button, index) => {
   const interactive = button.classList.contains('help-button');
   const panel = doc.createElement('div');
   panel.id = 'context-help-' + index; panel.className = 'help-popover'; panel.hidden = true;
   panel.setAttribute('role', 'tooltip'); panel.textContent = button.dataset.help;
   button.setAttribute('aria-describedby', panel.id);
   if (interactive) { button.setAttribute('aria-controls', panel.id); button.setAttribute('aria-expanded', 'false'); }
   doc.body.append(panel);
   const item = {button, panel, interactive};
   button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') open(item); });
   button.addEventListener('pointerleave', scheduleClose);
   button.addEventListener('focus', () => open(item));
   button.addEventListener('click', event => {
    if (!interactive) { close(); return; }
    event.preventDefault(); event.stopPropagation();
    if (active === item && pinned) close(); else { open(item); pinned = true; }
   });
   button.addEventListener('blur', event => { if (active === item && !panel.contains(event.relatedTarget)) close(); });
   panel.addEventListener('pointerenter', cancelClose);
   panel.addEventListener('pointerleave', scheduleClose);
  });
  doc.addEventListener('pointerdown', event => { if (active && !contains(event.target)) close(); });
  doc.addEventListener('keydown', event => {
   if (event.key === 'Escape' && active) { close(); event.preventDefault(); event.stopPropagation(); }
  }, true);
  win.addEventListener('resize', close);
  // Follow keyboard-focus scrolling, and allow long explanations to scroll internally.
  doc.addEventListener('scroll', event => {
   if (!active || active.panel.contains(event.target)) return;
   if (doc.activeElement === active.button) position(); else close();
  }, true);
  return {close};
 }
 if (typeof module !== 'undefined' && module.exports) module.exports = {installHelp};
 else installHelp(document, window);
})();
