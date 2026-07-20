/* Psychrometric chart renderer. Reads global CHART payload, draws into #psychart.
   Fresh implementation for this product. x: dry-bulb, y: moisture content (axis
   on the right, as psychrometric charts are conventionally drawn). CHART is
   already converted to the active display system (SI or IP) server-side
   (app.chart.chart_payload) and carries its own unit symbols, grid step and
   per-point labels, so nothing here hardcodes a unit. */

(function () {
  const el = document.getElementById("psychart");
  if (!el || typeof CHART === "undefined" || !CHART) return;

  const W = 760, H = 500;
  const M = { top: 18, right: 64, bottom: 44, left: 14 };
  const pw = W - M.left - M.right, ph = H - M.top - M.bottom;

  const x = t => M.left + ((t - CHART.t_min) / (CHART.t_max - CHART.t_min)) * pw;
  const y = w => M.top + ph - (w / CHART.w_max) * ph;

  const NS = "http://www.w3.org/2000/svg";
  el.setAttribute("viewBox", `0 0 ${W} ${H}`);

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
  const clipId = "psychart-clip";
  const defs = add("defs", {});
  const clip = add("clipPath", { id: clipId }, defs);
  add("rect", { x: M.left, y: M.top, width: pw, height: ph }, clip);
  const plot = add("g", { "clip-path": `url(#${clipId})` });

  /* grid -- step size comes from the payload (app.chart._nice_step), so the
     on-screen chart and the PDF chart (app.reports.chart) draw the same
     gridlines regardless of unit system. */
  const tStep = CHART.t_step;
  for (let t = Math.ceil(CHART.t_min / tStep) * tStep; t <= CHART.t_max + 1e-9; t += tStep) {
    add("line", { x1: x(t), y1: M.top, x2: x(t), y2: M.top + ph, stroke: "#E3E7ED", "stroke-width": 1 });
    text(t.toFixed(tStep < 1 ? 1 : 0), { x: x(t), y: M.top + ph + 18, "text-anchor": "middle", "font-size": 11, fill: "#64707F" });
  }
  const wStep = CHART.w_step;
  for (let w = 0; w <= CHART.w_max + 1e-9; w += wStep) {
    add("line", { x1: M.left, y1: y(w), x2: M.left + pw, y2: y(w), stroke: "#E3E7ED", "stroke-width": 1 });
    text(w.toFixed(0), { x: M.left + pw + 8, y: y(w) + 4, "font-size": 11, fill: "#64707F" });
  }
  text(`Dry-bulb temperature (${CHART.t_sym})`, { x: M.left + pw / 2, y: H - 8, "text-anchor": "middle", "font-size": 12, fill: "#1B2531" });
  text(CHART.w_sym, { x: M.left + pw + 30, y: M.top + 12, "font-size": 11, fill: "#64707F" });

  /* RH curves */
  for (const rh in CHART.rh_curves) {
    path(CHART.rh_curves[rh], { stroke: "#C3CEDA", "stroke-width": 1, "stroke-dasharray": "4 3" }, plot);
    const c = CHART.rh_curves[rh];
    let lp = null;
    for (const p of c) if (p[1] <= CHART.w_max * 0.97) lp = p;
    if (lp) text(rh + "%", { x: x(lp[0]) - 20, y: y(lp[1]) - 4, "font-size": 10, fill: "#8B99A9" }, el);
  }

  /* saturation curve */
  path(CHART.sat, { stroke: "#2B5C8A", "stroke-width": 2 }, plot);

  /* process segments */
  for (const seg of CHART.segments) {
    const a = CHART.points[seg[0]], b = CHART.points[seg[1]];
    add("line", {
      x1: x(a.t), y1: y(a.w), x2: x(b.t), y2: y(b.w),
      stroke: "#3E77AE", "stroke-width": 2.5, "stroke-linecap": "round",
    }, plot);
  }

  /* Dashed red guide lines to both axes, one pair per point, each labelled with
     the pre-formatted value from the payload -- mirrors the PDF chart
     (app.reports.chart) so the on-screen and downloaded charts read the same. */
  const GUIDE = "#D6484A";
  CHART.points.forEach(p => {
    const px = x(p.t), py = y(p.w), yAxisBottom = y(0);
    add("line", {
      x1: M.left, y1: py, x2: px, y2: py,
      stroke: GUIDE, "stroke-width": 1, "stroke-dasharray": "5 3",
    }, plot);
    add("line", {
      x1: px, y1: yAxisBottom, x2: px, y2: py,
      stroke: GUIDE, "stroke-width": 1, "stroke-dasharray": "5 3",
    }, plot);
    text(p.w_label, {
      x: M.left + 4, y: py - 4, "font-size": 10, "font-weight": 600, fill: GUIDE,
      stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
    });
    text(p.t_label, {
      x: px + 4, y: yAxisBottom - 4, "font-size": 10, "font-weight": 600, fill: GUIDE,
      stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
    });
  });

  /* state points + labels */
  CHART.points.forEach(p => {
    add("circle", { cx: x(p.t), cy: y(p.w), r: 5, fill: "#1B2531", stroke: "#fff", "stroke-width": 1.5 });
    text(p.label, {
      x: x(p.t) + 8, y: y(p.w) - 8, "font-size": 12, "font-weight": 700, fill: "#1B2531",
      stroke: "#FFFFFF", "stroke-width": 3, "paint-order": "stroke",
    });
  });
})();
