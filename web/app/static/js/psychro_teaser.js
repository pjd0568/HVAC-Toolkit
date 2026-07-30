/* Homepage free psychrometric calculator + trial teaser.
   Calls the public engine-backed API; converts inputs on SI/IP toggle;
   persists the last good payload to localStorage (`hvac_teaser_state`) on CTA. */
(function () {
  "use strict";

  var root = document.getElementById("psychro-teaser");
  if (!root) return;

  var apiUrl = root.getAttribute("data-teaser-api");
  var registerUrl = root.getAttribute("data-register-url") || "/register";
  var storageKey = root.getAttribute("data-storage-key") || "hvac_teaser_state";
  var P_ATM_SI = 101.325;

  var tdbEl = root.querySelector('[data-teaser-input="t_db"]');
  var propEl = root.querySelector('[data-teaser-input="prop"]');
  var valEl = root.querySelector('[data-teaser-input="val"]');
  var pressureEl = root.querySelector('[data-teaser-input="pressure"]');
  var valLabel = root.querySelector("[data-teaser-val-label]");
  var statusEl = root.querySelector("[data-teaser-status]");
  var modal = root.querySelector("[data-teaser-modal]");
  var systemButtons = root.querySelectorAll("[data-teaser-system]");

  var system = detectDefaultSystem();
  var lastPayload = null;
  var debounceTimer = null;
  var calcSeq = 0;

  function detectDefaultSystem() {
    try {
      var lang = String(navigator.language || navigator.userLanguage || "").toLowerCase();
      if (lang === "en-us" || /(^|-)us$/.test(lang)) return "IP";
      if (typeof Intl !== "undefined" && Intl.Locale) {
        var locale = new Intl.Locale(navigator.language || "en");
        if (String(locale.region || "").toUpperCase() === "US") return "IP";
      }
    } catch (e) { /* ignore */ }
    return "SI";
  }

  function seaLevelPressureDisplay(sys) {
    return sys === "IP" ? +(P_ATM_SI / 3.386389).toFixed(3) : +P_ATM_SI.toFixed(3);
  }

  function cToF(c) { return c * 9 / 5 + 32; }
  function fToC(f) { return (f - 32) * 5 / 9; }
  function kpaToInHg(kpa) { return kpa / 3.386389; }
  function inHgToKpa(inhg) { return inhg * 3.386389; }

  function parseNum(el) {
    var raw = String(el.value || "").trim().replace(",", ".");
    if (!raw) return null;
    var n = parseFloat(raw);
    return isFinite(n) ? n : null;
  }

  function formatNum(n, dp) {
    if (n == null || !isFinite(n)) return "";
    var f = Math.pow(10, dp);
    return String(Math.round(n * f) / f);
  }

  function setSystemUI(sys) {
    system = sys;
    systemButtons.forEach(function (btn) {
      var on = btn.getAttribute("data-teaser-system") === sys;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    root.querySelectorAll("[data-teaser-sym='temperature']").forEach(function (el) {
      el.textContent = sys === "IP" ? "°F" : "°C";
    });
    root.querySelectorAll("[data-teaser-sym='pressure']").forEach(function (el) {
      el.textContent = sys === "IP" ? "inHg" : "kPa";
    });
    updateValLabel();
  }

  function updateValLabel() {
    if (!valLabel) return;
    if (propEl.value === "twb") {
      valLabel.textContent = "Wet bulb temperature (" + (system === "IP" ? "°F" : "°C") + ")";
    } else {
      valLabel.textContent = "Relative humidity (%)";
    }
  }

  function convertInputs(fromSys, toSys) {
    if (fromSys === toSys) return;
    var t = parseNum(tdbEl);
    if (t != null) {
      var tSi = fromSys === "IP" ? fToC(t) : t;
      tdbEl.value = formatNum(toSys === "IP" ? cToF(tSi) : tSi, 1);
    }
    if (propEl.value === "twb") {
      var wb = parseNum(valEl);
      if (wb != null) {
        var wbSi = fromSys === "IP" ? fToC(wb) : wb;
        valEl.value = formatNum(toSys === "IP" ? cToF(wbSi) : wbSi, 1);
      }
    }
    var p = parseNum(pressureEl);
    if (p != null) {
      var pSi = fromSys === "IP" ? inHgToKpa(p) : p;
      pressureEl.value = formatNum(toSys === "IP" ? kpaToInHg(pSi) : pSi, 3);
    } else {
      pressureEl.value = formatNum(seaLevelPressureDisplay(toSys), 3);
    }
  }

  function setDefaults() {
    if (system === "IP") {
      tdbEl.value = "70";
      propEl.value = "rh";
      valEl.value = "50";
      pressureEl.value = formatNum(seaLevelPressureDisplay("IP"), 3);
    } else {
      tdbEl.value = "21";
      propEl.value = "rh";
      valEl.value = "50";
      pressureEl.value = formatNum(seaLevelPressureDisplay("SI"), 3);
    }
    updateValLabel();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function valunit(display, symbol) {
    if (display == null || display === "") {
      return '<span class="valunit"><span class="v">—</span></span>';
    }
    return (
      '<span class="valunit"><span class="v">' + escapeHtml(display) +
      '</span><span class="u">' + escapeHtml(symbol || "") + "</span></span>"
    );
  }

  function renderOutputs(payload) {
    var outs = (payload && payload.outputs) || {};
    ["t_dp", "t_wb", "w", "h", "v", "rho"].forEach(function (key) {
      var cell = root.querySelector('[data-teaser-out="' + key + '"]');
      if (!cell) return;
      var q = outs[key];
      if (!q) {
        cell.innerHTML = valunit(null);
        return;
      }
      cell.innerHTML = valunit(q.display, q.symbol);
    });
  }

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("is-error", !!isError);
  }

  function buildBody() {
    var t = parseNum(tdbEl);
    var v = parseNum(valEl);
    var p = parseNum(pressureEl);
    if (t == null || v == null) return null;
    return {
      system: system,
      t_db: t,
      prop: propEl.value || "rh",
      val: v,
      pressure: p == null ? seaLevelPressureDisplay(system) : p,
    };
  }

  function calculate() {
    var body = buildBody();
    if (!body) {
      setStatus("Enter dry bulb and a second property to calculate.", false);
      return;
    }
    var seq = ++calcSeq;
    setStatus("Calculating…", false);
    fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { okHttp: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (seq !== calcSeq) return;
        if (!result.okHttp || !result.data || !result.data.ok) {
          lastPayload = null;
          setStatus((result.data && result.data.error) || "Could not calculate state.", true);
          renderOutputs(null);
          return;
        }
        lastPayload = result.data;
        renderOutputs(result.data);
        setStatus("", false);
      })
      .catch(function () {
        if (seq !== calcSeq) return;
        lastPayload = null;
        setStatus("Network error — try again.", true);
      });
  }

  function scheduleCalculate() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(calculate, 180);
  }

  function openModal() {
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("teaser-modal-open");
    var focusBtn = modal.querySelector("[data-teaser-cta]");
    if (focusBtn) focusBtn.focus();
  }

  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove("teaser-modal-open");
  }

  function persistAndGo() {
    try {
      if (lastPayload && lastPayload.ok) {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            system: lastPayload.system,
            inputs: lastPayload.inputs,
            outputs: lastPayload.outputs,
            si: lastPayload.si,
            savedAt: new Date().toISOString(),
          })
        );
      } else {
        var body = buildBody();
        if (body) {
          localStorage.setItem(
            storageKey,
            JSON.stringify({
              system: body.system,
              pendingInputs: body,
              savedAt: new Date().toISOString(),
            })
          );
        }
      }
    } catch (e) { /* private mode */ }
    window.location.href = registerUrl;
  }

  systemButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var next = btn.getAttribute("data-teaser-system");
      if (!next || next === system) return;
      convertInputs(system, next);
      setSystemUI(next);
      scheduleCalculate();
    });
  });

  [tdbEl, valEl, pressureEl].forEach(function (el) {
    el.addEventListener("input", scheduleCalculate);
    el.addEventListener("change", scheduleCalculate);
  });
  propEl.addEventListener("change", function () {
    updateValLabel();
    scheduleCalculate();
  });

  root.querySelectorAll("[data-teaser-lock]").forEach(function (el) {
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      openModal();
    });
  });
  root.querySelectorAll("[data-teaser-cta]").forEach(function (el) {
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      persistAndGo();
    });
  });
  root.querySelectorAll("[data-teaser-modal-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && modal && !modal.hidden) closeModal();
  });

  setSystemUI(system);
  setDefaults();
  calculate();
})();
