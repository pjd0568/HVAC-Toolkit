/* Pipe System — Stage 2 pressure-drop builder.
 *
 * Reads/writes system-row form fields, calls /api/system-state, and rebuilds
 * the committed-rows table from already-formatted server JSON. No engine or
 * unit maths is duplicated here. State travels in `sys_*` / `stage_*` query
 * params (plus the Design Inputs from #pipe-form) so a built schedule stays
 * a shareable URL — same convention as duct Index Leg.
 */
(function () {
  "use strict";

  var form = document.getElementById("pipe-form");
  var panel = document.getElementById("sys-panel");
  if (!form || !panel) return;

  var API_URL = window.location.pathname.replace(/\/$/, "") + "/api/system-state";
  var CSV_URL = window.location.pathname.replace(/\/$/, "") + "/system/export.csv";

  var ROW_FIELDS = ["type", "dn", "flow_ls", "length", "fitting", "label", "dp"];

  // Seeded from the first API response / initial page render.
  var typeOptions = [];
  var dnOptions = [];
  var fittingGroups = [];
  var dutyFlowLs = "";
  var pressureSym = "Pa";
  var lengthSym = "m";

  function debounce(fn, wait) {
    var t = null;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, wait);
    };
  }

  function readDesignParams() {
    var params = new URLSearchParams();
    var fd = new FormData(form);
    fd.forEach(function (value, key) {
      if (value !== null && value !== undefined && String(value) !== "") {
        params.set(key, String(value));
      }
    });
    // Radios: FormData includes the checked one; ensure mode is present.
    var mode = form.querySelector('input[name="mode"]:checked');
    if (mode) params.set("mode", mode.value);
    return params;
  }

  function readStageFields(params) {
    ROW_FIELDS.forEach(function (field) {
      var el = panel.querySelector('[name="stage_' + field + '"]');
      if (el) params.set("stage_" + field, el.value);
    });
  }

  function readCommittedRows(params) {
    var rows = panel.querySelectorAll("#sys-rows-body tr[data-sys-row]");
    params.set("sys_row_count", String(rows.length));
    rows.forEach(function (tr, i) {
      ROW_FIELDS.forEach(function (field) {
        var el = tr.querySelector('[data-row-field="' + field + '"]');
        if (el) params.set("sys_" + field + "_" + i, el.value);
      });
    });
    var margin = document.getElementById("sys-safety-margin");
    if (margin) params.set("sys_safety_margin", margin.value || "0");
  }

  function buildParams() {
    var params = readDesignParams();
    readStageFields(params);
    readCommittedRows(params);
    return params;
  }

  function syncTypeVisibility(scope) {
    var typeEl = scope.querySelector('[data-row-field="type"]');
    if (!typeEl) return;
    var t = typeEl.value;
    function vis(sel, on) {
      scope.querySelectorAll(sel).forEach(function (el) {
        el.style.visibility = on ? "visible" : "hidden";
      });
    }
    vis(".sys-field-length", t === "straight");
    vis(".sys-field-fitting", t === "fitting");
    vis(".sys-field-desc", t === "device");
    vis(".sys-field-dp", t === "device");
    var dn = scope.querySelector('[data-row-field="dn"]');
    var flow = scope.querySelector('[data-row-field="flow_ls"]');
    if (dn) dn.style.visibility = t === "device" ? "hidden" : "visible";
    if (flow) flow.style.visibility = t === "device" ? "hidden" : "visible";
  }

  function syncAllTypeVisibility() {
    var stage = document.getElementById("sys-stage-row");
    if (stage) syncTypeVisibility(stage);
    panel.querySelectorAll("#sys-rows-body tr[data-sys-row]").forEach(syncTypeVisibility);
  }

  function fillSelect(sel, options, selected) {
    sel.innerHTML = "";
    options.forEach(function (opt) {
      var el = document.createElement("option");
      el.value = String(opt.value != null ? opt.value : opt.dn);
      el.textContent = opt.label;
      if (String(el.value) === String(selected)) el.selected = true;
      sel.appendChild(el);
    });
  }

  function fillFittingSelect(sel, selected) {
    sel.innerHTML = "";
    fittingGroups.forEach(function (group) {
      var og = document.createElement("optgroup");
      og.label = group.label;
      (group.fittings || []).forEach(function (f) {
        var el = document.createElement("option");
        el.value = f.key;
        el.textContent = f.label;
        if (f.key === selected) el.selected = true;
        og.appendChild(el);
      });
      sel.appendChild(og);
    });
  }

  function buildRowTr(row) {
    var tr = document.createElement("tr");
    tr.setAttribute("data-sys-row", "");
    tr.setAttribute("data-index", String(row.index));
    if (row.error) tr.className = "row-error";

    var raw = row.raw || {};
    var num = document.createElement("td");
    num.className = "leg-row-num";
    num.textContent = String(row.index + 1);
    tr.appendChild(num);

    // Type
    var tdType = document.createElement("td");
    tdType.className = "leg-cell";
    var typeSel = document.createElement("select");
    typeSel.setAttribute("data-row-field", "type");
    typeSel.name = "sys_type_" + row.index;
    fillSelect(typeSel, typeOptions, raw.type || row.type || "straight");
    tdType.appendChild(typeSel);
    tr.appendChild(tdType);

    // DN
    var tdDn = document.createElement("td");
    tdDn.className = "leg-cell";
    var dnSel = document.createElement("select");
    dnSel.setAttribute("data-row-field", "dn");
    dnSel.name = "sys_dn_" + row.index;
    fillSelect(dnSel, dnOptions.map(function (o) {
      return { value: o.dn, label: o.label };
    }), raw.dn || row.dn || "");
    tdDn.appendChild(dnSel);
    tr.appendChild(tdDn);

    // Flow
    var tdFlow = document.createElement("td");
    tdFlow.className = "leg-cell";
    var flowIn = document.createElement("input");
    flowIn.setAttribute("data-row-field", "flow_ls");
    flowIn.name = "sys_flow_ls_" + row.index;
    flowIn.value = raw.flow_ls || "";
    flowIn.placeholder = dutyFlowLs;
    flowIn.setAttribute("inputmode", "decimal");
    tdFlow.appendChild(flowIn);
    tr.appendChild(tdFlow);

    // Length
    var tdLen = document.createElement("td");
    tdLen.className = "leg-cell sys-field-length";
    var lenIn = document.createElement("input");
    lenIn.setAttribute("data-row-field", "length");
    lenIn.name = "sys_length_" + row.index;
    lenIn.value = raw.length || "";
    lenIn.setAttribute("inputmode", "decimal");
    tdLen.appendChild(lenIn);
    tr.appendChild(tdLen);

    // Fitting
    var tdFit = document.createElement("td");
    tdFit.className = "leg-cell sys-field-fitting";
    var fitSel = document.createElement("select");
    fitSel.setAttribute("data-row-field", "fitting");
    fitSel.name = "sys_fitting_" + row.index;
    fillFittingSelect(fitSel, raw.fitting || row.fitting_key || "");
    tdFit.appendChild(fitSel);
    tr.appendChild(tdFit);

    // Description
    var tdDesc = document.createElement("td");
    tdDesc.className = "leg-cell sys-field-desc";
    var labelIn = document.createElement("input");
    labelIn.setAttribute("data-row-field", "label");
    labelIn.name = "sys_label_" + row.index;
    labelIn.value = raw.label || "";
    tdDesc.appendChild(labelIn);
    tr.appendChild(tdDesc);

    // Manual ΔP
    var tdDp = document.createElement("td");
    tdDp.className = "leg-cell sys-field-dp";
    var dpIn = document.createElement("input");
    dpIn.setAttribute("data-row-field", "dp");
    dpIn.name = "sys_dp_" + row.index;
    dpIn.value = raw.dp || "";
    dpIn.setAttribute("inputmode", "decimal");
    tdDp.appendChild(dpIn);
    tr.appendChild(tdDp);

    // Result
    var tdRes = document.createElement("td");
    tdRes.className = "num";
    tdRes.appendChild(document.createTextNode((row.dp_display || "—") + " "));
    var u = document.createElement("span");
    u.className = "u";
    u.textContent = pressureSym;
    tdRes.appendChild(u);
    if (row.error) {
      var err = document.createElement("div");
      err.className = "suffix leg-row-error-text";
      err.textContent = row.error;
      tdRes.appendChild(err);
    }
    tr.appendChild(tdRes);

    // Remove
    var tdAct = document.createElement("td");
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-ghost";
    btn.setAttribute("data-sys-remove", "");
    btn.setAttribute("aria-label", "Remove row");
    btn.textContent = "✕";
    tdAct.appendChild(btn);
    tr.appendChild(tdAct);

    syncTypeVisibility(tr);
    return tr;
  }

  function updateStageResult(system) {
    var cell = document.getElementById("sys-stage-result-cell");
    if (!cell) return;
    while (cell.firstChild) cell.removeChild(cell.firstChild);
    if (system.stage_error) {
      var err = document.createElement("div");
      err.className = "error";
      err.style.margin = "0";
      err.textContent = system.stage_error;
      cell.appendChild(err);
      return;
    }
    if (!system.stage) return;
    var meta = document.createElement("div");
    meta.className = "suffix";
    meta.textContent = "V: " + (system.stage.velocity_display || "—") +
      " · " + (system.stage.friction_or_k_display || "—");
    cell.appendChild(meta);
    var dpLine = document.createElement("div");
    var dpSpan = document.createElement("span");
    dpSpan.id = "stage-sys-dp";
    dpSpan.textContent = system.stage.dp_display || "";
    dpLine.appendChild(dpSpan);
    dpLine.appendChild(document.createTextNode(" "));
    var us = document.createElement("span");
    us.className = "u";
    us.textContent = system.velocity_pressure_sym || pressureSym;
    dpLine.appendChild(us);
    cell.appendChild(dpLine);
  }

  function applySystemState(system) {
    typeOptions = (system.type_options || []).map(function (o) {
      return { value: o.value, label: o.label };
    });
    dnOptions = system.dn_options || [];
    fittingGroups = system.fitting_groups || [];
    dutyFlowLs = system.duty_flow_ls || "";
    pressureSym = system.velocity_pressure_sym || "Pa";
    lengthSym = system.run_length_sym || "m";

    // Refresh stage DN options (material may have changed via design form).
    var stageDn = document.getElementById("stage_dn");
    if (stageDn) {
      var prev = stageDn.value;
      fillSelect(stageDn, dnOptions.map(function (o) {
        return { value: o.dn, label: o.label };
      }), prev || (system.stage_raw && system.stage_raw.dn) || "");
    }

    var body = document.getElementById("sys-rows-body");
    if (body) {
      while (body.firstChild) body.removeChild(body.firstChild);
      (system.rows || []).forEach(function (row) {
        body.appendChild(buildRowTr(row));
      });
    }

    updateStageResult(system);

    var total = document.getElementById("sys-total");
    if (total) total.textContent = system.total_display || "0";
    var totalSym = document.getElementById("sys-total-sym");
    if (totalSym) totalSym.textContent = system.total_sym || pressureSym;

    var margin = system.safety_margin || 0;
    var marginTr = document.getElementById("sys-margin-tr");
    var totalMarginTr = document.getElementById("sys-total-margin-tr");
    var show = margin > 0;
    if (marginTr) marginTr.style.display = show ? "" : "none";
    if (totalMarginTr) totalMarginTr.style.display = show ? "" : "none";
    var pct = document.getElementById("sys-margin-pct");
    if (pct) pct.textContent = String(Math.round(margin));
    var amt = document.getElementById("sys-margin-amount");
    if (amt) amt.textContent = system.margin_amount_display || "";
    var totM = document.getElementById("sys-total-margin");
    if (totM) totM.textContent = system.total_with_margin_display || "";

    syncAllTypeVisibility();
    syncReportForm(system);
    replaceUrl();
    updateCsvLink();
  }

  function syncReportForm(system) {
    var reportForm = document.querySelector('form[action$="/report"]');
    if (!reportForm) return;
    // Remove prior sys_* / stage_* hidden fields.
    Array.prototype.slice.call(reportForm.querySelectorAll('input[type="hidden"]')).forEach(function (inp) {
      var n = inp.name || "";
      if (n.indexOf("sys_") === 0 || n.indexOf("stage_") === 0) {
        inp.parentNode.removeChild(inp);
      }
    });
    function addHidden(name, value) {
      var inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = name;
      inp.value = value == null ? "" : String(value);
      reportForm.appendChild(inp);
    }
    addHidden("sys_row_count", system.row_count || 0);
    addHidden("sys_safety_margin", system.safety_margin || 0);
    (system.rows || []).forEach(function (row) {
      ROW_FIELDS.forEach(function (field) {
        addHidden("sys_" + field + "_" + row.index, (row.raw && row.raw[field]) || "");
      });
    });
  }

  function replaceUrl() {
    var params = buildParams();
    var qs = params.toString();
    var url = window.location.pathname + (qs ? "?" + qs : "");
    history.replaceState(null, "", url);
  }

  function updateCsvLink() {
    var a = document.getElementById("sys-export-csv");
    if (!a) return;
    a.href = CSV_URL + "?" + buildParams().toString();
  }

  var fetching = false;
  var pending = false;

  function fetchSystem() {
    if (fetching) {
      pending = true;
      return;
    }
    fetching = true;
    var params = buildParams();
    fetch(API_URL + "?" + params.toString(), {
      headers: { Accept: "application/json" },
    })
      .then(function (res) { return res.json(); })
      .then(function (system) {
        applySystemState(system);
      })
      .catch(function () { /* leave table as-is on network error */ })
      .finally(function () {
        fetching = false;
        if (pending) {
          pending = false;
          fetchSystem();
        }
      });
  }

  var debouncedFetch = debounce(fetchSystem, 200);

  function onPanelChange(evt) {
    var t = evt.target;
    if (!t || !panel.contains(t)) return;
    if (t.getAttribute("data-row-field") === "type") {
      syncTypeVisibility(t.closest("tr") || panel);
    }
    debouncedFetch();
  }

  panel.addEventListener("change", onPanelChange);
  panel.addEventListener("input", function (evt) {
    var t = evt.target;
    if (!t || t.tagName !== "INPUT") return;
    if (t.hasAttribute("data-row-field") || t.id === "sys-safety-margin") {
      debouncedFetch();
    }
  });

  var addBtn = document.getElementById("sys-add-row");
  if (addBtn) {
    addBtn.addEventListener("click", function () {
      var params = buildParams();
      var n = parseInt(params.get("sys_row_count") || "0", 10) || 0;
      ROW_FIELDS.forEach(function (field) {
        var el = panel.querySelector('[name="stage_' + field + '"]');
        params.set("sys_" + field + "_" + n, el ? el.value : "");
      });
      params.set("sys_row_count", String(n + 1));
      // Preserve type/dn for the next staging draft; clear length/fitting specifics lightly.
      var stageLen = document.getElementById("stage_length");
      if (stageLen) stageLen.value = stageLen.value; // keep
      var stageLabel = document.getElementById("stage_label");
      if (stageLabel) stageLabel.value = "";
      var stageDp = document.getElementById("stage_dp");
      if (stageDp) stageDp.value = stageDp.value;

      fetching = true;
      fetch(API_URL + "?" + params.toString(), {
        headers: { Accept: "application/json" },
      })
        .then(function (res) { return res.json(); })
        .then(function (system) {
          applySystemState(system);
          // After commit, leave stage type/dn/flow; clear length for next straight, etc.
          var typeEl = document.getElementById("stage_type");
          if (typeEl && typeEl.value === "straight" && stageLen) {
            /* keep length for similar runs */
          }
        })
        .finally(function () { fetching = false; });
    });
  }

  panel.addEventListener("click", function (evt) {
    var btn = evt.target.closest("[data-sys-remove]");
    if (!btn) return;
    var tr = btn.closest("tr[data-sys-row]");
    if (tr && tr.parentNode) {
      tr.parentNode.removeChild(tr);
      fetchSystem();
    }
  });

  var clearBtn = document.getElementById("sys-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      var body = document.getElementById("sys-rows-body");
      if (body) {
        while (body.firstChild) body.removeChild(body.firstChild);
      }
      var margin = document.getElementById("sys-safety-margin");
      if (margin) margin.value = "0";
      fetchSystem();
    });
  }

  // Design Inputs changes (Calculate is a full GET) — when user changes material
  // without submitting, system DN options should refresh on next system edit.
  // Also preserve system state when selecting a DN size row: those links are
  // rebuilt server-side without sys_*; after JS boot we rewrite them.
  function rewriteSizeLinks() {
    var params = buildParams();
    document.querySelectorAll("a.pipe-row-link").forEach(function (a) {
      try {
        var u = new URL(a.href, window.location.origin);
        var dn = u.searchParams.get("selected_dn");
        var merged = new URLSearchParams(params.toString());
        if (dn) merged.set("selected_dn", dn);
        a.href = u.pathname + "?" + merged.toString();
      } catch (e) { /* ignore */ }
    });
  }

  syncAllTypeVisibility();
  updateCsvLink();
  rewriteSizeLinks();

  // If the URL already carries sys rows, ensure footer/state matches; otherwise
  // just seed stage preview against current design inputs.
  fetchSystem();
})();
