/* Duct Sizing tool -- instant, no-reload live updates (Correction #2), plus
 * rectangular lock/round-25mm controls and a simplified top panel
 * (Correction #3), fully independent width/height with padlock toggles
 * (Correction #4), flat-oval major/minor stepped independently through real
 * catalogue sizes only (Correction #5), a fully independent per-row Index
 * Leg pressure-drop builder (Correction #6), spreadsheet-style data grid
 * (Correction #7), and a 2-row labeled composer above the grid
 * (Correction #9).
 *
 * All calculation and unit-conversion happens server-side
 * (blueprints/duct.py); this file only reads/writes form fields, calls the
 * JSON APIs, and drops already-formatted display strings into the DOM. No
 * engine or unit maths is duplicated here.
 *
 * Correction #6: the top 3-column sizer and the Index Leg builder are fully
 * independent -- two separate state objects, two separate JSON endpoints
 * (/api/state, /api/leg-state), two separate fetch/apply cycles. They now
 * also live on separate pages/modules (Correction #8).
 *
 * Correction #7 / #9: Index Leg composer is `#leg-stage` (2-row labeled
 * form); committed rows are a centered spreadsheet grid. `buildRowCellsHtml()`
 * mirrors `_duct_index_leg.html`'s `leg_row_cells` macro -- keep both in sync.
 *
 * Correction #8: Duct Sizing and Index Leg / pressure drop are separate
 * modules. This file initialises whichever panels are present on the page
 * (`#duct-form` and/or `#leg-panel`) so either page can load alone.
 *
 * Calculate vs live edit (sizer): Calculate clears pinned sizes and
 * re-proposes from volume + design rule (velocity or friction). After that,
 * changing volume or size keeps the current duct size pinned and only
 * refreshes outputs — until Calculate is pressed again.
 *
 * Index Leg state model: every row (and the staging composer) carries its
 * own type/shape/volume/size/length-or-fitting-or-label+dp, read fresh from
 * the DOM by LOOP POSITION (not a stored row index).
 */
(function () {
  "use strict";

  // Auto-select the full content of any typed number/decimal input when the
  // user clicks into it, so they can immediately overtype a new value without
  // first having to select-all. Uses event capture so it fires for dynamically
  // created leg-row inputs too. Skips readonly inputs (flat-oval steppers).
  document.addEventListener("focus", function (evt) {
    var el = evt.target;
    if (el.tagName !== "INPUT" || el.readOnly) return;
    var t = el.type;
    if (t === "number" || t === "text" || el.getAttribute("inputmode") === "decimal" ||
        el.hasAttribute("data-row-field")) {
      el.select();
    }
  }, true);

  function debounce(fn, wait) {
    var t = null;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, wait);
    };
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    var next = value == null ? "" : String(value);
    if (el.textContent !== next) el.textContent = next;
  }

  function setDot(wrapperId, status) {
    var wrapper = document.getElementById(wrapperId);
    if (!wrapper) return;
    var dot = wrapper.querySelector(".dot");
    if (dot) dot.className = "dot " + status;
  }

  // ===========================================================================
  // Duct Sizer (3-column / shape tabs) — optional; page may be Index Leg only.
  // ===========================================================================
  function initSizer() {
  var form = document.getElementById("duct-form");
  if (!form) return;

  var API_BASE = (window.DUCT_API_BASE || window.location.pathname).replace(/\/$/, "");
  var API_STATE_URL = API_BASE + "/api/state";
  var NUDGE_STEP = parseFloat(form.dataset.nudgeStep || "10");
  var ROUND25_STEP = parseFloat(form.dataset.round25Step || "25");

  var els = {
    volume: document.getElementById("f-volume"),
    basis: document.getElementById("f-basis"),
    target: document.getElementById("f-target"),
    targetUnit: document.getElementById("f-target-unit"),
    circularMm: document.getElementById("f-circular-mm"),
    rectWidthHidden: document.getElementById("f-rect-width"),
    rectHeightHidden: document.getElementById("f-rect-height"),
    rectLockWidthHidden: document.getElementById("f-rect-lock-width"),
    rectLockHeightHidden: document.getElementById("f-rect-lock-height"),
    rectRound25Hidden: document.getElementById("f-rect-round25"),
    ovalMajorHidden: document.getElementById("f-oval-major"),
    ovalMinorHidden: document.getElementById("f-oval-minor"),
    circularSelect: document.getElementById("circular-select"),
    rectWidth: document.getElementById("rect-width"),
    rectHeight: document.getElementById("rect-height"),
    rectRound25: document.getElementById("rect-round25"),
    rectWidthLockBtn: document.getElementById("rect-width-lock"),
    rectHeightLockBtn: document.getElementById("rect-height-lock"),
    ovalMajor: document.getElementById("oval-major"),
    ovalMinor: document.getElementById("oval-minor"),
    loading: document.getElementById("duct-loading"),
    errorBox: document.getElementById("duct-error"),
  };

  function currentStep() {
    return (els.rectRound25 && els.rectRound25.checked) ? ROUND25_STEP : NUDGE_STEP;
  }

  // Absolute W/H scale: SI mm ranges keyed by air volume (m³/s).
  // Display values follow the active unit system (mm or in).
  var UNIT_SYSTEM = form.dataset.unitSystem || "SI";
  var MM_PER_IN = 25.4;
  // Matches engine duct_flow IP factor (CFM → m³/h) / 3600 → m³/s.
  var CFM_TO_M3S = 1.699010796 / 3600.0;
  var VOL_THRESHOLD_M3S = 7.5;
  var RANGE_SMALL_MM = { min: 100, mid: 800, max: 1500 };
  var RANGE_LARGE_MM = { min: 750, mid: 1625, max: 2500 };

  function volumeM3s() {
    var v = parseFloat(els.volume && els.volume.value) || 0;
    if (UNIT_SYSTEM === "IP") return v * CFM_TO_M3S;
    return v;
  }

  function scrubRangeMm() {
    return volumeM3s() < VOL_THRESHOLD_M3S ? RANGE_SMALL_MM : RANGE_LARGE_MM;
  }

  function toDisplayDim(mm) {
    return UNIT_SYSTEM === "IP" ? mm / MM_PER_IN : mm;
  }

  function formatMark(mm) {
    var d = toDisplayDim(mm);
    if (UNIT_SYSTEM === "IP") {
      var r = Math.round(d * 10) / 10;
      return (Math.abs(r - Math.round(r)) < 1e-9) ? String(Math.round(r)) : String(r);
    }
    return String(Math.round(d));
  }

  function scrubRangeDisplay() {
    var r = scrubRangeMm();
    return {
      min: toDisplayDim(r.min),
      mid: toDisplayDim(r.mid),
      max: toDisplayDim(r.max),
      minLabel: formatMark(r.min),
      midLabel: formatMark(r.mid),
      maxLabel: formatMark(r.max),
    };
  }

  function snapDimValue(raw) {
    var step = currentStep();
    if (!step || step <= 0) return raw;
    return Math.round(raw / step) * step;
  }

  function valueToPct(value, range) {
    var span = range.max - range.min;
    if (!(span > 0)) return 0;
    var pct = ((value - range.min) / span) * 100;
    return Math.max(0, Math.min(100, pct));
  }

  function clientXToPct(scrub, clientX) {
    var rect = scrub.getBoundingClientRect();
    var pad = 10;
    var usable = Math.max(1, rect.width - pad * 2);
    var x = clientX - rect.left - pad;
    return Math.max(0, Math.min(100, (x / usable) * 100));
  }

  function syncDimScrub(scrub) {
    if (!scrub) return;
    var field = scrub.getAttribute("data-nudge-scrub");
    var input = document.querySelector('input[data-field="' + field + '"]');
    var thumb = scrub.querySelector(".dim-scrub-thumb");
    var wrap = scrub.closest(".dim-scrub-wrap");
    var range = scrubRangeDisplay();
    if (wrap) {
      var minEl = wrap.querySelector('[data-scrub-mark="min"]');
      var midEl = wrap.querySelector('[data-scrub-mark="mid"]');
      var maxEl = wrap.querySelector('[data-scrub-mark="max"]');
      if (minEl) minEl.textContent = range.minLabel;
      if (midEl) midEl.textContent = range.midLabel;
      if (maxEl) maxEl.textContent = range.maxLabel;
    }
    var value = input ? (parseFloat(input.value) || 0) : range.min;
    var pct = valueToPct(value, range);
    if (thumb) {
      thumb.style.left = "calc(10px + (100% - 20px) * " + (pct / 100) + ")";
      thumb.style.marginLeft = "-9px";
    }
    scrub.setAttribute("aria-valuemin", String(range.min));
    scrub.setAttribute("aria-valuemax", String(range.max));
    scrub.setAttribute("aria-valuenow", String(value));
  }

  function syncAllDimScrubs() {
    document.querySelectorAll("[data-nudge-scrub]").forEach(syncDimScrub);
  }

  function setLoading(on) {
    if (els.loading) els.loading.style.display = on ? "" : "none";
    document.querySelectorAll(".col-panel").forEach(function (p) {
      p.classList.toggle("is-loading", !!on);
    });
  }

  function showError(msg) {
    if (!els.errorBox) return;
    els.errorBox.innerHTML = msg ? '<div class="error">' + msg + "</div>" : "";
  }

  function buildBaseParams() {
    var p = new URLSearchParams();
    p.set("volume", els.volume.value);
    p.set("basis", els.basis.value);
    p.set("target_value", els.target.value);
    p.set("circular_mm", els.circularMm.value || "");
    p.set("rect_width", els.rectWidthHidden.value || "");
    p.set("rect_height", els.rectHeightHidden.value || "");
    p.set("rect_lock_width", els.rectLockWidthHidden.value || "");
    p.set("rect_lock_height", els.rectLockHeightHidden.value || "");
    p.set("rect_round25", els.rectRound25Hidden.value || "");
    p.set("oval_major", els.ovalMajorHidden.value || "");
    p.set("oval_minor", els.ovalMinorHidden.value || "");
    return p;
  }

  function setLockButton(btn, locked) {
    if (!btn) return;
    btn.setAttribute("data-locked", locked ? "true" : "false");
    btn.setAttribute("aria-pressed", locked ? "true" : "false");
    var label = btn.querySelector(".lock-label");
    if (label) label.textContent = locked ? "Locked" : "Unlocked";
    syncRectDimLocked(btn, locked);
  }

  function syncRectDimLocked(btn, locked) {
    if (!btn) return;
    var card = btn.closest(".rect-dim-card");
    var input = card
      ? card.querySelector('input[type="number"]')
      : null;
    var scrub = card
      ? card.querySelector("[data-nudge-scrub]")
      : null;
    if (card) card.classList.toggle("is-locked", !!locked);
    if (input) input.disabled = !!locked;
    if (scrub) {
      scrub.classList.toggle("is-disabled", !!locked);
      scrub.setAttribute("aria-disabled", locked ? "true" : "false");
      scrub.tabIndex = locked ? -1 : 0;
    }
  }

  var debouncedNudgeFetch = debounce(function (field, value) {
    fetchState({ nudge: field, nudge_value: String(value) }, { quiet: true });
  }, 120);

  function nudgeRectField(field, next, opts) {
    var input = document.querySelector('input[data-field="' + field + '"]');
    if (!input || input.disabled) return;
    if (next <= 0) return;
    input.value = next;
    syncAllDimScrubs();
    if (opts && opts.live) {
      debouncedNudgeFetch(field, next);
    } else {
      fetchState({ nudge: field, nudge_value: String(next) }, { quiet: true });
    }
  }

  function applyState(data) {
    if (data.error) {
      showError(data.error);
      return;
    }
    showError(null);

    var c = data.circular, r = data.rectangular, o = data.flat_oval;

    // -- circular --
    setText("circ-diameter", c.diameter);
    setText("circ-velocity", c.velocity);
    setText("circ-vp", c.velocity_pressure);
    setText("circ-friction", c.friction_rate);
    setDot("circ-dot-velocity", c.status_velocity);
    setDot("circ-dot-friction", c.status_friction);
    var gaugeRow = document.getElementById("circ-gauge-row");
    var gaugeText = document.getElementById("circ-gauge-text");
    if (!c.is_auto && c.gauge_mm !== null && c.gauge_mm !== undefined) {
      gaugeRow.style.display = "";
      gaugeText.textContent = c.gauge_mm + " mm gauge" + (c.standard ? " — standard stock" : " — special order only");
    } else {
      gaugeRow.style.display = "none";
    }
    els.circularMm.value = c.is_auto ? "" : c.selected_mm;
    els.circularSelect.value = c.is_auto ? "" : c.selected_mm;

    // -- rectangular --
    setText("rect-velocity", r.velocity);
    setText("rect-vp", r.velocity_pressure);
    setText("rect-friction", r.friction_rate);
    setText("rect-de", r.equivalent_diameter);
    setText("rect-aspect-ratio", r.aspect_ratio);
    setDot("rect-dot-velocity", r.status_velocity);
    setDot("rect-dot-friction", r.status_friction);
    var warnRow = document.getElementById("rect-warn-row");
    warnRow.style.display = r.aspect_ratio_warning ? "" : "none";
    // Prefer patching values in place so scrubbing/typing doesn't fight focus
    // or cause the number field to visually "blink".
    if (document.activeElement !== els.rectWidth) {
      if (String(els.rectWidth.value) !== String(r.width)) els.rectWidth.value = r.width;
    }
    if (document.activeElement !== els.rectHeight) {
      if (String(els.rectHeight.value) !== String(r.height)) els.rectHeight.value = r.height;
    }
    els.rectWidthHidden.value = r.width;
    els.rectHeightHidden.value = r.height;
    syncAllDimScrubs();

    // -- flat oval --
    setText("oval-velocity", o.velocity);
    setText("oval-vp", o.velocity_pressure);
    setText("oval-friction", o.friction_rate);
    setText("oval-de", o.equivalent_diameter);
    setDot("oval-dot-velocity", o.status_velocity);
    setDot("oval-dot-friction", o.status_friction);
    els.ovalMajor.value = o.major;
    els.ovalMinor.value = o.minor;
    els.ovalMajorHidden.value = o.major;
    els.ovalMinorHidden.value = o.minor;

    updateUrl(data.fields);
  }

  function updateUrl(fields) {
    if (!fields || !window.history || !window.history.replaceState) return;
    var p = new URLSearchParams();
    Object.keys(fields).forEach(function (k) {
      if (fields[k] !== null && fields[k] !== undefined && fields[k] !== "") {
        p.set(k, fields[k]);
      }
    });
    var newUrl = window.location.pathname + "?" + p.toString();
    window.history.replaceState(null, "", newUrl);
  }

  function fetchState(overrides, opts) {
    var quiet = !!(opts && opts.quiet);
    var params = buildBaseParams();
    if (overrides) {
      Object.keys(overrides).forEach(function (k) { params.set(k, overrides[k]); });
    }
    if (!quiet) setLoading(true);
    return fetch(API_STATE_URL + "?" + params.toString(), { headers: { "Accept": "application/json" } })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!quiet) setLoading(false);
        applyState(data);
        return data;
      })
      .catch(function () {
        if (!quiet) setLoading(false);
        showError("Could not reach the server — check your connection and try again.");
      });
  }

  // -- Live top-input edits (volume / target / basis): keep every current
  // duct size pinned and only refresh outputs (velocity, friction, etc.).
  // Circular "Auto" has an empty circular_mm, so freeze the displayed
  // diameter for the request, then restore Auto in the UI afterwards.
  function onLivePrimaryChange() {
    var wasAuto = !els.circularMm.value;
    var overrides = {};
    if (wasAuto) {
      var dEl = document.getElementById("circ-diameter");
      var d = dEl ? dEl.textContent.trim() : "";
      if (d) overrides.circular_mm = d;
    }
    fetchState(overrides).then(function () {
      if (!wasAuto) return;
      // Keep Auto selected; sizes stay frozen until Calculate.
      els.circularMm.value = "";
      els.circularSelect.value = "";
      var gaugeRow = document.getElementById("circ-gauge-row");
      if (gaugeRow) gaugeRow.style.display = "none";
      if (window.history && window.history.replaceState) {
        var p = new URLSearchParams(window.location.search);
        p.delete("circular_mm");
        var qs = p.toString();
        window.history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : ""));
      }
    });
  }

  // -- Calculate button: clear circular/oval pinned state, and clear
  // rectangular width/height independently unless each is individually
  // locked (Correction #4 -- no more single shared lock), then re-propose
  // sizes from the design target (rectangular at 1:1 aspect by default).
  function onCalculate() {
    els.circularMm.value = "";
    els.ovalMajorHidden.value = "";
    els.ovalMinorHidden.value = "";
    var overrides = { circular_mm: "", oval_major: "", oval_minor: "" };

    if (els.rectLockWidthHidden.value !== "1") {
      els.rectWidthHidden.value = "";
      overrides.rect_width = "";
    }
    if (els.rectLockHeightHidden.value !== "1") {
      els.rectHeightHidden.value = "";
      overrides.rect_height = "";
    }
    // A locked side's hidden field is left untouched -- buildBaseParams()
    // already picks up the persisted value, so no override is needed.
    fetchState(overrides);
  }

  var debouncedLivePrimaryChange = debounce(onLivePrimaryChange, 250);

  [els.volume, els.target].forEach(function (el) {
    el.addEventListener("change", onLivePrimaryChange);
    el.addEventListener("input", debouncedLivePrimaryChange);
  });
  if (els.volume) {
    els.volume.addEventListener("input", function () {
      syncAllDimScrubs();
    });
  }

  els.basis.addEventListener("change", function () {
    var isVelocity = els.basis.value === "velocity";
    if (els.targetUnit) {
      els.targetUnit.textContent = isVelocity ? els.targetUnit.dataset.velocitySym : els.targetUnit.dataset.frictionSym;
    }
    var defVel = form.dataset.defaultVelocity || "6";
    var defFric = form.dataset.defaultFriction || "1";
    if (els.target) {
      els.target.value = isVelocity ? defVel : defFric;
    }
    onLivePrimaryChange();
  });

  // -- Circular stock-size select --
  els.circularSelect.addEventListener("change", function () {
    var value = els.circularSelect.value; // "" = auto
    els.circularMm.value = value;
    fetchState({ nudge: "circular_mm", nudge_value: value || "auto" });
  });

  // -- Rectangular padlock toggles (width / height independent) --
  if (els.rectWidthLockBtn) {
    els.rectWidthLockBtn.addEventListener("click", function () {
      var locked = els.rectWidthLockBtn.getAttribute("data-locked") === "true";
      var next = !locked;
      setLockButton(els.rectWidthLockBtn, next);
      els.rectLockWidthHidden.value = next ? "1" : "";
      fetchState({ rect_lock_width: els.rectLockWidthHidden.value }, { quiet: true });
    });
  }
  if (els.rectHeightLockBtn) {
    els.rectHeightLockBtn.addEventListener("click", function () {
      var locked = els.rectHeightLockBtn.getAttribute("data-locked") === "true";
      var next = !locked;
      setLockButton(els.rectHeightLockBtn, next);
      els.rectLockHeightHidden.value = next ? "1" : "";
      fetchState({ rect_lock_height: els.rectLockHeightHidden.value }, { quiet: true });
    });
  }

  // -- Round-to-25mm checkbox --
  els.rectRound25.addEventListener("change", function () {
    els.rectRound25Hidden.value = els.rectRound25.checked ? "1" : "";
    fetchState({ rect_round25: els.rectRound25Hidden.value }, { quiet: true });
    syncAllDimScrubs();
  });

  // -- Rectangular nudge inputs (direct type-in; flat oval is readonly and
  // has no equivalent -- see the oval catalogue-step handler below) --
  els.rectWidth.addEventListener("change", function () {
    if (els.rectWidth.disabled) return;
    fetchState({ nudge: "rect_width", nudge_value: els.rectWidth.value }, { quiet: true });
    syncAllDimScrubs();
  });
  els.rectHeight.addEventListener("change", function () {
    if (els.rectHeight.disabled) return;
    fetchState({ nudge: "rect_height", nudge_value: els.rectHeight.value }, { quiet: true });
    syncAllDimScrubs();
  });
  els.rectWidth.addEventListener("input", function () { syncDimScrub(document.querySelector('[data-nudge-scrub="rect_width"]')); });
  els.rectHeight.addEventListener("input", function () { syncDimScrub(document.querySelector('[data-nudge-scrub="rect_height"]')); });

  // -- Rectangular stepper +/- buttons (continuous, computed client-side) --
  document.querySelectorAll("[data-nudge][data-dir]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var field = btn.getAttribute("data-nudge");
      var dir = parseFloat(btn.getAttribute("data-dir"));
      var input = document.querySelector('input[data-field="' + field + '"]');
      if (!input || input.disabled) return;
      var step = currentStep();
      var current = parseFloat(input.value) || 0;
      var next = current + dir * step;
      if (next <= 0) next = current; // never step to zero/negative
      nudgeRectField(field, next);
    });
  });

  // -- Absolute scale slider for rectangular dimensions --
  (function bindDimScrubs() {
    document.querySelectorAll("[data-nudge-scrub]").forEach(function (scrub) {
      var field = scrub.getAttribute("data-nudge-scrub");
      var dragging = false;
      var pointerId = null;

      function setFromClientX(clientX, opts) {
        var input = document.querySelector('input[data-field="' + field + '"]');
        if (!input || input.disabled) return;
        var range = scrubRangeDisplay();
        var pct = clientXToPct(scrub, clientX);
        var raw = range.min + (pct / 100) * (range.max - range.min);
        var next = snapDimValue(raw);
        next = Math.max(range.min, Math.min(range.max, next));
        if (next <= 0) return;
        if (String(input.value) === String(next) && !(opts && opts.force)) {
          syncDimScrub(scrub);
          return;
        }
        nudgeRectField(field, next, opts);
      }

      scrub.addEventListener("pointerdown", function (e) {
        if (scrub.classList.contains("is-disabled") || scrub.getAttribute("aria-disabled") === "true") return;
        dragging = true;
        pointerId = e.pointerId;
        scrub.classList.add("is-active");
        scrub.setPointerCapture(pointerId);
        setFromClientX(e.clientX, { live: true });
        e.preventDefault();
      });
      scrub.addEventListener("pointermove", function (e) {
        if (!dragging || e.pointerId !== pointerId) return;
        setFromClientX(e.clientX, { live: true });
      });
      function endDrag(e) {
        if (!dragging) return;
        if (e && pointerId !== null && e.pointerId !== pointerId) return;
        dragging = false;
        pointerId = null;
        scrub.classList.remove("is-active");
        var input = document.querySelector('input[data-field="' + field + '"]');
        if (input && !input.disabled) {
          fetchState({ nudge: field, nudge_value: String(input.value) }, { quiet: true });
        }
        syncDimScrub(scrub);
      }
      scrub.addEventListener("pointerup", endDrag);
      scrub.addEventListener("pointercancel", endDrag);
      scrub.addEventListener("lostpointercapture", endDrag);

      scrub.addEventListener("keydown", function (e) {
        if (scrub.classList.contains("is-disabled")) return;
        var dir = 0;
        if (e.key === "ArrowRight" || e.key === "ArrowUp") dir = 1;
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") dir = -1;
        if (!dir) return;
        e.preventDefault();
        var input = document.querySelector('input[data-field="' + field + '"]');
        if (!input || input.disabled) return;
        var range = scrubRangeDisplay();
        var step = currentStep();
        var current = parseFloat(input.value) || 0;
        var next = current + dir * step;
        next = Math.max(range.min, Math.min(range.max, next));
        if (next <= 0) next = current;
        nudgeRectField(field, next);
      });
    });

    syncAllDimScrubs();
  })();

  // Sync lock → disabled input/scrub on load (server may have restored locks).
  if (els.rectWidthLockBtn) {
    syncRectDimLocked(els.rectWidthLockBtn, els.rectWidthLockBtn.getAttribute("data-locked") === "true");
  }
  if (els.rectHeightLockBtn) {
    syncRectDimLocked(els.rectHeightLockBtn, els.rectHeightLockBtn.getAttribute("data-locked") === "true");
  }

  // -- Flat-oval major/minor stepper +/- buttons (Correction #5): these
  // send a step DIRECTION, not a computed value -- the server looks up the
  // next/previous real catalogue size (LINDAB_FLAT_OVAL_CATALOG's sizes
  // aren't evenly spaced, so a client-computed delta could easily miss the
  // next real size, or land on one that isn't valid for the current major).
  document.querySelectorAll("[data-oval-step][data-dir]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var field = btn.getAttribute("data-oval-step");
      var dir = btn.getAttribute("data-dir");
      fetchState({ nudge: field, nudge_dir: dir });
    });
  });

  // -- Per-column "Reset to calculated" --
  document.querySelectorAll("[data-reset]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var which = btn.getAttribute("data-reset");
      if (which === "rectangular") {
        els.rectWidthHidden.value = "";
        els.rectHeightHidden.value = "";
        els.rectLockWidthHidden.value = "";
        els.rectLockHeightHidden.value = "";
        setLockButton(els.rectWidthLockBtn, false);
        setLockButton(els.rectHeightLockBtn, false);
        fetchState({
          rect_width: "", rect_height: "",
          rect_lock_width: "", rect_lock_height: "",
          nudge: "", nudge_value: ""
        });
      } else if (which === "oval") {
        els.ovalMajorHidden.value = "";
        els.ovalMinorHidden.value = "";
        fetchState({ oval_major: "", oval_minor: "", nudge: "", nudge_value: "" });
      }
    });
  });

  // -- Calculate: re-propose duct sizes from the design inputs --
  form.addEventListener("submit", function (evt) {
    evt.preventDefault();
    onCalculate();
  });
  } // initSizer

  // ===========================================================================
  // Index Leg (Correction #6) -- fully independent of the sizer above.
  // May be the only panel on the page (Correction #8).
  // ===========================================================================
  function initLeg() {
  var legPanel = document.getElementById("leg-panel");
  if (!legPanel) return;

  var LEG_API_URL = (window.DUCT_API_BASE || window.location.pathname).replace(/\/$/, "") + "/api/leg-state";
  var ROW_FIELDS = ["type", "shape", "volume", "diameter", "width", "height",
                     "major", "minor", "length", "fitting", "label", "dp"];

  var legEls = {
    stageRow: document.getElementById("leg-stage"),
    stageResultCell: document.getElementById("leg-stage-result-cell"),
    rowsBody: document.getElementById("leg-rows-body"),
    errorBox: document.getElementById("leg-error"),
    addBtn: document.getElementById("leg-add-row"),
    clearBtn: document.getElementById("leg-clear-table"),
    exportLink: document.getElementById("leg-export-csv"),
    safetyMargin: document.getElementById("leg-safety-margin"),
  };

  var EXPORT_BASE_HREF = legEls.exportLink ? legEls.exportLink.href.split("?")[0] : "";
  var LEG_SYMS = window.DUCT_LEG_SYMS || {};
  var LEG_TYPE_OPTIONS = window.DUCT_LEG_TYPE_OPTIONS || [];
  var LEG_SHAPE_OPTIONS = window.DUCT_LEG_SHAPE_OPTIONS || [];
  var LEG_FITTINGS_BY_SHAPE = window.DUCT_LEG_FITTINGS_BY_SHAPE || {};

  function escAttr(v) {
    return v === null || v === undefined ? "" : String(v).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  function typeOptionsHtml(selected) {
    return LEG_TYPE_OPTIONS.map(function (o) {
      return '<option value="' + o.key + '"' + (o.key === selected ? " selected" : "") + ">" + o.label + "</option>";
    }).join("");
  }

  function shapeOptionsHtml(selected) {
    return LEG_SHAPE_OPTIONS.map(function (o) {
      return '<option value="' + o.key + '"' + (o.key === selected ? " selected" : "") + ">" + o.label + "</option>";
    }).join("");
  }

  function fittingOptionsHtml(shape, selectedKey) {
    var list = LEG_FITTINGS_BY_SHAPE[shape] || [];
    return list.map(function (f) {
      return '<option value="' + f.key + '"' + (f.key === selectedKey ? " selected" : "") +
        ">" + f.label + " (K=" + f.k.toFixed(2) + ")</option>";
    }).join("");
  }

  // Mirrors `_duct_index_leg.html`'s `leg_row_cells` macro exactly -- same
  // columns, same data attributes, same order -- one <td> per column, no
  // wrapping element, so the caller can drop these straight into a <tr>
  // alongside the #/Pressure-Drop/Remove cells it builds itself. Used for
  // every committed data-grid row (composer fields are server-rendered
  // separately in `#leg-stage`).
  function buildRowCellsHtml(namePrefix, nameSuffix, raw, currentType, currentShape, currentFitting) {
    function name(field) { return namePrefix + field + nameSuffix; }
    var v = function (field) { return escAttr(raw[field]); };
    return (
      '<td class="leg-cell"><select data-row-field="type" name="' + name("type") + '">' + typeOptionsHtml(currentType) + '</select></td>' +
      '<td class="leg-cell"><select data-row-field="shape" data-shape-field name="' + name("shape") + '">' + shapeOptionsHtml(currentShape) + '</select></td>' +
      '<td class="leg-cell"><input data-row-field="volume" data-shape-field name="' + name("volume") + '" value="' + v("volume") + '" inputmode="decimal"></td>' +
      '<td class="leg-cell">' +
        '<input data-row-field="diameter" data-size-for="circular" name="' + name("diameter") + '" value="' + v("diameter") + '" inputmode="decimal">' +
        '<input data-row-field="width" data-size-for="rectangular" name="' + name("width") + '" value="' + v("width") + '" inputmode="decimal">' +
        '<input data-row-field="major" data-size-for="flat_oval" name="' + name("major") + '" value="' + v("major") + '" inputmode="decimal">' +
      '</td>' +
      '<td class="leg-cell">' +
        '<input data-row-field="height" data-size-for="rectangular" name="' + name("height") + '" value="' + v("height") + '" inputmode="decimal">' +
        '<input data-row-field="minor" data-size-for="flat_oval" name="' + name("minor") + '" value="' + v("minor") + '" inputmode="decimal">' +
      '</td>' +
      '<td class="leg-cell"><input data-row-field="length" data-type-for="straight flex" name="' + name("length") + '" value="' + v("length") + '" inputmode="decimal"></td>' +
      '<td class="leg-cell"><select data-row-field="fitting" data-fitting-select data-type-for="fitting" name="' + name("fitting") + '">' + fittingOptionsHtml(currentShape, currentFitting) + '</select></td>' +
      '<td class="leg-cell"><input data-row-field="label" data-type-for="accessory" name="' + name("label") + '" value="' + v("label") + '"></td>' +
      '<td class="leg-cell"><input data-row-field="dp" data-type-for="accessory" name="' + name("dp") + '" value="' + v("dp") + '" inputmode="decimal"></td>'
    );
  }

  // Builds the <td> elements for one row via buildRowCellsHtml() (a plain
  // HTML string) and hands back real DOM nodes, so callers that also need
  // DOM-API-built cells (the #/Pressure-Drop/Remove cells, built with
  // textContent for safety -- see buildRowTr()) can append them directly.
  function buildRowCellsNodes(namePrefix, nameSuffix, raw, currentType, currentShape, currentFitting) {
    var tmp = document.createElement("tbody");
    tmp.innerHTML = "<tr>" + buildRowCellsHtml(namePrefix, nameSuffix, raw, currentType, currentShape, currentFitting) + "</tr>";
    return tmp.firstElementChild; // a <tr> containing just the field <td>s
  }

  function updateFieldVisibility(container) {
    if (!container) return;
    var typeSel = container.querySelector('[data-row-field="type"]');
    var shapeSel = container.querySelector('[data-row-field="shape"]');
    var type = typeSel ? typeSel.value : "straight";
    var shape = shapeSel ? shapeSel.value : "circular";
    var isAccessory = type === "accessory";
    container.querySelectorAll("[data-shape-field]").forEach(function (el) {
      el.style.display = isAccessory ? "none" : "";
    });
    container.querySelectorAll("[data-size-for]").forEach(function (el) {
      var forShape = el.getAttribute("data-size-for");
      el.style.display = (!isAccessory && forShape === shape) ? "" : "none";
    });
    container.querySelectorAll("[data-type-for]").forEach(function (el) {
      var forTypes = el.getAttribute("data-type-for").split(" ");
      el.style.display = forTypes.indexOf(type) !== -1 ? "" : "none";
    });
  }

  function refreshFittingOptions(container, shape) {
    var sel = container.querySelector('[data-row-field="fitting"]');
    if (sel) sel.innerHTML = fittingOptionsHtml(shape, null);
  }

  function readFieldsFrom(container) {
    var raw = {};
    ROW_FIELDS.forEach(function (f) {
      var input = container.querySelector('[data-row-field="' + f + '"]');
      raw[f] = input ? input.value : "";
    });
    return raw;
  }

  function buildLegParams(opts) {
    opts = opts || {};
    var p = new URLSearchParams();
    var rows = legEls.rowsBody ? legEls.rowsBody.querySelectorAll("tr[data-row]") : [];
    p.set("leg_row_count", String(rows.length));
    p.set("leg_safety_margin", legEls.safetyMargin ? (legEls.safetyMargin.value || "0") : "0");
    rows.forEach(function (row, i) {
      ROW_FIELDS.forEach(function (f) {
        var input = row.querySelector('[data-row-field="' + f + '"]');
        if (input) p.set("leg_" + f + "_" + i, input.value);
      });
    });
    if (!opts.skipStaging && legEls.stageRow) {
      ROW_FIELDS.forEach(function (f) {
        var input = legEls.stageRow.querySelector('[data-row-field="' + f + '"]');
        if (input) p.set("stage_" + f, input.value);
      });
    }
    return p;
  }

  function showLegError(msg) {
    if (!legEls.errorBox) return;
    legEls.errorBox.innerHTML = "";
    if (!msg) return;
    var div = document.createElement("div");
    div.className = "error";
    div.textContent = msg;
    legEls.errorBox.appendChild(div);
  }

  // The composer's preview panel shows live velocity / VP / F-or-K and the
  // item's pressure drop, or the stage-level error -- built with the DOM API
  // + textContent (not innerHTML) since `leg.stage_error` can embed a raw
  // value the user just typed (see blueprints/duct.py's `_f()`).
  function updateStageResultCell(leg) {
    if (!legEls.stageResultCell) return;
    legEls.stageResultCell.innerHTML = "";
    if (leg.stage_error) {
      var errDiv = document.createElement("div");
      errDiv.className = "error";
      errDiv.id = "leg-stage-error";
      errDiv.style.margin = "0";
      errDiv.textContent = leg.stage_error;
      legEls.stageResultCell.appendChild(errDiv);
      return;
    }
    var s = leg.stage;
    if (!s) return;

    var metrics = document.createElement("div");
    metrics.className = "leg-preview-metrics suffix";
    function metric(id, label, text) {
      var wrap = document.createElement("span");
      wrap.appendChild(document.createTextNode(label + ": "));
      var span = document.createElement("span");
      span.id = id;
      span.textContent = text;
      wrap.appendChild(span);
      metrics.appendChild(wrap);
    }
    metric("stage-velocity", "V", s.velocity_display);
    metric("stage-vp", "VP", s.velocity_pressure_display);
    metric("stage-friction", "F/K", s.friction_rate_display);

    var dpLine = document.createElement("div");
    dpLine.className = "leg-preview-dp";
    var dpSpan = document.createElement("span");
    dpSpan.id = "stage-dp";
    dpSpan.textContent = s.dp_display;
    dpLine.appendChild(dpSpan);
    dpLine.appendChild(document.createTextNode(" "));
    var symSpan = document.createElement("span");
    symSpan.className = "u";
    symSpan.textContent = LEG_SYMS.velocity_pressure || "";
    dpLine.appendChild(symSpan);

    legEls.stageResultCell.appendChild(metrics);
    legEls.stageResultCell.appendChild(dpLine);
  }

  // Builds one committed row's <tr> -- the field <td>s come from
  // buildRowCellsNodes() (mirrors the server-rendered macro exactly); the
  // #/Pressure-Drop/Remove cells are still built via the DOM API +
  // textContent, same as before, since `row.dp_display`/`row.error` can
  // carry a raw value the user typed and must never be treated as HTML.
  function buildRowTr(row) {
    var tr = document.createElement("tr");
    tr.setAttribute("data-row", "");
    tr.setAttribute("data-index", String(row.index));
    if (row.error) tr.className = "row-error";

    var numTd = document.createElement("td");
    numTd.className = "leg-row-num";
    numTd.textContent = String(row.index + 1);
    tr.appendChild(numTd);

    var cellsRow = buildRowCellsNodes(
      "leg_", "_" + row.index, row.raw, row.type, row.shape || "circular", row.fitting_key || row.raw.fitting
    );
    while (cellsRow.firstChild) tr.appendChild(cellsRow.firstChild);

    var dpTd = document.createElement("td");
    dpTd.className = "num leg-dp-cell";
    dpTd.appendChild(document.createTextNode(row.dp_display + " "));
    var symSpan = document.createElement("span");
    symSpan.className = "u";
    symSpan.textContent = LEG_SYMS.velocity_pressure || "";
    dpTd.appendChild(symSpan);
    if (row.error) {
      var errDiv = document.createElement("div");
      errDiv.className = "suffix leg-row-error-text";
      errDiv.textContent = row.error;
      dpTd.appendChild(errDiv);
    }
    tr.appendChild(dpTd);

    var removeTd = document.createElement("td");
    removeTd.className = "leg-action-cell";
    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-ghost";
    removeBtn.setAttribute("data-leg-remove", "");
    removeBtn.setAttribute("aria-label", "Remove row");
    removeBtn.textContent = "✕";
    removeTd.appendChild(removeBtn);
    tr.appendChild(removeTd);

    updateFieldVisibility(tr);
    return tr;
  }

  // Keep the PDF report form's hidden leg fields in sync with the current
  // leg state so "Download PDF Report" always generates a leg-table-first
  // PDF when there are committed rows. The form's hidden fields are rendered
  // server-side once on page load (when the leg is typically empty); without
  // this sync they'd always show leg_row_count=0 and generate a sizer-only
  // PDF regardless of how many rows have been added since the page loaded.
  function syncReportFormLegFields(leg) {
    var form = document.querySelector("form[action$=\"/report\"]");
    if (!form) return;
    // Remove all stale leg hidden fields from a previous sync
    Array.prototype.slice.call(form.querySelectorAll("input[name^=\"leg_\"]")).forEach(function (el) {
      el.parentNode.removeChild(el);
    });
    // Add fresh hidden fields matching what _report_fields_for() produces
    function addHidden(name, val) {
      var inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = name;
      inp.value = (val == null) ? "" : String(val);
      form.appendChild(inp);
    }
    addHidden("leg_row_count", leg.row_count || 0);
    addHidden("leg_safety_margin", leg.safety_margin || 0);
    (leg.rows || []).forEach(function (row) {
      var i = row.index;
      var raw = row.raw || {};
      ["type", "shape", "volume", "diameter", "width", "height",
       "major", "minor", "length", "fitting", "label", "dp"].forEach(function (f) {
        var v = (f === "type") ? (row.type || "") :
                (f === "shape") ? (row.shape || "") :
                (raw[f] == null ? "" : String(raw[f]));
        addHidden("leg_" + f + "_" + i, v);
      });
    });
  }

  function applyLegState(leg) {
    if (legEls.rowsBody) {
      legEls.rowsBody.innerHTML = "";
      (leg.rows || []).forEach(function (row) {
        legEls.rowsBody.appendChild(buildRowTr(row));
      });
    }
    setText("leg-total", leg.total_display);
    setText("leg-total-sym", leg.total_sym);
    updateStageResultCell(leg);
    syncReportFormLegFields(leg);

    // Safety margin rows in tfoot
    var margin = leg.safety_margin || 0;
    var showMargin = margin > 0 && leg.total_with_margin_display;
    var marginTr = document.getElementById("leg-margin-tr");
    var totalMarginTr = document.getElementById("leg-total-margin-tr");
    if (marginTr) marginTr.style.display = showMargin ? "" : "none";
    if (totalMarginTr) totalMarginTr.style.display = showMargin ? "" : "none";
    if (showMargin) {
      setText("leg-margin-pct", margin.toFixed(0));
      setText("leg-margin-amount", leg.margin_amount_display || "—");
      setText("leg-margin-sym", leg.total_sym);
      setText("leg-total-margin", leg.total_with_margin_display);
      setText("leg-total-margin-sym", leg.total_sym);
    }

    if (legEls.exportLink && EXPORT_BASE_HREF) {
      legEls.exportLink.href = EXPORT_BASE_HREF + "?" + buildLegParams().toString();
    }
  }

  function fetchLegState(overrides, opts) {
    var params = buildLegParams(opts);
    if (overrides) {
      Object.keys(overrides).forEach(function (k) { params.set(k, overrides[k]); });
    }
    return fetch(LEG_API_URL + "?" + params.toString(), { headers: { "Accept": "application/json" } })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        showLegError(null);
        applyLegState(data);
        return data;
      })
      .catch(function () {
        showLegError("Could not reach the server — check your connection and try again.");
      });
  }

  var debouncedLegFetch = debounce(function () { fetchLegState(); }, 300);

  // -- Entry row: any field change/typing refreshes the live preview in its
  // Pressure Drop cell. A shape change also refreshes the fitting dropdown's
  // options client-side immediately (so it doesn't briefly show the wrong
  // shape's fittings while the debounced fetch is in flight); a type or
  // shape change also toggles field visibility immediately. --
  if (legEls.stageRow) {
    legEls.stageRow.addEventListener("change", function (evt) {
      var target = evt.target;
      if (!target.hasAttribute("data-row-field")) return;
      if (target.getAttribute("data-row-field") === "shape") {
        refreshFittingOptions(legEls.stageRow, target.value);
      }
      if (target.getAttribute("data-row-field") === "type" || target.getAttribute("data-row-field") === "shape") {
        updateFieldVisibility(legEls.stageRow);
      }
      fetchLegState();
    });
    legEls.stageRow.addEventListener("input", function (evt) {
      if (evt.target.hasAttribute("data-row-field")) debouncedLegFetch();
    });
  }

  // -- Add to Table: commit the current entry-row values as a new row, then
  // clear only the "specific item" fields (length/fitting/label/dp) --
  // type/shape/volume/size carry forward, since a real index leg's shape
  // and type usually stay the same run to run, per Paul's own description
  // of the workflow. --
  function clearStagingItemFields() {
    if (!legEls.stageRow) return;
    ["length", "fitting", "label", "dp"].forEach(function (f) {
      var input = legEls.stageRow.querySelector('[data-row-field="' + f + '"]');
      if (!input) return;
      if (input.tagName === "SELECT") {
        if (input.options.length) input.selectedIndex = 0;
      } else {
        input.value = "";
      }
    });
  }

  if (legEls.addBtn) {
    legEls.addBtn.addEventListener("click", function () {
      if (!legEls.stageRow || !legEls.rowsBody) return;
      var existingCount = legEls.rowsBody.querySelectorAll("tr[data-row]").length;
      var stagingRaw = readFieldsFrom(legEls.stageRow);
      var overrides = { leg_row_count: String(existingCount + 1) };
      ROW_FIELDS.forEach(function (f) {
        overrides["leg_" + f + "_" + existingCount] = stagingRaw[f];
      });
      fetchLegState(overrides).then(function () {
        clearStagingItemFields();
        fetchLegState();
      });
    });
  }

  // -- Committed rows: delegated listeners, since the whole table is rebuilt
  // on every response -- per-row handlers would be thrown away each time. --
  if (legEls.rowsBody) {
    legEls.rowsBody.addEventListener("change", function (evt) {
      var target = evt.target;
      if (!target.hasAttribute("data-row-field")) return;
      var tr = target.closest("tr[data-row]");
      var field = target.getAttribute("data-row-field");
      if (tr && field === "shape") refreshFittingOptions(tr, target.value);
      if (tr && (field === "type" || field === "shape")) updateFieldVisibility(tr);
      fetchLegState();
    });
    legEls.rowsBody.addEventListener("input", function (evt) {
      if (evt.target.hasAttribute("data-row-field")) debouncedLegFetch();
    });
    legEls.rowsBody.addEventListener("click", function (evt) {
      var btn = evt.target.closest("[data-leg-remove]");
      if (!btn) return;
      var tr = btn.closest("tr");
      if (tr) tr.remove();
      fetchLegState();
    });
  }

  // -- Safety margin input: refetch so tfoot rows update immediately --
  if (legEls.safetyMargin) {
    legEls.safetyMargin.addEventListener("input", debounce(function () { fetchLegState(); }, 300));
    legEls.safetyMargin.addEventListener("change", function () { fetchLegState(); });
  }

  // -- Clear Table --
  if (legEls.clearBtn) {
    legEls.clearBtn.addEventListener("click", function () {
      fetchLegState({ leg_row_count: "0" });
    });
  }

  // -- Initial field visibility (server-rendered state on first load) --
  updateFieldVisibility(legEls.stageRow);
  document.querySelectorAll("#leg-rows-body tr[data-row]").forEach(function (tr) {
    updateFieldVisibility(tr);
  });
  if (legEls.exportLink && EXPORT_BASE_HREF) {
    legEls.exportLink.href = EXPORT_BASE_HREF + "?" + buildLegParams().toString();
  }
  } // initLeg

  initSizer();
  initLeg();
})();
