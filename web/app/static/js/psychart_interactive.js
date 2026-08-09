/* Interactive psychrometric chart POC.
   Long-press to place A–D, edit below, map a process between any two.
   Geometry from server CHART payload (same as psychart.js). */

(function () {
  const el = document.getElementById("psychart");
  if (!el || typeof CHART === "undefined" || !CHART || typeof IX_CONFIG === "undefined") return;

  const W = 760, H = 500;
  const M = { top: 18, right: 64, bottom: 44, left: 14 };
  const pw = W - M.left - M.right, ph = H - M.top - M.bottom;
  const LONG_MS = 500;
  const LETTERS = ["A", "B", "C", "D"];
  const MAX = 4;

  let chart = CHART;
  /** @type {Array<{letter:string,name:string,label:string,si:object,display:object,symbols:object}>} */
  let points = [];
  /** @type {[number, number]|null} */
  let segment = null;

  const wrap = document.getElementById("ix-chart-wrap");
  const pointsEl = document.getElementById("ix-points");
  const countEl = document.getElementById("ix-count");
  const cursorEl = document.getElementById("ix-cursor");
  const toastEl = document.getElementById("ix-toast");
  const fromSel = document.getElementById("ix-from");
  const toSel = document.getElementById("ix-to");
  const processOut = document.getElementById("ix-process-out");
  const altInput = document.getElementById("ix-altitude");

  const NS = "http://www.w3.org/2000/svg";

  function x(t) { return M.left + ((t - chart.t_min) / (chart.t_max - chart.t_min)) * pw; }
  function y(w) { return M.top + ph - (w / chart.w_max) * ph; }
  function invX(px) { return chart.t_min + ((px - M.left) / pw) * (chart.t_max - chart.t_min); }
  function invY(py) { return ((M.top + ph - py) / ph) * chart.w_max; }

  function toast(msg, ms) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toastEl.hidden = true; }, ms || 2800);
  }

  function add(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    (parent || el).appendChild(n);
    return n;
  }
  function text(s, attrs, parent) {
    const n = add("text", attrs, parent);
    n.textContent = s;
    return n;
  }
  function path(pts, attrs, parent) {
    const d = pts.map((p, i) => (i ? "L" : "M") + x(p[0]).toFixed(1) + " " + y(p[1]).toFixed(1)).join(" ");
    return add("path", Object.assign({ d, fill: "none" }, attrs), parent);
  }

  function redraw() {
    while (el.firstChild) el.removeChild(el.firstChild);
    el.setAttribute("viewBox", `0 0 ${W} ${H}`);

    const clipId = "psychart-ix-clip";
    const defs = add("defs", {});
    const clip = add("clipPath", { id: clipId }, defs);
    add("rect", { x: M.left, y: M.top, width: pw, height: ph }, clip);
    const plot = add("g", { "clip-path": `url(#${clipId})` });

    const tStep = chart.t_step;
    for (let t = Math.ceil(chart.t_min / tStep) * tStep; t <= chart.t_max + 1e-9; t += tStep) {
      add("line", { x1: x(t), y1: M.top, x2: x(t), y2: M.top + ph, stroke: "#C5CCD5", "stroke-width": 1 });
      text(t.toFixed(tStep < 1 ? 1 : 0), { x: x(t), y: M.top + ph + 18, "text-anchor": "middle", "font-size": 11, fill: "#5A636E" });
    }
    const wStep = chart.w_step;
    for (let w = 0; w <= chart.w_max + 1e-9; w += wStep) {
      add("line", { x1: M.left, y1: y(w), x2: M.left + pw, y2: y(w), stroke: "#C5CCD5", "stroke-width": 1 });
      text(w.toFixed(0), { x: M.left + pw + 8, y: y(w) + 4, "font-size": 11, fill: "#5A636E" });
    }
    text(`Dry-bulb temperature (${chart.t_sym})`, { x: M.left + pw / 2, y: H - 8, "text-anchor": "middle", "font-size": 12, fill: "#12151A" });
    text(chart.w_sym, { x: M.left + pw + 30, y: M.top + 12, "font-size": 11, fill: "#5A636E" });

    for (const rh in chart.rh_curves) {
      path(chart.rh_curves[rh], { stroke: "#A8B0BA", "stroke-width": 1, "stroke-dasharray": "4 3" }, plot);
      const c = chart.rh_curves[rh];
      let lp = null;
      for (const p of c) if (p[1] <= chart.w_max * 0.97) lp = p;
      if (lp) text(rh + "%", { x: x(lp[0]) - 20, y: y(lp[1]) - 4, "font-size": 10, fill: "#6B7380" }, el);
    }
    path(chart.sat, { stroke: "#1A4F7A", "stroke-width": 2 }, plot);

    for (const seg of chart.segments || []) {
      const a = chart.points[seg[0]], b = chart.points[seg[1]];
      if (!a || !b) continue;
      add("line", {
        x1: x(a.t), y1: y(a.w), x2: x(b.t), y2: y(b.w),
        stroke: "#00A99D", "stroke-width": 2.5, "stroke-linecap": "round",
      }, plot);
    }

    const GUIDE = "#C94444";
    (chart.points || []).forEach(p => {
      const px = x(p.t), py = y(p.w), yAxisBottom = y(0);
      add("line", { x1: M.left, y1: py, x2: px, y2: py, stroke: GUIDE, "stroke-width": 1, "stroke-dasharray": "5 3" }, plot);
      add("line", { x1: px, y1: yAxisBottom, x2: px, y2: py, stroke: GUIDE, "stroke-width": 1, "stroke-dasharray": "5 3" }, plot);
      text(p.w_label, {
        x: M.left + 4, y: py - 4, "font-size": 10, "font-weight": 600, fill: GUIDE,
        stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
      });
      text(p.t_label, {
        x: px + 4, y: yAxisBottom - 4, "font-size": 10, "font-weight": 600, fill: GUIDE,
        stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
      });
    });

    (chart.points || []).forEach(p => {
      add("circle", { cx: x(p.t), cy: y(p.w), r: 6, fill: "#12151A", stroke: "#fff", "stroke-width": 1.5 });
      text(p.label, {
        x: x(p.t) + 8, y: y(p.w) - 8, "font-size": 12, "font-weight": 700, fill: "#12151A",
        stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
      });
    });

    // Invisible hit target for long-press (keeps plot interactive).
    add("rect", {
      x: M.left, y: M.top, width: pw, height: ph,
      fill: "transparent", class: "ix-hit",
    });
  }

  function svgPoint(evt) {
    const pt = el.createSVGPoint();
    const clientX = evt.clientX != null ? evt.clientX : (evt.touches && evt.touches[0] && evt.touches[0].clientX);
    const clientY = evt.clientY != null ? evt.clientY : (evt.touches && evt.touches[0] && evt.touches[0].clientY);
    if (clientX == null) return null;
    pt.x = clientX;
    pt.y = clientY;
    const ctm = el.getScreenCTM();
    if (!ctm) return null;
    return pt.matrixTransform(ctm.inverse());
  }

  function inPlot(sx, sy) {
    return sx >= M.left && sx <= M.left + pw && sy >= M.top && sy <= M.top + ph;
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body),
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({ ok: false, error: "Invalid response" }));
    if (!res.ok || data.ok === false) throw new Error(data.error || ("HTTP " + res.status));
    return data;
  }

  async function refreshChart() {
    const payload = {
      altitude: altInput ? altInput.value : "0",
      points: points.map(p => ({ letter: p.letter, name: p.name, si: p.si })),
      segment: segment,
    };
    const data = await postJson(IX_CONFIG.chartUrl, payload);
    chart = data.chart;
    redraw();
  }

  function nextLetter() {
    const used = new Set(points.map(p => p.letter));
    return LETTERS.find(L => !used.has(L)) || null;
  }

  async function placeAt(tDisp, wDisp) {
    if (points.length >= MAX) {
      toast("Maximum of 4 points (A–D). Remove one to add another.");
      return;
    }
    const letter = nextLetter();
    if (!letter) return;
    try {
      const data = await postJson(IX_CONFIG.resolveUrl, {
        altitude: altInput ? altInput.value : "0",
        letter,
        name: "",
        t_db: tDisp,
        w: wDisp,
      });
      points.push({
        letter: data.letter,
        name: data.name || "",
        label: data.label,
        si: data.si,
        display: data.display,
        symbols: data.symbols,
      });
      if (data.clamped) toast("Point clamped to saturation curve");
      else toast("Placed point " + data.letter);
      await refreshChart();
      renderPoints();
      fillProcessSelects();
    } catch (err) {
      toast(err.message || String(err));
    }
  }

  function renderPoints() {
    countEl.textContent = points.length + " / " + MAX;
    if (!points.length) {
      pointsEl.innerHTML = '<p class="ix-empty">No points yet — long-press the chart to place point A.</p>';
      return;
    }
    pointsEl.innerHTML = "";
    points.forEach((p, idx) => {
      const sym = p.symbols || {};
      const d = p.display;
      const card = document.createElement("div");
      card.className = "ix-point-card";
      card.dataset.idx = String(idx);
      card.innerHTML = `
        <div class="ix-point-head">
          <strong>Point ${p.letter}</strong>
          <button type="button" class="btn-ghost ix-remove" data-idx="${idx}">Remove</button>
        </div>
        <label class="ix-field">
          <span>Label</span>
          <input type="text" class="ix-name" data-idx="${idx}" maxlength="48" value="${escapeAttr(p.name)}" placeholder="e.g. Fresh Air">
        </label>
        <div class="ix-edit-row">
          <label class="ix-field">
            <span>Dry-bulb</span>
            <span class="ix-input-wrap">
              <input type="number" step="any" class="ix-tdb" data-idx="${idx}" value="${escapeAttr(d.t_db)}">
              <span class="u">${escapeHtml(sym.temperature || "")}</span>
            </span>
          </label>
          <label class="ix-field">
            <span>Second property</span>
            <select class="ix-prop" data-idx="${idx}">
              ${propOptions("rh")}
            </select>
          </label>
          <label class="ix-field">
            <span>Value</span>
            <span class="ix-input-wrap">
              <input type="number" step="any" class="ix-val" data-idx="${idx}" value="${escapeAttr(d.rh)}">
              <span class="u ix-val-u" data-idx="${idx}">%</span>
            </span>
          </label>
          <button type="button" class="btn-accent ix-apply" data-idx="${idx}">Update</button>
        </div>
        <table class="results ix-props">
          <tr><th>Property</th><th>Value</th></tr>
          <tr><td>Dry-bulb</td><td class="num">${escapeHtml(d.t_db)} ${escapeHtml(sym.temperature || "")}</td></tr>
          <tr><td>Wet-bulb</td><td class="num">${escapeHtml(d.t_wb)} ${escapeHtml(sym.temperature || "")}</td></tr>
          <tr><td>Dew-point</td><td class="num">${escapeHtml(d.t_dp)}${d.t_dp === "—" ? "" : " " + escapeHtml(sym.temperature || "")}</td></tr>
          <tr><td>Relative humidity</td><td class="num">${escapeHtml(d.rh)} %</td></tr>
          <tr><td>Humidity ratio</td><td class="num">${escapeHtml(d.w)} ${escapeHtml(sym.humidity_ratio || "")}</td></tr>
          <tr><td>Enthalpy</td><td class="num">${escapeHtml(d.h)} ${escapeHtml(sym.enthalpy || "")}</td></tr>
          <tr><td>Specific volume</td><td class="num">${escapeHtml(d.v)} ${escapeHtml(sym.specific_volume || "")}</td></tr>
          <tr><td>Density</td><td class="num">${escapeHtml(d.rho)} ${escapeHtml(sym.density || "")}</td></tr>
          <tr><td>Vapour pressure</td><td class="num">${escapeHtml(d.p_w)} ${escapeHtml(sym.pressure || "")}</td></tr>
        </table>
      `;
      pointsEl.appendChild(card);
    });
  }

  function propOptions(selected) {
    const props = IX_CONFIG.secondProperties || { rh: "Relative humidity (%)" };
    return Object.keys(props).map(k =>
      `<option value="${k}"${k === selected ? " selected" : ""}>${escapeHtml(props[k])}</option>`
    ).join("");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function escapeAttr(s) { return escapeHtml(s); }

  function fillProcessSelects() {
    const opts = points.map((p, i) => {
      const name = p.name ? ` — ${p.name}` : "";
      return `<option value="${i}">${p.letter}${escapeHtml(name)}</option>`;
    }).join("");
    const prevFrom = fromSel.value, prevTo = toSel.value;
    fromSel.innerHTML = opts;
    toSel.innerHTML = opts;
    if (points.length >= 2) {
      fromSel.value = prevFrom !== "" && +prevFrom < points.length ? prevFrom : "0";
      toSel.value = prevTo !== "" && +prevTo < points.length && prevTo !== fromSel.value
        ? prevTo
        : (fromSel.value === "0" ? "1" : "0");
    }
    fromSel.disabled = toSel.disabled = points.length < 2;
  }

  async function applyPoint(idx) {
    const card = pointsEl.querySelector(`.ix-point-card[data-idx="${idx}"]`);
    if (!card) return;
    const name = card.querySelector(".ix-name").value.trim();
    const t_db = card.querySelector(".ix-tdb").value;
    const prop = card.querySelector(".ix-prop").value;
    const val = card.querySelector(".ix-val").value;
    try {
      const data = await postJson(IX_CONFIG.resolveUrl, {
        altitude: altInput ? altInput.value : "0",
        letter: points[idx].letter,
        name,
        t_db,
        prop,
        val,
      });
      points[idx] = {
        letter: data.letter,
        name: data.name || "",
        label: data.label,
        si: data.si,
        display: data.display,
        symbols: data.symbols,
      };
      // Keep segment indices valid if letters unchanged.
      await refreshChart();
      renderPoints();
      fillProcessSelects();
      toast("Updated point " + data.letter);
    } catch (err) {
      toast(err.message || String(err));
    }
  }

  async function renamePoint(idx) {
    const card = pointsEl.querySelector(`.ix-point-card[data-idx="${idx}"]`);
    if (!card) return;
    const name = card.querySelector(".ix-name").value.trim();
    points[idx].name = name;
    points[idx].label = name ? `${points[idx].letter} — ${name}` : points[idx].letter;
    await refreshChart();
    fillProcessSelects();
  }

  function removePoint(idx) {
    points.splice(idx, 1);
    segment = null;
    processOut.hidden = true;
    refreshChart().then(() => {
      renderPoints();
      fillProcessSelects();
    }).catch(err => toast(err.message || String(err)));
  }

  async function mapProcess() {
    if (points.length < 2) {
      toast("Place at least two points first");
      return;
    }
    const i0 = +fromSel.value, i1 = +toSel.value;
    if (i0 === i1) {
      toast("Choose two different points");
      return;
    }
    const flow = document.getElementById("ix-flow").value;
    try {
      segment = [i0, i1];
      await refreshChart();
      const body = {
        altitude: altInput ? altInput.value : "0",
        from_si: points[i0].si,
        to_si: points[i1].si,
        from_letter: points[i0].letter,
        to_letter: points[i1].letter,
      };
      if (flow !== "") body.vol_flow = flow;
      const data = await postJson(IX_CONFIG.processUrl, body);
      let html = `<div class="ix-process-title">${escapeHtml(data.from_letter)} → ${escapeHtml(data.to_letter)}</div><ul>`;
      for (const a of data.actions) html += `<li>${escapeHtml(a)}</li>`;
      html += "</ul>";
      html += `<table class="results"><tr><th>Δ</th><th>Value</th></tr>`;
      html += `<tr><td>Dry-bulb</td><td class="num">${escapeHtml(data.delta.t)} ${escapeHtml(data.delta.t_sym)}</td></tr>`;
      html += `<tr><td>Humidity ratio</td><td class="num">${escapeHtml(data.delta.w)} ${escapeHtml(data.delta.w_sym)}</td></tr>`;
      html += `<tr><td>Enthalpy</td><td class="num">${escapeHtml(data.delta.h)} ${escapeHtml(data.delta.h_sym)}</td></tr>`;
      html += `<tr><td>Relative humidity</td><td class="num">${escapeHtml(data.delta.rh_pp)} pp</td></tr></table>`;
      if (data.rates) {
        const r = data.rates;
        html += `<div class="ix-rates"><strong>With airflow</strong><table class="results">`;
        html += `<tr><td>Dry-air mass flow</td><td class="num">${escapeHtml(r.m_da)} ${escapeHtml(r.m_da_sym)}</td></tr>`;
        html += `<tr><td>${escapeHtml(r.heat_cool_kw_label)}</td><td class="num">${escapeHtml(r.heat_cool_kw)} kW</td></tr>`;
        html += `<tr><td>Sensible</td><td class="num">${escapeHtml(r.q_sensible_kw)} kW</td></tr>`;
        html += `<tr><td>Latent</td><td class="num">${escapeHtml(r.q_latent_kw)} kW</td></tr>`;
        html += `<tr><td>${escapeHtml(r.moisture_label)}</td><td class="num">${escapeHtml(r.moisture_abs_kg_h)} kg/h</td></tr>`;
        html += `</table></div>`;
      }
      processOut.innerHTML = html;
      processOut.hidden = false;
    } catch (err) {
      toast(err.message || String(err));
    }
  }

  // Long-press handling
  let pressTimer = null;
  let pressStart = null;
  let moved = false;

  function clearPress() {
    if (pressTimer) clearTimeout(pressTimer);
    pressTimer = null;
    pressStart = null;
    moved = false;
    if (wrap) wrap.classList.remove("ix-pressing");
  }

  function onDown(evt) {
    if (evt.type === "mousedown" && evt.button !== 0) return;
    const sp = svgPoint(evt);
    if (!sp || !inPlot(sp.x, sp.y)) return;
    moved = false;
    pressStart = { x: sp.x, y: sp.y, t: invX(sp.x), w: invY(sp.y) };
    if (wrap) wrap.classList.add("ix-pressing");
    pressTimer = setTimeout(() => {
      if (!pressStart || moved) return;
      const t = pressStart.t, w = Math.max(0, pressStart.w);
      clearPress();
      placeAt(t, w);
    }, LONG_MS);
    if (evt.type === "touchstart") evt.preventDefault();
  }

  function onMove(evt) {
    const sp = svgPoint(evt);
    if (!sp) return;
    if (inPlot(sp.x, sp.y) && cursorEl) {
      const t = invX(sp.x), w = invY(sp.y);
      cursorEl.textContent = `${t.toFixed(chart.t_dp ?? 1)} ${chart.t_sym}, ${w.toFixed(chart.w_dp ?? 1)} ${chart.w_sym}`;
    }
    if (!pressStart) return;
    const dx = sp.x - pressStart.x, dy = sp.y - pressStart.y;
    if (dx * dx + dy * dy > 36) {
      moved = true;
      clearPress();
    }
  }

  function onUp() { clearPress(); }

  el.addEventListener("mousedown", onDown);
  el.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  el.addEventListener("touchstart", onDown, { passive: false });
  el.addEventListener("touchmove", onMove, { passive: true });
  el.addEventListener("touchend", onUp);
  el.addEventListener("touchcancel", onUp);
  el.addEventListener("contextmenu", e => e.preventDefault());

  pointsEl.addEventListener("click", e => {
    const rem = e.target.closest(".ix-remove");
    if (rem) { removePoint(+rem.dataset.idx); return; }
    const apply = e.target.closest(".ix-apply");
    if (apply) { applyPoint(+apply.dataset.idx); }
  });

  pointsEl.addEventListener("change", e => {
    const prop = e.target.closest(".ix-prop");
    if (!prop) return;
    const idx = +prop.dataset.idx;
    const u = pointsEl.querySelector(`.ix-val-u[data-idx="${idx}"]`);
    const val = pointsEl.querySelector(`.ix-val[data-idx="${idx}"]`);
    const p = points[idx];
    if (!u || !p) return;
    if (prop.value === "rh") {
      u.textContent = "%";
      val.value = p.display.rh;
    } else if (prop.value === "w") {
      u.textContent = p.symbols.humidity_ratio || "";
      val.value = p.display.w;
    } else if (prop.value === "twb") {
      u.textContent = p.symbols.temperature || "";
      val.value = p.display.t_wb;
    } else if (prop.value === "tdp") {
      u.textContent = p.symbols.temperature || "";
      val.value = p.display.t_dp === "—" ? "" : p.display.t_dp;
    }
  });

  let nameTimer = null;
  pointsEl.addEventListener("input", e => {
    const name = e.target.closest(".ix-name");
    if (!name) return;
    clearTimeout(nameTimer);
    nameTimer = setTimeout(() => renamePoint(+name.dataset.idx), 400);
  });

  document.getElementById("ix-map").addEventListener("click", mapProcess);
  document.getElementById("ix-reset").addEventListener("click", () => {
    points = [];
    segment = null;
    processOut.hidden = true;
    refreshChart().then(() => {
      renderPoints();
      fillProcessSelects();
      toast("Cleared");
    });
  });

  altInput && altInput.addEventListener("change", () => {
    // Re-resolve all points at the new altitude (same display T/RH).
    (async () => {
      try {
        const next = [];
        for (const p of points) {
          const data = await postJson(IX_CONFIG.resolveUrl, {
            altitude: altInput.value,
            letter: p.letter,
            name: p.name,
            t_db: p.display.t_db,
            prop: "rh",
            val: p.display.rh,
          });
          next.push({
            letter: data.letter,
            name: data.name || "",
            label: data.label,
            si: data.si,
            display: data.display,
            symbols: data.symbols,
          });
        }
        points = next;
        await refreshChart();
        renderPoints();
        fillProcessSelects();
        toast("Updated for new altitude");
      } catch (err) {
        toast(err.message || String(err));
      }
    })();
  });

  redraw();
  fillProcessSelects();
})();
