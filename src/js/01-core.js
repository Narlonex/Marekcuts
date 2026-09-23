/* ==========================================================================
   01-core.js — helpers, i18n engine, scroll reveal, focus management
   Reads the generated config from window.MC (built from content/*.json).
   ========================================================================== */
(function () {
  'use strict';

  var MC = window.MC || {};
  var App = (window.MCApp = window.MCApp || {});

  /* ---------- DOM helpers ---------- */
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  App.qs = qs;
  App.qsa = qsa;

  function on(el, type, fn, opts) { if (el) el.addEventListener(type, fn, opts); }
  App.on = on;

  /* ---------- i18n ------------------------------------------------------- */
  var STORAGE_KEY = 'mc-lang';
  var SUPPORTED = ['sk', 'en'];
  var lang = 'sk';
  var langListeners = [];

  function readStoredLang() {
    try {
      var v = window.localStorage.getItem(STORAGE_KEY);
      if (v && SUPPORTED.indexOf(v) !== -1) return v;
    } catch (err) { /* storage blocked - fall through */ }
    return null;
  }

  /* t('key') or t('key', {name: 'value'}) -> localised string */
  function t(key, vars) {
    var entry = MC.i18n ? MC.i18n[key] : null;
    var str = entry ? (entry[lang] || entry.sk || '') : key;
    if (vars) {
      str = str.replace(/\{(\w+)\}/g, function (m, k) {
        return vars[k] === undefined || vars[k] === null ? m : String(vars[k]);
      });
    }
    return str;
  }
  App.t = t;
  App.lang = function () { return lang; };
  App.onLangChange = function (fn) { langListeners.push(fn); };

  /* ---------- localised formatting ---------- */
  var LOCALE = { sk: 'sk-SK', en: 'en-GB' };
  function locale() { return LOCALE[lang] || 'en-GB'; }

  App.parseISO = function (value) {
    if (!value) return null;
    if (value instanceof Date) return value;
    var m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  };
  App.toISO = function (date) {
    var m = String(date.getMonth() + 1), d = String(date.getDate());
    return date.getFullYear() + '-' + (m.length < 2 ? '0' + m : m) + '-' + (d.length < 2 ? '0' + d : d);
  };

  /* ISO "2026-10-14" -> "14. októbra 2026" / "14 October 2026" */
  App.formatDate = function (value, opts) {
    var d = value instanceof Date ? value : App.parseISO(value);
    if (!d) return '';
    try {
      return new Intl.DateTimeFormat(locale(), opts || { day: 'numeric', month: 'long', year: 'numeric' }).format(d);
    } catch (err) { return App.toISO(d); }
  };
  App.formatMonth = function (date) {
    try { return new Intl.DateTimeFormat(locale(), { month: 'long', year: 'numeric' }).format(date); }
    catch (err) { return ''; }
  };
  /* Monday-first short weekday labels, localised through Intl */
  App.weekdayNames = function () {
    var out = [];
    try {
      var fmt = new Intl.DateTimeFormat(locale(), { weekday: 'short' });
      for (var i = 0; i < 7; i++) out.push(fmt.format(new Date(2024, 0, 1 + i)).replace('.', ''));
    } catch (err) { out = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']; }
    return out;
  };
  App.formatPrice = function (n) {
    try {
      return new Intl.NumberFormat(locale(), {
        style: 'currency', currency: MC.currency || 'EUR',
        minimumFractionDigits: 0, maximumFractionDigits: 0
      }).format(n);
    } catch (err) { return n + ' \u20AC'; }
  };
  App.formatDuration = function (minutes) { return minutes + ' min'; };

  /* ---------- applying the language ---------- */
  function applyStatic(root) {
    qsa('[data-i18n]', root).forEach(function (el) {
      var vars = null;
      if (el.hasAttribute('data-i18n-vars')) {
        try { vars = JSON.parse(el.getAttribute('data-i18n-vars')); } catch (err) { vars = null; }
      }
      el.textContent = t(el.getAttribute('data-i18n'), vars);
    });
    qsa('[data-i18n-attr]', root).forEach(function (el) {
      el.getAttribute('data-i18n-attr').split('|').forEach(function (pair) {
        var bits = pair.split(':');
        if (bits.length < 2) return;
        el.setAttribute(bits[0].trim(), t(bits.slice(1).join(':').trim()));
      });
    });
  }
  App.applyStatic = applyStatic;

  function setMeta(selector, value) {
    var el = qs(selector);
    if (el && value) el.setAttribute('content', value);
  }

  function applyDocument() {
    document.documentElement.lang = lang;
    document.documentElement.setAttribute('data-lang', lang);
    /* Sub-pages carry their own title key (data-title-key on <body>), so the
       generic homepage title never clobbers e.g. "Privacy Policy | Marek Cuts". */
    var titleKey = document.body.getAttribute('data-title-key');
    var pageTitle = titleKey
      ? t(titleKey) + ' | ' + (MC.businessName || '')
      : t('seo.title');
    document.title = pageTitle;
    setMeta('meta[name="description"]', t('seo.description'));
    setMeta('meta[property="og:title"]', titleKey ? pageTitle : t('seo.ogTitle'));
    setMeta('meta[property="og:description"]', t('seo.ogDescription'));
    setMeta('meta[property="og:locale"]', t('seo.locale'));
    setMeta('meta[property="og:locale:alternate"]', lang === 'sk' ? 'en_GB' : 'sk_SK');
    setMeta('meta[name="twitter:title"]', titleKey ? pageTitle : t('seo.ogTitle'));
    setMeta('meta[name="twitter:description"]', t('seo.ogDescription'));
  }

  function syncSwitcher() {
    qsa('[data-lang-btn]').forEach(function (btn) {
      var isActive = btn.getAttribute('data-lang-btn') === lang;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  function setLang(next) {
    if (SUPPORTED.indexOf(next) === -1 || next === lang) { syncSwitcher(); return; }
    lang = next;
    try { window.localStorage.setItem(STORAGE_KEY, lang); } catch (err) { /* ignore */ }
    applyDocument();
    applyStatic(document);
    syncSwitcher();
    document.dispatchEvent(new CustomEvent('mc:lang', { detail: { lang: lang } }));
    langListeners.forEach(function (fn) {
      try { fn(lang); } catch (err) { console.error('[MarekCuts] lang listener failed', err); }
    });
  }
  App.setLang = setLang;

  App.initI18n = function () {
    lang = readStoredLang() || MC.defaultLang || 'sk';
    applyDocument();
    applyStatic(document);
    syncSwitcher();
    qsa('[data-lang-btn]').forEach(function (btn) {
      on(btn, 'click', function () { setLang(btn.getAttribute('data-lang-btn')); });
    });
  };

  /* ---------- scroll reveal ---------- */
  App.initReveal = function () {
    var items = qsa('[data-reveal]');
    if (!items.length) return;
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-revealed'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          io.unobserve(entry.target);
        }
      });
      /* threshold 0 + a small negative bottom margin: fires as soon as any part
         crosses into view, and works for elements taller than the viewport
         (where a fractional threshold could never be reached). */
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0 });
    items.forEach(function (el) { io.observe(el); });
    /* safety net: never leave content hidden if the observer misbehaves */
    window.setTimeout(function () {
      items.forEach(function (el) {
        if (el.getBoundingClientRect().top < window.innerHeight) el.classList.add('is-revealed');
      });
    }, 1400);
  };

  /* ---------- focus management ---------- */
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  App.focusables = function (root) {
    return qsa(FOCUSABLE, root).filter(function (el) {
      return el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement;
    });
  };

  App.focusTrap = function (container) {
    var previous = null;
    function keydown(e) {
      if (e.key !== 'Tab') return;
      var f = App.focusables(container);
      if (!f.length) { e.preventDefault(); return; }
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    return {
      activate: function (initial) {
        previous = document.activeElement;
        document.addEventListener('keydown', keydown);
        var target = initial;
        /* A backdrop <div> is a valid click target but not focusable (tabIndex
           -1), so fall back to the first real focusable inside the dialog. */
        if (!target || typeof target.focus !== 'function' || target.tabIndex < 0) {
          target = App.focusables(container)[0] || container;
        }
        window.setTimeout(function () {
          if (target && target.focus) { try { target.focus(); } catch (err) {} }
        }, 30);
      },
      deactivate: function () {
        document.removeEventListener('keydown', keydown);
        if (previous && previous.focus) { try { previous.focus(); } catch (err) {} }
        previous = null;
      }
    };
  };

  /* ---------- body scroll lock (reference counted) ---------- */
  var locks = 0;
  App.lockScroll = function () { locks += 1; document.body.classList.add('is-locked'); };
  App.unlockScroll = function () {
    locks = Math.max(0, locks - 1);
    if (!locks) document.body.classList.remove('is-locked');
  };

  /* ---------- misc ---------- */
  App.prefersReducedMotion = function () {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  };

  App.smoothScrollTo = function (target) {
    var el = typeof target === 'string' ? qs(target) : target;
    if (!el) return;
    var header = qs('[data-header]');
    var offset = header ? header.offsetHeight : 0;
    var top = el.getBoundingClientRect().top + window.pageYOffset - offset + 1;
    window.scrollTo({ top: top < 0 ? 0 : top, behavior: App.prefersReducedMotion() ? 'auto' : 'smooth' });
  };

  App.debounce = function (fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { fn.apply(self, args); }, wait);
    };
  };

  /* only reveal the reviews carousel controls when it really is a carousel */
  App.isCarouselMode = function () {
    return window.matchMedia && window.matchMedia('(max-width: 1024px)').matches;
  };

  /* ---------- boot ---------- */
  var modules = [];
  App.register = function (fn) { modules.push(fn); };
  var booted = false;

  function boot() {
    if (booted) return;
    booted = true;
    /* Language before anything else: modules read App.lang() while they render. */
    try { App.initI18n(); }
    catch (err) { console.error('[MarekCuts] i18n failed to initialise', err); }
    for (var i = 0; i < modules.length; i++) {
      try { modules[i](); }
      catch (err) { console.error('[MarekCuts] module ' + i + ' failed', err); }
    }
    document.body.classList.remove('is-loading');
  }

  /*
    script.js is loaded with `defer`, so by the time this runs the document has
    finished parsing and readyState is already "interactive". Calling boot()
    straight away would fire before the other modules in this same file have had
    a chance to call App.register(), leaving the page un-initialised. So: wait for
    DOMContentLoaded while parsing, otherwise let the current task finish first.
  */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    window.setTimeout(boot, 0);
  }
})();
