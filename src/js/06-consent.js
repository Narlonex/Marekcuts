/* ==========================================================================
   06-consent.js — cookie consent (essential / analytics / marketing)
   --------------------------------------------------------------------------
   No analytics or marketing tool is bundled. Nothing beyond essential storage
   runs unless the visitor opts in. See README for how to plug a tool in via
   window.mcConsent.onGrant('analytics', fn).
   ========================================================================== */
(function () {
  'use strict';

  var App = window.MCApp;
  var qs = App.qs, qsa = App.qsa, on = App.on;

  var STORAGE_KEY = 'mc-consent';
  var VERSION = 1;                     /* bump to re-ask everyone after a policy change */
  var CATEGORIES = ['analytics', 'marketing'];
  var hooks = { analytics: [], marketing: [] };

  var stored = null;
  var openRef = null;   /* set once the DOM module boots, so mcConsent.open() works from anywhere */

  function readStore() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== VERSION) return null;
      return parsed;
    } catch (err) { return null; }
  }

  function writeStore(prefs) {
    var record = { version: VERSION, ts: new Date().toISOString() };
    CATEGORIES.forEach(function (c) { record[c] = !!prefs[c]; });
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
    } catch (err) { /* storage blocked: consent still applies for this page view */ }
    stored = record;
    apply();
  }

  /* run anything that was waiting for a category to be granted */
  function apply() {
    CATEGORIES.forEach(function (category) {
      if (stored && stored[category]) {
        hooks[category].splice(0).forEach(function (fn) {
          try { fn(); } catch (err) { console.error('[MarekCuts] consent hook failed', err); }
        });
      }
    });
  }

  var mcConsent = {
    /* read a stored preference */
    has: function (category) { return !!(stored && stored[category]); },
    /* run fn as soon as (or if) the category is granted */
    onGrant: function (category, fn) {
      if (CATEGORIES.indexOf(category) === -1) return;
      if (this.has(category)) { fn(); return; }
      hooks[category].push(fn);
    },
    /* programmatic control, handy for a future settings UI elsewhere */
    all: function () { return stored || { version: VERSION, analytics: false, marketing: false }; },
    open: function () { if (openRef) openRef(); },
    clear: function () {
      try { window.localStorage.removeItem(STORAGE_KEY); } catch (err) { /* ignore */ }
      stored = null;
    }
  };
  window.mcConsent = mcConsent;

  App.register(function () {
    var banner = qs('[data-consent-banner]');
    var modal = qs('[data-consent-modal]');
    if (!banner) return;

    var trap = modal ? App.focusTrap(modal) : null;

    function syncToggles() {
      if (!modal) return;
      qsa('[data-consent-cat]', modal).forEach(function (input) {
        input.checked = mcConsent.has(input.getAttribute('data-consent-cat'));
      });
    }

    function openModal() {
      if (!modal) return;
      syncToggles();
      var note = qs('[data-consent-note]', modal);
      if (note) note.hidden = true;
      modal.hidden = false;
      App.lockScroll();
      if (trap) trap.activate(qs('button[data-consent-close]', modal));
    }

    function closeModal() {
      if (!modal || modal.hidden) return;
      modal.hidden = true;
      App.unlockScroll();
      if (trap) trap.deactivate();
    }

    function hideBanner() { banner.hidden = true; }

    function decide(prefs) {
      writeStore(prefs);
      hideBanner();
      closeModal();
    }

    /* banner actions */
    on(qs('[data-consent-accept]', banner), 'click', function () {
      decide({ analytics: true, marketing: true });
    });
    on(qs('[data-consent-reject]', banner), 'click', function () {
      decide({ analytics: false, marketing: false });
    });
    on(qs('[data-consent-settings]', banner), 'click', openModal);

    /* modal actions */
    if (modal) {
      qsa('[data-consent-close]', modal).forEach(function (el) { on(el, 'click', closeModal); });
      on(qs('[data-consent-save]', modal), 'click', function () {
        var prefs = {};
        qsa('[data-consent-cat]', modal).forEach(function (input) {
          prefs[input.getAttribute('data-consent-cat')] = input.checked;
        });
        CATEGORIES.forEach(function (c) { if (prefs[c] === undefined) prefs[c] = false; });
        decide(prefs);
      });
      on(document, 'keydown', function (e) {
        if (e.key === 'Escape' && !modal.hidden) { e.preventDefault(); closeModal(); }
      });
    }

    /* footer link reopens the preferences */
    qsa('[data-consent-open]').forEach(function (btn) { on(btn, 'click', openModal); });

    openRef = openModal;

    /* initial state */
    stored = readStore();
    if (stored) hideBanner(); else banner.hidden = false;
    apply();
  });
})();
