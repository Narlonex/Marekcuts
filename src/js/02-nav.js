/* ==========================================================================
   02-nav.js — sticky header, scroll spy, animated in-page navigation
   ========================================================================== */
(function () {
  'use strict';

  var App = window.MCApp;
  var qs = App.qs, qsa = App.qsa, on = App.on;

  var header = qs('[data-header]');
  var HIDE_AFTER = 420;

  /* ---------- header state ---------- */
  function initHeader() {
    if (!header) return;
    var lastY = window.pageYOffset;
    var ticking = false;
    var isDrawerOpen = function () { return document.body.classList.contains('is-locked'); };

    function update() {
      var y = window.pageYOffset;
      header.classList.toggle('is-scrolled', y > 12);

      /* retract the header on small screens while scrolling down */
      var compact = window.matchMedia && window.matchMedia('(max-width: 1024px)').matches;
      if (compact && !isDrawerOpen()) {
        if (y > HIDE_AFTER && y > lastY + 4) header.classList.add('is-hidden');
        else if (y < lastY - 4 || y <= HIDE_AFTER) header.classList.remove('is-hidden');
      } else {
        header.classList.remove('is-hidden');
      }
      lastY = y;
      ticking = false;
    }

    function request() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }

    on(window, 'scroll', request, { passive: true });
    on(window, 'resize', App.debounce(update, 150));
    update();
  }

  /* ---------- scroll spy ---------- */
  function initScrollSpy() {
    var links = qsa('.nav__link[href^="#"]');
    if (!links.length || !('IntersectionObserver' in window)) return;

    var map = {};
    var sections = [];
    links.forEach(function (link) {
      var id = link.getAttribute('href').slice(1);
      var target = id ? document.getElementById(id) : null;
      if (target) { map[id] = link; sections.push(target); }
    });
    if (!sections.length) return;

    function activate(id) {
      links.forEach(function (l) { l.classList.remove('is-active'); });
      if (map[id]) {
        map[id].classList.add('is-active');
        map[id].setAttribute('aria-current', 'true');
      }
      links.forEach(function (l) {
        if (l !== map[id]) l.removeAttribute('aria-current');
      });
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) activate(entry.target.id);
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });

    sections.forEach(function (s) { io.observe(s); });

    /* at the very top nothing has crossed the midpoint yet — highlight Home */
    on(window, 'scroll', App.debounce(function () {
      if (window.pageYOffset < 80) activate(sections[0].id);
    }, 120), { passive: true });
    if (window.pageYOffset < 80) activate(sections[0].id);
  }

  /* ---------- in-page navigation ---------- */
  function initSmoothLinks() {
    on(document, 'click', function (e) {
      var link = e.target.closest ? e.target.closest('a[href^="#"]') : null;
      if (!link) return;
      var hash = link.getAttribute('href');
      if (!hash || hash === '#' || hash.length < 2) return;
      var target = document.getElementById(hash.slice(1));
      if (!target) return;

      e.preventDefault();
      var drawerWasOpen = document.body.classList.contains('is-locked');
      if (drawerWasOpen) closeDrawer();
      /* wait for the drawer close transition before scrolling */
      window.setTimeout(function () { App.smoothScrollTo(target); }, drawerWasOpen ? 240 : 0);
      if (window.history && window.history.pushState) window.history.pushState(null, '', hash);
    });
  }

  /* ---------- mobile drawer ---------- */
  var drawer = qs('[data-drawer]');
  var burger = qs('[data-burger]');
  var trap = null;

  function openDrawer() {
    if (!drawer || !burger) return;
    drawer.hidden = false;
    burger.setAttribute('aria-expanded', 'true');
    burger.setAttribute('aria-label', App.t('nav.closeMenu'));
    App.lockScroll();
    if (!trap) trap = App.focusTrap(drawer);
    trap.activate(qs('[data-drawer-close]', drawer));
  }

  function closeDrawer() {
    if (!drawer || !burger) return;
    if (drawer.hidden) return;
    drawer.hidden = true;
    burger.setAttribute('aria-expanded', 'false');
    burger.setAttribute('aria-label', App.t('nav.openMenu'));
    App.unlockScroll();
    if (trap) { trap.deactivate(); }
  }

  function initDrawer() {
    if (!drawer || !burger) return;
    on(burger, 'click', function () {
      if (drawer.hidden) openDrawer(); else closeDrawer();
    });
    qsa('[data-drawer-close]', drawer).forEach(function (btn) { on(btn, 'click', closeDrawer); });
    qsa('.drawer__link', drawer).forEach(function (link) { on(link, 'click', function () { window.setTimeout(closeDrawer, 10); }); });
    on(document, 'keydown', function (e) { if (e.key === 'Escape') closeDrawer(); });
    on(window, 'resize', App.debounce(function () {
      if (!window.matchMedia('(max-width: 1024px)').matches) closeDrawer();
    }, 160));
    /* keep the burger label in sync with the current language */
    App.onLangChange(function () {
      burger.setAttribute('aria-label', App.t(drawer.hidden ? 'nav.openMenu' : 'nav.closeMenu'));
    });
  }

  App.register(function () {
    App.initReveal();
    initHeader();
    initScrollSpy();
    initSmoothLinks();
    initDrawer();
  });
})();
