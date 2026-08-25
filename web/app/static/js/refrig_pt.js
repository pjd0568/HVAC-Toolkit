(function () {
  var root = document.getElementById("pt-explorer");
  if (!root) return;
  var dataEl = document.getElementById("pt-data");
  if (!dataEl) return;

  var points;
  try {
    points = JSON.parse(dataEl.textContent || "[]");
  } catch (err) {
    return;
  }
  if (!points.length) return;

  var P_ATM = 1.01325;
  var hasGlide = root.getAttribute("data-glide") === "1";

  var slider = document.getElementById("pt-temp");
  var tempInput = document.getElementById("pt-temp-input");
  var pressureInput = document.getElementById("pt-pressure-input");
  var pressurePhase = document.getElementById("pt-pressure-phase");
  var pressureGo = document.getElementById("pt-pressure-go");
  var pressureHint = document.getElementById("pt-pressure-hint");
  var pressureTemp = document.getElementById("pt-pressure-temp");
  var tbody = document.getElementById("pt-tbody");
  var table = document.getElementById("pt-table");
  var liqVal = document.getElementById("pt-liq-value");
  var vapVal = document.getElementById("pt-vap-value");
  var glideOut = document.getElementById("pt-glide");
  var dialLiq = document.getElementById("pt-dial-liq");
  var dialVap = document.getElementById("pt-dial-vap");
  var liqMin = document.getElementById("pt-liq-min");
  var liqMax = document.getElementById("pt-liq-max");
  var vapMin = document.getElementById("pt-vap-min");
  var vapMax = document.getElementById("pt-vap-max");
  var modeBarg = document.getElementById("pt-mode-barg");
  var modeBara = document.getElementById("pt-mode-bara");
  var unitEls = document.querySelectorAll("[data-p-unit]");

  if (!slider) return;

  var mode = "barg";
  var syncingPressure = false;
  var sorted = points.slice().sort(function (a, b) { return a.t - b.t; });
  var byT = {};
  sorted.forEach(function (p) {
    byT[String(Math.round(p.t))] = p;
  });

  var tMin = Math.round(sorted[0].t);
  var tMax = Math.round(sorted[sorted.length - 1].t);

  function fmtP(v) {
    return v.toFixed(2);
  }

  function displayP(barg) {
    return mode === "bara" ? barg + P_ATM : barg;
  }

  function toBarg(displayed) {
    return mode === "bara" ? displayed - P_ATM : displayed;
  }

  function scaleBounds() {
    var lo = Infinity;
    var hi = -Infinity;
    sorted.forEach(function (p) {
      lo = Math.min(lo, displayP(p.liq), displayP(p.vap));
      hi = Math.max(hi, displayP(p.liq), displayP(p.vap));
    });
    if (!(hi > lo)) hi = lo + 1;
    return { lo: lo, hi: hi, span: hi - lo };
  }

  function frac(barg, bounds) {
    return Math.max(0, Math.min(1, (displayP(barg) - bounds.lo) / bounds.span));
  }

  function setDial(dial, barg, bounds) {
    if (!dial) return;
    var f = frac(barg, bounds);
    dial.style.setProperty("--pct", (f * 100).toFixed(2));
    dial.style.setProperty("--needle", (-90 + f * 180).toFixed(2) + "deg");
  }

  function updateScaleLabels(bounds) {
    if (liqMin) liqMin.textContent = fmtP(bounds.lo);
    if (liqMax) liqMax.textContent = fmtP(bounds.hi);
    if (vapMin) vapMin.textContent = fmtP(bounds.lo);
    if (vapMax) vapMax.textContent = fmtP(bounds.hi);
  }

  function updateUnitLabels() {
    var label = mode === "bara" ? "bara" : "barg";
    for (var i = 0; i < unitEls.length; i++) {
      unitEls[i].textContent = label;
    }
    if (modeBarg) modeBarg.classList.toggle("is-active", mode === "barg");
    if (modeBara) modeBara.classList.toggle("is-active", mode === "bara");
  }

  function clampT(t) {
    t = Math.round(Number(t));
    if (isNaN(t)) return null;
    if (t < tMin) t = tMin;
    if (t > tMax) t = tMax;
    return t;
  }

  /** Closest table temperature for a measured pressure on liq or vap curve. */
  function tempFromPressure(displayedP, phase) {
    var target = toBarg(displayedP);
    var key = phase === "vap" ? "vap" : "liq";
    var best = sorted[0];
    var bestErr = Math.abs(best[key] - target);
    for (var i = 1; i < sorted.length; i++) {
      var err = Math.abs(sorted[i][key] - target);
      if (err < bestErr) {
        bestErr = err;
        best = sorted[i];
      }
    }
    // Linear interpolate between neighbours when between two points.
    for (var j = 0; j < sorted.length - 1; j++) {
      var a = sorted[j][key];
      var b = sorted[j + 1][key];
      var lo = Math.min(a, b);
      var hi = Math.max(a, b);
      if (target >= lo && target <= hi && a !== b) {
        var u = (target - a) / (b - a);
        var tInterp = sorted[j].t + u * (sorted[j + 1].t - sorted[j].t);
        return {
          t: clampT(tInterp),
          err: 0,
          interpolated: true,
        };
      }
    }
    return {
      t: clampT(best.t),
      err: bestErr,
      interpolated: false,
    };
  }

  function renderTable(t) {
    if (!tbody) return;
    var idx = -1;
    for (var i = 0; i < sorted.length; i++) {
      if (Math.round(sorted[i].t) === t) {
        idx = i;
        break;
      }
    }
    if (idx < 0) return;

    var start = Math.max(0, idx - 2);
    var end = Math.min(sorted.length - 1, idx + 2);
    while (end - start < 4 && start > 0) start--;
    while (end - start < 4 && end < sorted.length - 1) end++;

    var html = "";
    for (var j = start; j <= end; j++) {
      var row = sorted[j];
      var rt = Math.round(row.t);
      var active = rt === t ? " pt-row-active" : "";
      html += '<tr class="' + active.trim() + '" data-t="' + rt + '">' +
        '<td class="num">' + rt + "</td>";
      if (hasGlide) {
        html +=
          '<td class="num">' + displayP(row.liq).toFixed(3) + "</td>" +
          '<td class="num">' + displayP(row.vap).toFixed(3) + "</td>";
      } else {
        html += '<td class="num">' + displayP(row.liq).toFixed(3) + "</td>";
      }
      html += "</tr>";
    }
    tbody.innerHTML = html;
  }

  function apply(t, opts) {
    opts = opts || {};
    t = clampT(t);
    if (t === null) return;
    var p = byT[String(t)];
    if (!p) return;

    slider.value = String(t);
    if (tempInput && document.activeElement !== tempInput) {
      tempInput.value = String(t);
    }

    var bounds = scaleBounds();
    updateScaleLabels(bounds);
    setDial(dialLiq, p.liq, bounds);
    if (liqVal) liqVal.textContent = fmtP(displayP(p.liq));

    if (hasGlide) {
      setDial(dialVap, p.vap, bounds);
      if (vapVal) vapVal.textContent = fmtP(displayP(p.vap));
      var glide = Math.abs(p.liq - p.vap);
      if (glideOut) {
        glideOut.textContent = "ΔP " + glide.toFixed(2) + " bar (glide)";
      }
    } else if (glideOut) {
      glideOut.textContent = "Bubble ≈ dew";
    }

    if (!opts.fromPressure && pressureInput && document.activeElement !== pressureInput) {
      syncingPressure = true;
      var phase = (pressurePhase && pressurePhase.value) || "liq";
      var show = phase === "vap" ? p.vap : p.liq;
      pressureInput.value = displayP(show).toFixed(2);
      syncingPressure = false;
    }

    if (!opts.fromPressure) {
      setPressureTempDisplay(t);
      setPressureHint("");
    }

    renderTable(t);
  }

  function setPressureTempDisplay(t) {
    if (!pressureTemp) return;
    if (t === null || t === undefined || isNaN(t)) {
      pressureTemp.textContent = "—";
      return;
    }
    var n = Number(t);
    pressureTemp.textContent = (n > 0 ? "+" : "") + String(n);
  }

  function setPressureHint(msg) {
    if (!pressureHint) return;
    if (!msg) {
      pressureHint.hidden = true;
      pressureHint.textContent = "";
      return;
    }
    pressureHint.hidden = false;
    pressureHint.textContent = msg;
  }

  function applyFromPressure() {
    if (!pressureInput) return;
    var raw = parseFloat(pressureInput.value);
    if (isNaN(raw)) {
      setPressureTempDisplay(null);
      setPressureHint("Enter a numeric pressure reading.");
      return;
    }
    var phase = (pressurePhase && pressurePhase.value) || "liq";
    var hit = tempFromPressure(raw, phase);
    if (hit.t === null) return;
    apply(hit.t, { fromPressure: true });
    setPressureTempDisplay(hit.t);
    if (hit.err > 0.15) {
      var unit = mode === "bara" ? "bara" : "barg";
      setPressureHint("Closest match — ΔP ≈ " + hit.err.toFixed(2) + " " + unit + " outside exact table point.");
    } else {
      setPressureHint("");
    }
  }

  function setMode(next) {
    var prev = mode;
    mode = next === "bara" ? "bara" : "barg";
    updateUnitLabels();
    // Convert pressure field so the reading stays physically the same.
    if (pressureInput && pressureInput.value !== "" && !isNaN(parseFloat(pressureInput.value))) {
      var barg = prev === "bara"
        ? parseFloat(pressureInput.value) - P_ATM
        : parseFloat(pressureInput.value);
      pressureInput.value = displayP(barg).toFixed(2);
    }
    apply(parseInt(slider.value, 10));
  }

  var start = clampT(slider.value);
  if (start === null) start = clampT(0);
  if (start === null) start = tMin;

  updateUnitLabels();
  apply(start);

  slider.addEventListener("input", function () {
    apply(slider.value);
  });

  if (tempInput) {
    tempInput.addEventListener("input", function () {
      var t = clampT(tempInput.value);
      if (t === null) return;
      apply(t);
    });
    tempInput.addEventListener("change", function () {
      var t = clampT(tempInput.value);
      if (t === null) {
        tempInput.value = slider.value;
        return;
      }
      apply(t);
    });
  }

  if (pressureGo) {
    pressureGo.addEventListener("click", applyFromPressure);
  }
  if (pressureInput) {
    pressureInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        applyFromPressure();
      }
    });
    pressureInput.addEventListener("change", applyFromPressure);
  }
  if (pressurePhase && pressurePhase.tagName === "SELECT") {
    pressurePhase.addEventListener("change", function () {
      if (pressureInput && pressureInput.value !== "") applyFromPressure();
      else apply(parseInt(slider.value, 10));
    });
  }

  if (modeBarg) modeBarg.addEventListener("click", function () { setMode("barg"); });
  if (modeBara) modeBara.addEventListener("click", function () { setMode("bara"); });

  if (table) {
    table.addEventListener("click", function (ev) {
      var tr = ev.target.closest("tr[data-t]");
      if (!tr) return;
      apply(tr.getAttribute("data-t"));
    });
  }
})();
