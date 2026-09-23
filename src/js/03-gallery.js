/* ==========================================================================
   03-gallery.js — full-screen lightbox for the gallery grid
   Keyboard: Esc closes, Left/Right navigate. Touch: horizontal swipe.
   ========================================================================== */
(function () {
  'use strict';

  var App = window.MCApp;
  var qs = App.qs, qsa = App.qsa, on = App.on;

  App.register(function () {
    var box = qs('[data-lightbox]');
    var tiles = qsa('[data-gallery-item]');
    if (!box || !tiles.length) return;

    var img = qs('[data-lightbox-img]', box);
    var caption = qs('[data-lightbox-caption]', box);
    var counter = qs('[data-lightbox-counter]', box);
    var trap = App.focusTrap(box);
    var index = 0;

    function slide(i) {
      index = (i + tiles.length) % tiles.length;
      var tile = tiles[index];
      var full = tile.getAttribute('data-full');
      var active = qs('source[data-lang="' + App.lang() + '"]', tile);
      if (!full && active) full = active.getAttribute('srcset');
      if (!full) {
        var fallback = qs('img', tile);
        full = fallback ? (fallback.getAttribute('data-full') || fallback.getAttribute('src')) : '';
      }
      img.setAttribute('src', full || '');
      img.setAttribute('alt', tile.getAttribute('data-alt') || '');
      caption.textContent = tile.getAttribute('data-alt') || '';
      counter.textContent = App.t('gallery.counter', { current: index + 1, total: tiles.length });

      /* warm the neighbours so navigation feels instant */
      [tiles[(index + 1) % tiles.length], tiles[(index - 1 + tiles.length) % tiles.length]].forEach(function (t) {
        var src = t && t.getAttribute('data-full');
        if (src) { var pre = new Image(); pre.src = src; }
      });
    }

    function open(i, trigger) {
      box.hidden = false;
      App.lockScroll();
      slide(i);
      trap.activate(qs('button[data-lightbox-close]', box));
      box.setAttribute('data-trigger', trigger ? 'yes' : 'no');
    }

    function close() {
      if (box.hidden) return;
      box.hidden = true;
      App.unlockScroll();
      trap.deactivate();
      img.removeAttribute('src');
      img.setAttribute('alt', '');
    }

    function next() { slide(index + 1); }
    function prev() { slide(index - 1); }

    tiles.forEach(function (tile, i) {
      on(tile, 'click', function () { open(i, true); });
    });

    qsa('[data-lightbox-close]', box).forEach(function (b) { on(b, 'click', close); });
    on(qs('[data-lightbox-next]', box), 'click', next);
    on(qs('[data-lightbox-prev]', box), 'click', prev);

    on(document, 'keydown', function (e) {
      if (box.hidden) return;
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
    });

    /* touch swipe */
    var startX = null;
    on(box, 'touchstart', function (e) {
      if (e.touches.length === 1) startX = e.touches[0].clientX;
    }, { passive: true });
    on(box, 'touchend', function (e) {
      if (startX === null) return;
      var dx = (e.changedTouches[0] ? e.changedTouches[0].clientX : startX) - startX;
      startX = null;
      if (Math.abs(dx) < 45) return;
      if (dx < 0) next(); else prev();
    });

    /* keep the visible caption in the active language */
    App.onLangChange(function () {
      if (box.hidden) return;
      var tile = tiles[index];
      if (tile) {
        var alt = tile.getAttribute('data-alt-' + App.lang()) || tile.getAttribute('data-alt') || '';
        img.setAttribute('alt', alt);
        caption.textContent = alt;
      }
      counter.textContent = App.t('gallery.counter', { current: index + 1, total: tiles.length });
    });
  });
})();
