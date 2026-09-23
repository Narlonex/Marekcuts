/* ==========================================================================
   05-booking.js — DEMO booking wizard
   --------------------------------------------------------------------------
   NOTHING here talks to a network. submitBooking() is a clearly named
   simulation, and the seam for a real backend is marked further down.
   Availability comes from content/availability.json (demo data).
   ========================================================================== */
(function () {
  'use strict';

  var App = window.MCApp;
  var qs = App.qs, qsa = App.qsa, on = App.on;

  var AVAIL = (window.MC && window.MC.availability) || {};
  var SERVICES = (window.MC && window.MC.services) || [];
  var MAX_NOTE = 500;
  var STORAGE_KEY = 'mc-booking';
  var TOTAL_STEPS = 6;
  var SIMULATED_LATENCY_MS = 650;   /* demo only — makes the button feel real */

  var state = {
    step: 1,
    serviceId: null,
    date: null,       /* ISO "2026-10-14" */
    time: null,       /* "16:30" */
    name: '', email: '', phone: '', note: '',
    consent: false
  };

  /* ---------- small utilities ---------- */
  function pad(n) { return n < 10 ? '0' + n : String(n); }

  function toMinutes(hhmm) {
    var parts = String(hhmm).split(':');
    return Number(parts[0]) * 60 + Number(parts[1] || 0);
  }
  function fromMinutes(total) { return pad(Math.floor(total / 60)) + ':' + pad(total % 60); }

  function today() {
    var d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  /* deterministic pseudo-random so the same date always looks the same */
  function hashString(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ---------- availability engine ---------------------------------------- */
  function isClosedWeekday(date) {
    return (AVAIL.closedWeekdays || []).indexOf(date.getDay()) !== -1;
  }
  function isBlackout(iso) {
    return (AVAIL.blackoutDates || []).indexOf(iso) !== -1;
  }
  function isPast(date) {
    return date < today();
  }
  function withinWindow(date) {
    var limit = new Date(today());
    limit.setDate(limit.getDate() + (AVAIL.windowDays || 90));
    return date <= limit;
  }

  /* every slot the shop could offer on a given day, before bookings */
  function allSlots() {
    var out = [];
    var start = toMinutes(AVAIL.slotStart || '09:00');
    var end = toMinutes(AVAIL.slotEnd || '18:00');
    var step = AVAIL.slotStepMinutes || 30;
    for (var m = start; m <= end; m += step) out.push(fromMinutes(m));
    return out;
  }

  /* [{time, available}] for one ISO date; empty when the day is closed */
  function getAvailableTimes(iso) {
    var date = App.parseISO(iso);
    if (!date || isClosedWeekday(date) || isBlackout(iso) || isPast(date) || !withinWindow(date)) return [];

    var explicit = (AVAIL.explicitUnavailable || {})[iso] || [];
    var ratio = (AVAIL.weekdayBusyRatio || {})[String(date.getDay())];
    if (ratio === undefined || ratio === null) ratio = AVAIL.busyRatio || 0;
    var rand = mulberry32((AVAIL.seed || 1) + hashString(iso));

    var leadLimit = null;
    if (App.toISO(today()) === iso) {
      var now = new Date();
      leadLimit = now.getHours() * 60 + now.getMinutes() + (AVAIL.leadTimeMinutes || 0);
    }

    var slots = allSlots().map(function (time) {
      var mins = toMinutes(time);
      var available = true;
      if (leadLimit !== null && mins < leadLimit) available = false;
      if (explicit.indexOf(time) !== -1) available = false;
      if (available && rand() < ratio) available = false;
      return { time: time, available: available };
    });

    /* if the busy rule happened to wipe out the whole day, re-open a few slots
       so an "open" day never renders as completely empty in the demo */
    if (slots.length && !slots.some(function (s) { return s.available; })) {
      slots[0].available = true;
      if (slots[2]) slots[2].available = true;
      if (slots[4]) slots[4].available = true;
    }
    return slots;
  }

  /* dates inside the window that still have at least one free slot */
  function getAvailableDates() {
    var out = [];
    var cursor = new Date(today());
    var limit = new Date(today());
    limit.setDate(limit.getDate() + (AVAIL.windowDays || 90));
    while (cursor <= limit) {
      var iso = App.toISO(cursor);
      var slots = getAvailableTimes(iso);
      var free = slots.filter(function (s) { return s.available; });
      if (free.length) out.push(iso);
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }

  /* ---------- calendar --------------------------------------------------- */
  var cal = {
    cursor: null,        /* first day of the displayed month */
    focusISO: null,      /* roving tabindex target */
    grid: null, monthEl: null, weekdaysEl: null
  };

  function monthStart(date) { return new Date(date.getFullYear(), date.getMonth(), 1); }
  function addMonths(date, n) { return new Date(date.getFullYear(), date.getMonth() + n, 1); }

  function dayStatus(iso) {
    var date = App.parseISO(iso);
    if (!date) return 'past';
    if (isPast(date) || !withinWindow(date)) return 'past';
    if (isClosedWeekday(date) || isBlackout(iso)) return 'closed';
    var free = getAvailableTimes(iso).filter(function (s) { return s.available; });
    return free.length ? 'available' : 'full';
  }

  function statusLabel(status) {
    if (status === 'available') return App.t('booking.dayAvailable');
    if (status === 'full') return App.t('booking.dayFull');
    if (status === 'closed') return App.t('booking.dayClosed');
    return App.t('booking.dayPast');
  }

  function buildCell(date) {
    var iso = App.toISO(date);
    var status = dayStatus(iso);
    var disabled = status !== 'available';
    var isSelected = state.date === iso;
    var cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'cal__day';
    cell.setAttribute('role', 'gridcell');
    cell.setAttribute('data-iso', iso);
    cell.textContent = String(date.getDate());

    if (isSelected) cell.classList.add('cal__day--selected');
    if (App.toISO(today()) === iso) {
      cell.classList.add('cal__day--today');
      cell.setAttribute('aria-current', 'date');
    }
    if (disabled) cell.setAttribute('aria-disabled', 'true');

    var parts = [App.formatDate(date, { day: 'numeric', month: 'long', year: 'numeric' })];
    if (isSelected) parts.push(App.t('booking.daySelected'));
    if (App.toISO(today()) === iso) parts.push(App.t('booking.dayToday'));
    parts.push(statusLabel(status));
    cell.setAttribute('aria-label', App.t('booking.dayLabel', { date: parts[0], status: parts.slice(1).join(', ') }));

    var roving = cal.focusISO === iso || (!cal.focusISO && !disabled && isSameMonth(date, cal.cursor));
    cell.tabIndex = roving ? 0 : -1;

    if (!disabled) {
      on(cell, 'click', function () { selectDate(iso); });
    } else {
      on(cell, 'click', function (e) { e.preventDefault(); });
    }
    return cell;
  }

  function isSameMonth(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
  }

  function renderCalendar() {
    if (!cal.grid) return;
    var year = cal.cursor.getFullYear();
    var month = cal.cursor.getMonth();

    cal.monthEl.textContent = App.formatMonth(cal.cursor);
    cal.monthEl.setAttribute('data-iso', App.toISO(cal.cursor));
    qs('[data-calendar]').setAttribute('aria-label', App.t('booking.calendarLabel', { month: App.formatMonth(cal.cursor) }));

    /* Monday-first labels */
    cal.weekdaysEl.textContent = '';
    App.weekdayNames().forEach(function (name) {
      var span = document.createElement('span');
      span.textContent = name;
      cal.weekdaysEl.appendChild(span);
    });

    cal.grid.textContent = '';
    var firstOfMonth = new Date(year, month, 1);
    var lead = (firstOfMonth.getDay() + 6) % 7;        /* Monday = 0 */
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    var cellIndex = 0;
    var cellCount = Math.ceil((lead + daysInMonth) / 7) * 7;

    for (var i = 0; i < cellCount; i += 7) {
      var row = document.createElement('div');
      row.className = 'cal__row';
      row.setAttribute('role', 'row');
      for (var j = 0; j < 7; j++) {
        cellIndex = i + j;
        if (cellIndex < lead || cellIndex >= lead + daysInMonth) {
          var blank = document.createElement('span');
          blank.className = 'cal__day cal__day--empty';
          blank.setAttribute('role', 'gridcell');
          blank.setAttribute('aria-hidden', 'true');
          row.appendChild(blank);
        } else {
          row.appendChild(buildCell(new Date(year, month, cellIndex - lead + 1)));
        }
      }
      cal.grid.appendChild(row);
    }

    /* keep the arrows honest about where the window ends */
    var windowEnd = new Date(today());
    windowEnd.setDate(windowEnd.getDate() + (AVAIL.windowDays || 90));
    var prev = qs('[data-cal-prev]');
    var next = qs('[data-cal-next]');
    var atStart = cal.cursor <= monthStart(today());
    var atEnd = monthStart(windowEnd) <= cal.cursor;
    if (prev) prev.disabled = atStart;
    if (next) next.disabled = atEnd;
  }

  /* arrow-key navigation within the grid */
  function moveFocus(fromISO, deltaDays) {
    var date = App.parseISO(fromISO);
    if (!date) date = today();
    date.setDate(date.getDate() + deltaDays);
    var iso = App.toISO(date);
    if (!isSameMonth(date, cal.cursor)) cal.cursor = monthStart(date);
    cal.focusISO = iso;
    renderCalendar();
    var target = qs('.cal__day[data-iso="' + iso + '"]', cal.grid);
    if (target) target.focus();
  }

  function initCalendar() {
    var root = qs('[data-calendar]');
    if (!root) return;
    cal.grid = qs('[data-cal-grid]', root);
    cal.monthEl = qs('[data-cal-month]', root);
    cal.weekdaysEl = qs('[data-cal-weekdays]', root);
    cal.cursor = monthStart(today());

    on(qs('[data-cal-prev]', root), 'click', function () {
      cal.cursor = addMonths(cal.cursor, -1);
      renderCalendar();
    });
    on(qs('[data-cal-next]', root), 'click', function () {
      cal.cursor = addMonths(cal.cursor, 1);
      renderCalendar();
    });

    on(cal.grid, 'keydown', function (e) {
      var iso = e.target && e.target.getAttribute ? e.target.getAttribute('data-iso') : null;
      if (!iso) return;
      var handled = true;
      if (e.key === 'ArrowLeft') moveFocus(iso, -1);
      else if (e.key === 'ArrowRight') moveFocus(iso, 1);
      else if (e.key === 'ArrowUp') moveFocus(iso, -7);
      else if (e.key === 'ArrowDown') moveFocus(iso, 7);
      else if (e.key === 'Home') moveFocus(iso, -((App.parseISO(iso).getDay() + 6) % 7));
      else if (e.key === 'End') moveFocus(iso, 6 - ((App.parseISO(iso).getDay() + 6) % 7));
      else if (e.key === 'PageUp') { cal.cursor = addMonths(cal.cursor, -1); renderCalendar(); }
      else if (e.key === 'PageDown') { cal.cursor = addMonths(cal.cursor, 1); renderCalendar(); }
      else if (e.key === 'Enter' || e.key === ' ') {
        var status = dayStatus(iso);
        if (status === 'available') { selectDate(iso); }
      } else handled = false;
      if (handled) e.preventDefault();
    });

    renderCalendar();
  }

  /* ---------- time slots ------------------------------------------------- */
  function renderTimes() {
    var wrap = qs('[data-times]');
    var grid = qs('[data-times-grid]');
    var label = qs('[data-times-label]');
    var hint = qs('[data-times-hint]');
    var empty = qs('[data-times-empty]');
    if (!wrap || !grid) return;

    if (!state.date) {
      wrap.hidden = true;
      if (empty) empty.hidden = true;
      if (hint) hint.hidden = false;
      grid.textContent = '';
      return;
    }
    if (hint) hint.hidden = true;

    var slots = getAvailableTimes(state.date);
    var free = slots.filter(function (s) { return s.available; });

    if (!free.length) {
      wrap.hidden = true;
      if (empty) empty.hidden = false;
      grid.textContent = '';
      return;
    }
    if (empty) empty.hidden = true;
    wrap.hidden = false;
    if (label) label.textContent = App.t('booking.availableTimesFor', { date: App.formatDate(state.date) });

    grid.textContent = '';
    slots.forEach(function (slot) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'slot';
      btn.textContent = slot.time;
      btn.setAttribute('data-time', slot.time);
      if (!slot.available) {
        btn.setAttribute('aria-disabled', 'true');
        btn.tabIndex = -1;
      } else {
        on(btn, 'click', function () { selectTime(slot.time); });
      }
      if (state.time === slot.time) btn.classList.add('is-selected');
      grid.appendChild(btn);
    });
  }

  /* ---------- selection -------------------------------------------------- */
  function serviceById(id) {
    for (var i = 0; i < SERVICES.length; i++) if (SERVICES[i].id === id) return SERVICES[i];
    return null;
  }

  function selectService(id) {
    state.serviceId = id;
    qsa('[data-service-option]').forEach(function (btn) {
      var chosen = btn.getAttribute('data-service-option') === id;
      btn.classList.toggle('is-selected', chosen);
      btn.setAttribute('aria-pressed', chosen ? 'true' : 'false');
    });
    clearError('service');
    updateRecap();
    save();
  }

  function selectDate(iso) {
    state.date = iso;
    /* the previously picked time may not exist on the new day */
    var slots = getAvailableTimes(iso).filter(function (s) { return s.available; });
    if (state.time && !slots.some(function (s) { return s.time === state.time; })) state.time = null;
    cal.focusISO = iso;
    renderCalendar();
    renderTimes();
    clearError('date');
    updateRecap();
    save();
  }

  function selectTime(time) {
    state.time = time;
    qsa('.slot', qs('[data-times-grid]')).forEach(function (btn) {
      btn.classList.toggle('is-selected', btn.getAttribute('data-time') === time);
    });
    clearError('time');
    updateRecap();
    save();
  }

  /* ---------- recap, summary -------------------------------------------- */
  function updateRecap() {
    var service = serviceById(state.serviceId);
    var a = qs('[data-recap-service]');
    var b = qs('[data-recap-date]');
    var c = qs('[data-recap-time]');
    if (a) a.textContent = service ? service.name[App.lang()] || service.name.sk : App.t('booking.placeholderValue');
    if (b) b.textContent = state.date ? App.formatDate(state.date) : App.t('booking.placeholderValue');
    if (c) c.textContent = state.time || App.t('booking.placeholderValue');
  }

  function summaryRows(withEdit) {
    var service = serviceById(state.serviceId);
    var rows = [
      ['booking.summaryService', service ? (service.name[App.lang()] || service.name.sk) : '', 1],
      ['booking.summaryDate', state.date ? App.formatDate(state.date) : '', 2],
      ['booking.summaryTime', state.time || '', 3],
      ['booking.summaryDuration', service ? App.formatDuration(service.duration) : '', null],
      ['booking.summaryPrice', service ? App.formatPrice(service.price) : '', null],
      ['booking.summaryCustomer', state.name, 4],
      ['booking.summaryEmail', state.email, 4],
      ['booking.summaryPhone', state.phone, 4]
    ];
    if (state.note) rows.push(['booking.summaryNote', state.note, 4]);
    return rows.filter(function (r) { return r[1]; }).map(function (r) {
      return { labelKey: r[0], value: r[1], step: r[2], edit: withEdit && r[2] };
    });
  }

  function renderSummary(target, withEdit) {
    if (!target) return;
    target.textContent = '';
    summaryRows(withEdit).forEach(function (row) {
      var wrap = document.createElement('div');
      wrap.className = 'summary__row';
      var dt = document.createElement('dt');
      dt.setAttribute('data-i18n', row.labelKey);
      dt.textContent = App.t(row.labelKey);
      var dd = document.createElement('dd');
      dd.textContent = row.value;
      wrap.appendChild(dt);
      wrap.appendChild(dd);
      if (row.edit) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'summary__edit';
        btn.textContent = App.t('booking.edit');
        btn.setAttribute('data-edit-step', String(row.edit));
        btn.setAttribute('aria-label', App.t('booking.edit') + ': ' + App.t(row.labelKey));
        on(btn, 'click', function () { goToStep(row.edit); });
        wrap.appendChild(btn);
      }
      target.appendChild(wrap);
    });
  }

  /* ---------- validation ------------------------------------------------- */
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/;

  function phoneDigits(value) { return String(value || '').replace(/[^0-9]/g, ''); }
  function fieldEl(name) { return qs('[data-field="' + name + '"]'); }
  function errorEl(name) { return qs('[data-error="' + name + '"]'); }

  function showError(name, message) {
    var box = errorEl(name), field = fieldEl(name);
    if (box) { box.textContent = message; box.hidden = false; }
    if (field) field.setAttribute('aria-invalid', 'true');
  }
  function clearError(name) {
    var box = errorEl(name), field = fieldEl(name);
    if (box) { box.hidden = true; box.textContent = ''; }
    if (field) field.removeAttribute('aria-invalid');
  }

  /* the single source of truth for "can this booking be submitted" */
  function validateBooking() {
    var errors = {};
    if (!state.serviceId) errors.service = App.t('booking.errService');
    if (!state.date) errors.date = App.t('booking.errDate');
    if (!state.time) errors.time = App.t('booking.errTime');

    if (String(state.name || '').trim().length < 2) errors.name = App.t('booking.errName');
    if (!EMAIL_RE.test(String(state.email || '').trim())) errors.email = App.t('booking.errEmail');
    if (phoneDigits(state.phone).length < 9) errors.phone = App.t('booking.errPhone');
    if (String(state.note || '').length > MAX_NOTE) errors.note = App.t('booking.errNote', { max: MAX_NOTE });
    if (!state.consent) errors.consent = App.t('booking.errConsent');

    return { valid: Object.keys(errors).length === 0, errors: errors };
  }

  function reportErrors(errors) {
    var keys = Object.keys(errors);
    if (!keys.length) return true;
    keys.forEach(function (k) { showError(k, errors[k]); });
    var first = fieldEl(keys[0]) || errorEl(keys[0]);
    if (first && first.focus) { try { first.focus(); } catch (err) {} }
    announce(App.t('booking.errSummary'));
    return false;
  }

  /* ---------- demo submission ------------------------------------------- */
  /* The ONLY place that would talk to a backend. It deliberately just waits and
     resolves: this site is static and no request is ever made. */
  function simulateSubmit(payload) {
    return new Promise(function (resolve) {
      window.setTimeout(function () {
        resolve({ ok: true, demo: true, reference: 'DEMO-' + Date.now().toString(36).toUpperCase() });
      }, App.prefersReducedMotion() ? 60 : SIMULATED_LATENCY_MS);
    });
  }

  function submitBooking() {
    var result = validateBooking();
    if (!result.valid) {
      /* send the user back to whichever earlier step is incomplete */
      if (result.errors.service) { goToStep(1); reportErrors({ service: result.errors.service }); return Promise.resolve(false); }
      if (result.errors.date) { goToStep(2); reportErrors({ date: result.errors.date }); return Promise.resolve(false); }
      if (result.errors.time) { goToStep(3); reportErrors({ time: result.errors.time }); return Promise.resolve(false); }
      reportErrors(result.errors);
      return Promise.resolve(false);
    }

    var payload = {
      service: state.serviceId, date: state.date, time: state.time,
      name: String(state.name).trim(), email: String(state.email).trim(),
      phone: String(state.phone).trim(), note: String(state.note || '').trim(), consent: true
    };

    var nextBtn = qs('[data-wizard-next]');
    var label = qs('[data-wizard-next-label]');
    var restore = label ? label.textContent : '';
    if (nextBtn) nextBtn.setAttribute('aria-disabled', 'true');
    if (label) label.textContent = App.t('booking.submitting');

    /* TODO (real backend): swap simulateSubmit for
       fetch('/api/booking', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                               body: JSON.stringify(payload) })
       and handle errors. Nothing else in this file has to change. */
    return simulateSubmit(payload).then(function () {
      if (nextBtn) nextBtn.removeAttribute('aria-disabled');
      if (label) label.textContent = restore;
      submitted = true;
      renderSummary(qs('[data-summary-done]'), false);
      goToStep(6);
      clearSaved();
      return true;
    });
  }

  /* ---------- steps ------------------------------------------------------ */
  var submitted = false;

  function canEnter(step) {
    if (step <= 1) return true;
    if (!state.serviceId) return false;
    if (step === 2) return true;
    if (!state.date) return false;
    if (step === 3) return true;
    if (!state.time) return false;
    if (step === 4) return true;
    if (!validateBooking().valid) return false;
    if (step === 5) return true;
    return submitted;
  }

  function announce(message) {
    var live = qs('[data-step-status]');
    if (live) live.textContent = message;
  }

  function goToStep(step) {
    step = Math.max(1, Math.min(TOTAL_STEPS, step));
    if (step > state.step && !canEnter(step)) {
      /* say what is missing instead of silently refusing */
      var errors = validateBooking().errors;
      if (step >= 4 && Object.keys(errors).length) reportErrors(errors);
      return false;
    }
    state.step = step;
    refreshStep();
    save();
    return true;
  }

  function refreshStep() {
    qsa('[data-step]').forEach(function (el) {
      var active = Number(el.getAttribute('data-step')) === state.step;
      el.classList.toggle('is-active', active);
      el.hidden = !active;
    });

    qsa('[data-stepper-item]').forEach(function (item) {
      var n = Number(item.getAttribute('data-stepper-item'));
      item.classList.toggle('is-active', n === state.step);
      item.classList.toggle('is-done', n < state.step);
      item.classList.toggle('is-locked', n > state.step && !canEnter(n));
    });

    /* On small screens the stepper scrolls horizontally, so pull the current
       step into view instead of leaving it off the right edge. */
    var stepper = qs('.stepper');
    var activeItem = qs('[data-stepper-item].is-active');
    if (stepper && activeItem && stepper.scrollWidth > stepper.clientWidth + 1) {
      var sBox = stepper.getBoundingClientRect();
      var iBox = activeItem.getBoundingClientRect();
      var delta = (iBox.left - sBox.left) - (stepper.clientWidth - iBox.width) / 2;
      var target = Math.max(0, Math.min(stepper.scrollWidth - stepper.clientWidth,
                                            stepper.scrollLeft + delta));
      if (Math.abs(target - stepper.scrollLeft) > 1) {
        if (stepper.scrollTo && !App.prefersReducedMotion()) {
          stepper.scrollTo({ left: target, behavior: 'smooth' });
        } else {
          stepper.scrollLeft = target;
        }
      }
    }

    var back = qs('[data-wizard-back]');
    var next = qs('[data-wizard-next]');
    var label = qs('[data-wizard-next-label]');
    var nav = qs('[data-wizard-nav]');

    if (nav) nav.hidden = state.step === 6;
    if (back) back.hidden = state.step === 1;
    if (next) next.hidden = state.step === 6;
    if (label) label.textContent = state.step === 5 ? App.t('booking.confirm') : App.t('booking.continue');

    if (state.step === 5) renderSummary(qs('[data-summary]'), true);
    updateRecap();

    announce(App.t('booking.stepPrefix') + ' ' + state.step + ' ' + App.t('booking.stepOf') + ' ' +
             TOTAL_STEPS + ': ' + App.t('booking.step' + state.step));

    if (window.history && window.history.replaceState && window.location.hash.indexOf('#booking') === 0) {
      window.history.replaceState(null, '', '#booking/step-' + state.step);
    }
  }

  /* ---------- session persistence --------------------------------------- */
  /* sessionStorage (not localStorage): the demo booking disappears as soon as
     the tab closes, so nothing lingers on a shared computer. */
  function save() {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        serviceId: state.serviceId, date: state.date, time: state.time,
        name: state.name, email: state.email, phone: state.phone,
        note: state.note, consent: state.consent,
        step: Math.min(5, state.step)
      }));
    } catch (err) { /* storage blocked is fine */ }
  }
  function clearSaved() {
    try { window.sessionStorage.removeItem(STORAGE_KEY); } catch (err) { /* ignore */ }
  }
  function restore() {
    var raw = null;
    try { raw = window.sessionStorage.getItem(STORAGE_KEY); } catch (err) { raw = null; }
    if (!raw) return false;
    var parsed;
    try { parsed = JSON.parse(raw); } catch (err) { return false; }
    if (!parsed || typeof parsed !== 'object') return false;
    ['serviceId', 'date', 'time', 'name', 'email', 'phone', 'note'].forEach(function (k) {
      if (typeof parsed[k] === 'string' || parsed[k] === null) state[k] = parsed[k];
    });
    state.consent = !!parsed.consent;
    /* never restore the final step — no booking has actually been made */
    state.step = Math.min(5, Math.max(1, Number(parsed.step) || 1));
    return !!(state.serviceId || state.date || state.time || state.name);
  }

  /* ---------- single-field validation (used on blur) -------------------- */
  function validateField(name) {
    if (name === 'name') return String(state.name || '').trim().length < 2 ? App.t('booking.errName') : null;
    if (name === 'email') return EMAIL_RE.test(String(state.email || '').trim()) ? null : App.t('booking.errEmail');
    if (name === 'phone') return phoneDigits(state.phone).length < 9 ? App.t('booking.errPhone') : null;
    if (name === 'note') return String(state.note || '').length > MAX_NOTE ? App.t('booking.errNote', { max: MAX_NOTE }) : null;
    if (name === 'consent') return state.consent ? null : App.t('booking.errConsent');
    return null;
  }

  function revalidateVisible() {
    ['name', 'email', 'phone', 'note', 'consent'].forEach(function (name) {
      var box = errorEl(name);
      if (box && !box.hidden) {
        var msg = validateField(name);
        if (msg) showError(name, msg); else clearError(name);
      }
    });
  }

  /* ---------- wiring ---------------------------------------------------- */
  function initForm() {
    var form = qs('[data-booking-form]');
    if (!form) return;

    function bind(name, prop) {
      var input = fieldEl(name);
      if (!input) return;
      on(input, 'input', function () {
        state[prop] = name === 'consent' ? input.checked : input.value;
        if (name === 'note') updateNoteCount();
        if (!errorEl(name) || !errorEl(name).hidden) revalidateVisible();
        save();
      });
      on(input, 'change', function () {
        state[prop] = name === 'consent' ? input.checked : input.value;
        save();
      });
      on(input, 'blur', function () {
        var msg = validateField(name);
        if (msg) showError(name, msg); else clearError(name);
      });
    }
    bind('name', 'name');
    bind('email', 'email');
    bind('phone', 'phone');
    bind('note', 'note');
    bind('consent', 'consent');
    updateNoteCount();
  }

  function updateNoteCount() {
    var counter = qs('[data-note-count]');
    if (!counter) return;
    counter.textContent = App.t('booking.noteCounter', { n: String(state.note || '').length, max: MAX_NOTE });
  }

  function fillForm() {
    var map = { name: 'name', email: 'email', phone: 'phone', note: 'note' };
    Object.keys(map).forEach(function (key) {
      var input = fieldEl(key);
      if (input) input.value = state[map[key]] || '';
    });
    var consent = fieldEl('consent');
    if (consent) consent.checked = !!state.consent;
    updateNoteCount();
  }

  function initServicePicker() {
    qsa('[data-service-option]').forEach(function (btn) {
      on(btn, 'click', function () {
        selectService(btn.getAttribute('data-service-option'));
        goToStep(2);
      });
    });
    /* "Rezervovať" buttons in the services section preselect and jump ahead */
    qsa('[data-book-service]').forEach(function (btn) {
      on(btn, 'click', function (e) {
        e.preventDefault();
        var id = btn.getAttribute('data-book-service');
        selectService(id);
        goToStep(2);
        App.smoothScrollTo('#booking');
        announce(App.t('booking.stepPrefix') + ' 2 ' + App.t('booking.stepOf') + ' ' + TOTAL_STEPS + ': ' + App.t('booking.step2'));
      });
    });
  }

  function initWizardNav() {
    on(qs('[data-wizard-back]'), 'click', function () { goToStep(state.step - 1); });
    on(qs('[data-wizard-next]'), 'click', function () {
      if (state.step === 5) { submitBooking(); return; }
      if (state.step === 4) {
        var errors = validateBooking().errors;
        var own = ['name', 'email', 'phone', 'note', 'consent'].filter(function (k) { return errors[k]; });
        if (own.length) {
          own.forEach(function (k) { showError(k, errors[k]); });
          var first = fieldEl(own[0]);
          if (first) first.focus();
          announce(App.t('booking.errSummary'));
          return;
        }
      }
      goToStep(state.step + 1);
    });
    qsa('[data-step-goto]').forEach(function (btn) {
      on(btn, 'click', function () { goToStep(Number(btn.getAttribute('data-step-goto'))); });
    });
  }

  /* ---------- language changes ----------------------------------------- */
  function onLanguageChange() {
    renderCalendar();
    renderTimes();
    updateRecap();
    updateNoteCount();
    revalidateVisible();
    if (state.step === 5) renderSummary(qs('[data-summary]'), true);
    if (state.step === 6) renderSummary(qs('[data-summary-done]'), false);
    refreshStep();
  }

  /* ---------- public API ------------------------------------------------- */
  /* Exposed so a real backend can be dropped in later without touching the UI. */
  window.MarekCutsBooking = {
    getAvailableDates: getAvailableDates,
    getAvailableTimes: getAvailableTimes,
    selectService: selectService,
    selectDate: selectDate,
    selectTime: selectTime,
    validateBooking: validateBooking,
    submitBooking: submitBooking,
    getState: function () { return JSON.parse(JSON.stringify(state)); },
    reset: function () {
      state.serviceId = null; state.date = null; state.time = null;
      state.name = ''; state.email = ''; state.phone = ''; state.note = '';
      state.consent = false; state.step = 1; submitted = false;
      clearSaved();
      qsa('[data-service-option]').forEach(function (b) { b.classList.remove('is-selected'); b.setAttribute('aria-pressed', 'false'); });
      fillForm();
      renderCalendar();
      renderTimes();
      updateRecap();
      refreshStep();
    }
  };

  /* ---------- init ------------------------------------------------------- */
  App.register(function () {
    if (!qs('[data-booking]')) return;

    initCalendar();
    initServicePicker();
    initForm();
    initWizardNav();

    var resumed = restore();
    fillForm();

    /* deep link: #booking/step-3 */
    var hashStep = (window.location.hash.match(/step-(\d)/) || [])[1];
    var target = hashStep ? Number(hashStep) : state.step;
    if (state.date) cal.focusISO = state.date;
    state.step = 1;
    goToStep(Math.max(1, Math.min(5, target)));
    renderTimes();

    if (resumed) {
      announce(App.t('booking.resumeNotice'));
    }

    App.onLangChange(onLanguageChange);
  });
})();
