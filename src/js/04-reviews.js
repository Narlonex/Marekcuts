/* ==========================================================================
   04-reviews.js — desktop grid becomes a snap carousel on smaller screens
   ========================================================================== */
(function () {
  'use strict';

  var App = window.MCApp;
  var qs = App.qs, qsa = App.qsa, on = App.on;

  App.register(function () {
    var viewport = qs('[data-reviews-viewport]');
    var track = qs('[data-reviews-track]');
    var controls = qs('[data-reviews-controls]');
    var dotsBox = qs('[data-reviews-dots]');
    if (!viewport || !track || !controls) return;

    var cards = qsa('.review', track);
    if (!cards.length) return;

    var dots = [];

    function buildDots() {
      if (!dotsBox) return;
      dotsBox.textContent = '';
      dots = cards.map(function (card, i) {
        var dot = document.createElement('button');
        dot.type = 'button';
        dot.className = 'reviews__dot';
        dot.setAttribute('role', 'tab');
        dot.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
        dot.setAttribute('aria-label', App.t('reviews.goTo', { n: i + 1 }));
        on(dot, 'click', function () { goTo(i); });
        dotsBox.appendChild(dot);
        return dot;
      });
    }

    function refreshDots() {
      dots.forEach(function (dot, i) {
        dot.setAttribute('aria-label', App.t('reviews.goTo', { n: i + 1 }));
      });
    }

    function currentIndex() {
      var center = viewport.scrollLeft + viewport.clientWidth / 2;
      var best = 0, bestDist = Infinity;
      cards.forEach(function (card, i) {
        var mid = card.offsetLeft + card.offsetWidth / 2;
        var dist = Math.abs(mid - center);
        if (dist < bestDist) { bestDist = dist; best = i; }
      });
      return best;
    }

    function goTo(i) {
      var card = cards[Math.max(0, Math.min(cards.length - 1, i))];
      if (!card) return;
      viewport.scrollTo({
        left: card.offsetLeft - (viewport.clientWidth - card.offsetWidth) / 2,
        behavior: App.prefersReducedMotion() ? 'auto' : 'smooth'
      });
    }

    function sync() {
      var i = currentIndex();
      dots.forEach(function (dot, n) { dot.setAttribute('aria-selected', n === i ? 'true' : 'false'); });
    }

    function refreshMode() {
      var carousel = App.isCarouselMode();
      controls.hidden = !carousel;
      if (carousel) { buildDots(); sync(); }
    }

    on(qs('[data-reviews-next]'), 'click', function () { goTo(currentIndex() + 1); });
    on(qs('[data-reviews-prev]'), 'click', function () { goTo(currentIndex() - 1); });
    on(viewport, 'scroll', App.debounce(sync, 90), { passive: true });
    on(window, 'resize', App.debounce(refreshMode, 160));

    App.onLangChange(refreshDots);

    refreshMode();
  });
})();
