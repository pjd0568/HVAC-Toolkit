/* Pipe System — compact composer + Tabulator results grid.
 *
 * Primary entry is the 2-row #sys-stage form; Add commits into the spreadsheet
 * table below. Committed rows remain editable in-place. All calc/unit work
 * stays in blueprints/pipe.py via GET /api/system-state.
 */
(function () {
  "use strict";

  var ROW_FIELDS = ["type", "dn", "flow_ls", "length", "fitting", "quantity", "label", "dp"];

  function debounce(fn, ms) {
    var t;
    return function () {
      var ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text == null ? "" : String(text);
  }

  function init() {
    var form = document.getElementById("pipe-form");
    var mount = document.getElementById("sys-grid");
    var panel = document.getElementById("sys-panel");
    var stage = document.getElementById("sys-stage");
    if (!form || !mount || !panel || typeof Tabulator === "undefined") return;

    var restoreParams = null;
    if (window.HvacDraft && HvacDraft.urlIsBare()) {
      var sysDraft = HvacDraft.load(HvacDraft.KEYS.pipeSystem);
      if (sysDraft && HvacDraft.rowCount(sysDraft, "sys") > 0) {
        restoreParams = HvacDraft.toParams(sysDraft);
      } else {
        var dutyDraft = HvacDraft.load(HvacDraft.KEYS.pipeDuty) || HvacDraft.load(HvacDraft.KEYS.pipeSizer);
        if (dutyDraft && Object.keys(dutyDraft).length) {
          restoreParams = HvacDraft.toParams(dutyDraft);
        }
      }
    }

    var PIPE_BASE = (window.PIPE_API_BASE || window.location.pathname).replace(/\/$/, "");
    var API_URL = PIPE_BASE + "/api/system-state";
    var CSV_URL = PIPE_BASE + "/system/export.csv";

    var INITIAL = window.PIPE_SYS_INITIAL || {};
    var TYPE_OPTIONS = INITIAL.type_options || [];
    var DN_OPTIONS = INITIAL.dn_options || [];
    var FITTING_GROUPS = INITIAL.fitting_groups || [];
    var DEFAULT_RAW = INITIAL.default_row_raw || {
      type: "straight", dn: "", flow_ls: "1.0", length: "5.0",
      fitting: "", quantity: "1", label: "Device", dp: "10"
    };
    var pressureSym = INITIAL.velocity_pressure_sym || "Pa";
    var GLYCOL_BY_FLUID = window.PIPE_GLYCOL_BY_FLUID || {};

    var errorBox = document.getElementById("sys-error");
    var stageResultCell = document.getElementById("sys-stage-result-cell");
    var addBtn = document.getElementById("sys-add-row");
    var clearBtn = document.getElementById("sys-clear");
    var exportLink = document.getElementById("sys-export-csv");
    var safetyMargin = document.getElementById("sys-safety-margin");

    var applying = false;
    var table = null;
    var lastGoodParams = null;

    function typeValues() {
      var o = {};
      TYPE_OPTIONS.forEach(function (opt) {
        o[opt.value] = opt.label;
      });
      return o;
    }

    function dnValues() {
      var o = {};
      DN_OPTIONS.forEach(function (opt) {
        o[String(opt.dn)] = opt.label;
      });
      return o;
    }

    function firstFittingKey() {
      for (var g = 0; g < FITTING_GROUPS.length; g++) {
        var fits = FITTING_GROUPS[g].fittings || [];
        if (fits.length) return fits[0].key;
      }
      return DEFAULT_RAW.fitting || "";
    }

    function fittingLabel(key) {
      for (var g = 0; g < FITTING_GROUPS.length; g++) {
        var fits = FITTING_GROUPS[g].fittings || [];
        for (var i = 0; i < fits.length; i++) {
          if (fits[i].key === key) return fits[i].label;
        }
      }
      return key || "";
    }

    function fittingOptionsHtml(selectedKey) {
      return FITTING_GROUPS.map(function (group) {
        var opts = (group.fittings || []).map(function (f) {
          return '<option value="' + f.key + '"' +
            (f.key === selectedKey ? " selected" : "") + ">" + f.label + "</option>";
        }).join("");
        return '<optgroup label="' + group.label + '">' + opts + "</optgroup>";
      }).join("");
    }

    function detailFromApi(row) {
      var raw = row.raw || {};
      var type = row.type || raw.type || "straight";
      if (type === "fitting") return row.fitting_key || raw.fitting || "";
      if (type === "device") return raw.label || row.label || "";
      return raw.length || row.length_display || "";
    }

    function pamFromApi(row) {
      return row.friction_or_k_display || "—";
    }

    function gridRowFromApi(row) {
      var raw = Object.assign({}, DEFAULT_RAW, row.raw || {});
      var type = row.type || raw.type || "straight";
      return {
        type: type,
        dn: raw.dn != null && raw.dn !== "" ? String(raw.dn) : (row.dn != null ? String(row.dn) : ""),
        flow_ls: raw.flow_ls || "",
        quantity: raw.quantity || String(row.quantity || "1"),
        velocity: row.velocity_display || "—",
        vp: row.velocity_pressure_display || "—",
        pam: pamFromApi(row),
        detail: detailFromApi(row),
        pd: type === "device" ? (raw.dp || row.dp_display || "") : (row.dp_display || "—"),
        length: raw.length || "",
        fitting: row.fitting_key || raw.fitting || "",
        label: raw.label || "",
        dp: raw.dp || "",
        error: row.error || null
      };
    }

    function rawFromGridRow(d) {
      var type = d.type || "straight";
      var raw = {
        type: type,
        dn: type === "device" ? "" : (d.dn || ""),
        flow_ls: type === "device" ? "" : (d.flow_ls || ""),
        length: "",
        fitting: "",
        quantity: "1",
        label: "",
        dp: ""
      };
      if (type === "straight") {
        raw.length = d.detail != null ? String(d.detail) : (d.length || "");
      } else if (type === "fitting") {
        raw.fitting = d.detail || d.fitting || firstFittingKey();
        raw.quantity = d.quantity || "1";
      } else if (type === "device") {
        raw.label = d.detail != null ? String(d.detail) : (d.label || DEFAULT_RAW.label);
        raw.dp = d.pd != null ? String(d.pd) : (d.dp || DEFAULT_RAW.dp);
      }
      return raw;
    }

    function readFieldsFrom(container) {
      var raw = {};
      ROW_FIELDS.forEach(function (f) {
        var input = container.querySelector('[data-row-field="' + f + '"]');
        raw[f] = input ? input.value : "";
      });
      return raw;
    }

    function updateFieldVisibility(container) {
      if (!container) return;
      var typeSel = container.querySelector('[data-row-field="type"]');
      var type = typeSel ? typeSel.value : "straight";
      var isDevice = type === "device";
      container.querySelectorAll("[data-pipe-size-field]").forEach(function (el) {
        el.style.display = isDevice ? "none" : "";
      });
      container.querySelectorAll("[data-type-for]").forEach(function (el) {
        var forTypes = el.getAttribute("data-type-for").split(" ");
        el.style.display = forTypes.indexOf(type) !== -1 ? "" : "none";
      });
    }

    function showError(msg) {
      if (!errorBox) return;
      errorBox.innerHTML = "";
      if (!msg) return;
      var div = document.createElement("div");
      div.className = "error";
      div.textContent = msg;
      errorBox.appendChild(div);
    }

    function updateStagePreview(system) {
      if (!stageResultCell) return;
      stageResultCell.innerHTML = "";
      if (system.stage_error) {
        var errDiv = document.createElement("div");
        errDiv.className = "error";
        errDiv.id = "sys-stage-error";
        errDiv.style.margin = "0";
        errDiv.textContent = system.stage_error;
        stageResultCell.appendChild(errDiv);
        return;
      }
      var s = system.stage;
      if (!s) return;

      var metrics = document.createElement("div");
      metrics.className = "leg-preview-metrics suffix";
      function metric(id, label, text) {
        var wrap = document.createElement("span");
        wrap.appendChild(document.createTextNode(label + " "));
        var span = document.createElement("span");
        span.id = id;
        span.textContent = text;
        wrap.appendChild(span);
        metrics.appendChild(wrap);
      }
      metric("stage-sys-velocity", "V", s.velocity_display);
      metric("stage-sys-vp", "VP", s.velocity_pressure_display);
      var fk = document.createElement("span");
      fk.id = "stage-sys-fk";
      fk.textContent = s.friction_or_k_display || "—";
      metrics.appendChild(fk);

      var dpLine = document.createElement("div");
      dpLine.className = "leg-preview-dp";
      var dpSpan = document.createElement("span");
      dpSpan.id = "stage-sys-dp";
      dpSpan.textContent = s.dp_display;
      dpLine.appendChild(dpSpan);
      dpLine.appendChild(document.createTextNode(" "));
      var symSpan = document.createElement("span");
      symSpan.className = "u";
      symSpan.textContent = system.velocity_pressure_sym || pressureSym;
      dpLine.appendChild(symSpan);

      stageResultCell.appendChild(metrics);
      stageResultCell.appendChild(dpLine);
    }

    function readDesignParams() {
      var params = new URLSearchParams();
      var fd = new FormData(form);
      fd.forEach(function (value, key) {
        if (value !== null && value !== undefined && String(value) !== "") {
          params.set(key, String(value));
        }
      });
      var mode = form.querySelector('input[name="mode"]:checked');
      if (mode) params.set("mode", mode.value);
      return params;
    }

    function syncCircuitHidden(value) {
      var h = document.getElementById("circuit-hidden");
      if (h) h.value = value;
    }

    function syncLiftHidden(value) {
      var h = document.getElementById("lift-hidden");
      if (h) h.value = value;
    }

    function syncLiftVisibility(circuit) {
      var field = document.getElementById("lift-field");
      var row = document.getElementById("head-lift-row");
      var open = circuit === "open";
      if (field) field.style.display = open ? "" : "none";
      if (row) row.style.display = open ? "" : "none";
    }

    function buildParams(opts) {
      opts = opts || {};
      var params = readDesignParams();
      var circuitEl = panel.querySelector('input[name="circuit_ui"]:checked');
      var circuit = (circuitEl && circuitEl.value) || "pressurised";
      params.set("circuit", circuit);
      var liftEl = document.getElementById("lift");
      params.set("lift", liftEl ? (liftEl.value || "0") : "0");
      syncCircuitHidden(circuit);
      if (liftEl) syncLiftHidden(liftEl.value || "0");

      var data = table ? table.getData() : [];
      params.set("sys_row_count", String(data.length));
      params.set("sys_safety_margin", safetyMargin ? (safetyMargin.value || "0") : "0");
      data.forEach(function (row, i) {
        var raw = rawFromGridRow(row);
        ROW_FIELDS.forEach(function (f) {
          params.set("sys_" + f + "_" + i, raw[f] == null ? "" : String(raw[f]));
        });
      });
      if (!opts.skipStaging && stage) {
        var stageRaw = readFieldsFrom(stage);
        ROW_FIELDS.forEach(function (f) {
          params.set("stage_" + f, stageRaw[f] == null ? "" : String(stageRaw[f]));
        });
      }
      return params;
    }

    function syncReportForm(system) {
      var reportForm = document.querySelector('form[action*="system/report"]')
        || document.querySelector('form[action$="/report"]');
      if (!reportForm) return;
      Array.prototype.slice.call(reportForm.querySelectorAll('input[type="hidden"]')).forEach(function (inp) {
        var n = inp.name || "";
        if (n.indexOf("sys_") === 0 || n.indexOf("stage_") === 0 || n === "circuit" || n === "lift") {
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
      var head = system.head || {};
      var hf = head.fields || {};
      var circuitEl = panel.querySelector('input[name="circuit_ui"]:checked');
      addHidden("circuit", (circuitEl && circuitEl.value) || hf.circuit || "pressurised");
      var liftEl = document.getElementById("lift");
      addHidden("lift", (liftEl && liftEl.value) || hf.lift || "");
    }

    function applyHeadState(head) {
      if (!head) return;
      var note = document.getElementById("head-note");
      if (note) note.textContent = head.note || "";
      var fluid = document.getElementById("sys-fluid-label");
      if (fluid) fluid.textContent = head.fluid_label || "—";
      var circuit = document.getElementById("head-circuit-label");
      if (circuit) circuit.textContent = head.circuit_label || "";
      var liftVal = document.getElementById("head-lift-val");
      if (liftVal) liftVal.textContent = head.lift_display || "";
      var liftSym = document.getElementById("head-lift-sym");
      if (liftSym) liftSym.textContent = head.lift_sym || "";
      var st = document.getElementById("head-static-summary");
      if (st) st.textContent = (head.static && head.static.summary) || "—";
      var fr = document.getElementById("head-friction-summary");
      if (fr) fr.textContent = (head.friction && head.friction.summary) || "—";
      var pu = document.getElementById("head-pump-summary");
      if (pu) pu.textContent = (head.pump && head.pump.summary) || "—";
      var circ = (head.fields && head.fields.circuit) || "pressurised";
      syncLiftVisibility(circ);
      var radio = panel.querySelector('input[name="circuit_ui"][value="' + circ + '"]');
      if (radio) radio.checked = true;
      syncCircuitHidden(circ);
    }

    function applyTotals(system) {
      setText("sys-total", system.total_display);
      setText("sys-total-sym", system.total_sym);
      setText("sys-margin-amount", system.margin_amount_display || "0");
      setText("sys-margin-sym", system.total_sym);
      setText("sys-total-margin", system.total_with_margin_display || system.total_display);
      setText("sys-total-margin-sym", system.total_sym);
      if (safetyMargin && document.activeElement !== safetyMargin) {
        safetyMargin.value = String(Math.round(system.safety_margin || 0));
      }
      if (exportLink) {
        exportLink.href = CSV_URL + "?" + buildParams().toString();
      }
      syncReportForm(system);
    }

    function paramsFromSystemApi(system) {
      var params = readDesignParams();
      var head = system.head || {};
      var hf = head.fields || {};
      var circuit = hf.circuit || "pressurised";
      var circuitEl = panel.querySelector('input[name="circuit_ui"]:checked');
      if (circuitEl) circuit = circuitEl.value;
      params.set("circuit", circuit);
      var liftEl = document.getElementById("lift");
      params.set("lift", (liftEl && liftEl.value) || hf.lift || "0");

      var rows = system.rows || [];
      params.set("sys_row_count", String(system.row_count != null ? system.row_count : rows.length));
      params.set("sys_safety_margin", String(Math.round(system.safety_margin || 0)));
      rows.forEach(function (row, i) {
        var raw = row.raw || {};
        var idx = row.index != null ? row.index : i;
        ROW_FIELDS.forEach(function (f) {
          params.set("sys_" + f + "_" + idx, raw[f] == null ? "" : String(raw[f]));
        });
      });
      var stageRaw = system.stage_raw || {};
      ROW_FIELDS.forEach(function (f) {
        params.set("stage_" + f, stageRaw[f] == null ? "" : String(stageRaw[f]));
      });
      return params;
    }

    function persistDraft(params, opts) {
      opts = opts || {};
      var p = params || lastGoodParams;
      if (!p) return;
      var qs = p.toString();
      var url = window.location.pathname + (qs ? "?" + qs : "");
      history.replaceState(null, "", url);
      if (window.HvacDraft) {
        if (HvacDraft.saveProtectRows(HvacDraft.KEYS.pipeSystem, p, "sys", opts)) {
          lastGoodParams = p;
        }
        var duty = {};
        HvacDraft.PIPE_DUTY_KEYS.forEach(function (k) {
          if (p.has(k)) duty[k] = p.get(k);
        });
        HvacDraft.save(HvacDraft.KEYS.pipeDuty, duty);
      } else {
        lastGoodParams = p;
      }
    }

    function replaceUrl() {
      persistDraft(lastGoodParams);
    }

    function refreshDnSelect(selected) {
      var stageDn = document.getElementById("stage_dn");
      if (!stageDn) return;
      var prev = selected != null ? String(selected) : stageDn.value;
      stageDn.innerHTML = "";
      DN_OPTIONS.forEach(function (opt) {
        var el = document.createElement("option");
        el.value = String(opt.dn);
        el.textContent = opt.label;
        if (el.value === prev) el.selected = true;
        stageDn.appendChild(el);
      });
      if (!stageDn.value && DN_OPTIONS.length) {
        stageDn.value = String(DN_OPTIONS[0].dn);
      }
    }

    function applySystemState(system, opts) {
      opts = opts || {};
      applying = true;

      function finish() {
        try {
          TYPE_OPTIONS = system.type_options || TYPE_OPTIONS;
          DN_OPTIONS = system.dn_options || DN_OPTIONS;
          FITTING_GROUPS = system.fitting_groups || FITTING_GROUPS;
          pressureSym = system.velocity_pressure_sym || pressureSym;
          if (system.default_row_raw) DEFAULT_RAW = system.default_row_raw;

          refreshDnSelect(system.stage_raw && system.stage_raw.dn);

          updateStagePreview(system);
          applyTotals(system);
          applyHeadState(system.head);
          persistDraft(paramsFromSystemApi(system), opts);
          rewriteSizeLinks();
          showError(null);
        } finally {
          applying = false;
        }
      }

      if (!opts.previewOnly) {
        return Promise.resolve(table.replaceData((system.rows || []).map(gridRowFromApi)))
          .then(finish)
          .catch(finish);
      }
      finish();
      return Promise.resolve(system);
    }

    function fetchSystem(overrides, opts) {
      opts = opts || {};
      var params = opts.params ? new URLSearchParams(opts.params.toString()) : buildParams(opts);
      if (overrides) {
        Object.keys(overrides).forEach(function (k) { params.set(k, overrides[k]); });
      }
      return fetch(API_URL + "?" + params.toString(), {
        headers: { Accept: "application/json" }
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          return applySystemState(data, opts).then(function () { return data; });
        })
        .catch(function () {
          showError("Could not reach the server — check your connection and try again.");
        });
    }

    var debouncedFetch = debounce(function () { fetchSystem(); }, 280);
    var debouncedPreview = debounce(function () {
      fetchSystem(null, { previewOnly: true });
    }, 280);

    function isEditable(cell) {
      var field = cell.getField();
      var d = cell.getRow().getData();
      var type = d.type || "straight";
      if (field === "type") return true;
      if (field === "dn" || field === "flow_ls") return type !== "device";
      if (field === "detail") return true;
      if (field === "pd") return type === "device";
      return false;
    }

    function detailEditor(cell, onRendered, success, cancel) {
      var d = cell.getRow().getData();
      var type = d.type || "straight";
      if (type === "fitting") {
        var sel = document.createElement("select");
        sel.className = "leg-grid-editor";
        sel.innerHTML = fittingOptionsHtml(d.detail || d.fitting || firstFittingKey());
        onRendered(function () { sel.focus(); });
        sel.addEventListener("change", function () { success(sel.value); });
        sel.addEventListener("blur", function () { success(sel.value); });
        return sel;
      }
      var input = document.createElement("input");
      input.type = "text";
      input.className = "leg-grid-editor";
      input.value = cell.getValue() == null ? "" : String(cell.getValue());
      onRendered(function () { input.focus(); input.select(); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { success(input.value); }
        if (e.key === "Escape") { cancel(); }
      });
      input.addEventListener("blur", function () { success(input.value); });
      return input;
    }

    function detailFormatter(cell) {
      var d = cell.getRow().getData();
      var type = d.type || "straight";
      var val = cell.getValue();
      if (type === "fitting") return fittingLabel(val);
      if (type === "device") return val || "";
      return val == null || val === "" ? "" : String(val);
    }

    function rowFormatter(row) {
      var el = row.getElement();
      var d = row.getData();
      if (d.error) el.classList.add("leg-grid-row-error");
      else el.classList.remove("leg-grid-row-error");
    }

    table = new Tabulator(mount, {
      data: (INITIAL.rows || []).map(gridRowFromApi),
      layout: "fitData",
      renderVertical: "basic",
      renderHorizontal: "basic",
      reactiveData: false,
      selectableRows: false,
      rowHeight: 22,
      placeholder: "No rows yet — fill the form above and press Add.",
      columnHeaderVertAlign: "middle",
      rowFormatter: rowFormatter,
      columns: [
        {
          title: "Item", field: "item", minWidth: 40,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          formatter: function (cell) { return String(cell.getRow().getPosition(true)); }
        },
        {
          title: "Type", field: "type", minWidth: 70,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: "list", editorParams: { values: typeValues() },
          formatter: function (cell) {
            var map = { straight: "Straight", fitting: "Fitting", device: "Device" };
            return map[cell.getValue()] || cell.getValue() || "";
          },
          editable: isEditable
        },
        {
          title: "DN", field: "dn", minWidth: 70,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: "list", editorParams: function () {
            return { values: dnValues() };
          },
          formatter: function (cell) {
            var d = cell.getRow().getData();
            if ((d.type || "") === "device") return "—";
            var map = dnValues();
            var v = cell.getValue();
            return map[String(v)] || v || "";
          },
          editable: isEditable
        },
        {
          title: "Flow", field: "flow_ls", minWidth: 55,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: "input", editable: isEditable,
          formatter: function (cell) {
            var d = cell.getRow().getData();
            if ((d.type || "") === "device") return "—";
            var v = cell.getValue();
            return v == null || v === "" ? "" : String(v);
          }
        },
        {
          title: "Vel", field: "velocity", minWidth: 50,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false, editable: false
        },
        {
          title: "VP", field: "vp", minWidth: 55,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false, editable: false
        },
        {
          title: "Pa/m", field: "pam", minWidth: 55,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false, editable: false
        },
        {
          title: "m", field: "detail", minWidth: 90,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: detailEditor, formatter: detailFormatter, editable: isEditable, tooltip: true
        },
        {
          title: "Qty", field: "quantity", minWidth: 42,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: "input",
          editable: function (cell) {
            return (cell.getRow().getData().type || "") === "fitting";
          },
          formatter: function (cell) {
            var d = cell.getRow().getData();
            if ((d.type || "") !== "fitting") return "—";
            var v = cell.getValue();
            return v == null || v === "" ? "1" : String(v);
          }
        },
        {
          title: "PD", field: "pd", minWidth: 55,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          editor: "input", editable: isEditable,
          formatter: function (cell) {
            var d = cell.getRow().getData();
            var v = cell.getValue();
            if (d.error) {
              var wrap = document.createElement("div");
              wrap.textContent = v == null ? "—" : String(v);
              var err = document.createElement("div");
              err.className = "leg-grid-row-error-text";
              err.textContent = d.error;
              wrap.appendChild(err);
              return wrap;
            }
            return v == null ? "" : String(v);
          }
        },
        {
          title: "Del", field: "_del", minWidth: 36, width: 36,
          widthGrow: 0, widthShrink: 0,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, resizable: false,
          formatter: function () {
            return "<button type=\"button\" class=\"leg-grid-remove\" aria-label=\"Remove row\" title=\"Delete\">×</button>";
          },
          cellClick: function (e, cell) {
            if (!e.target.closest(".leg-grid-remove")) return;
            cell.getRow().delete().then(function () { fetchSystem(); });
          }
        }
      ]
    });

    function redrawGrid() {
      if (!table) return;
      try { table.redraw(true); } catch (e) { /* ignore */ }
    }

    table.on("tableBuilt", redrawGrid);
    table.on("dataProcessed", redrawGrid);

    if (typeof ResizeObserver !== "undefined") {
      var roTimer = null;
      var ro = new ResizeObserver(function () {
        clearTimeout(roTimer);
        roTimer = setTimeout(redrawGrid, 40);
      });
      ro.observe(mount.parentElement || panel);
    }
    window.addEventListener("resize", redrawGrid);

    table.on("cellEdited", function (cell) {
      if (applying) return;
      var field = cell.getField();
      var row = cell.getRow();
      var d = row.getData();

      if (field === "type") {
        if (d.type === "device") {
          row.update({
            dn: "", flow_ls: "", velocity: "—", vp: "—", pam: "—",
            detail: d.detail || DEFAULT_RAW.label, pd: d.pd || DEFAULT_RAW.dp
          });
        } else if (d.type === "fitting") {
          var fk = d.fitting || firstFittingKey();
          row.update({ detail: fk, fitting: fk, quantity: d.quantity || "1" });
        } else if (!d.detail) {
          row.update({ detail: DEFAULT_RAW.length });
        }
      }
      debouncedFetch();
    });

    // Composer: live preview; Add commits into the grid
    if (stage) {
      updateFieldVisibility(stage);
      stage.addEventListener("change", function (evt) {
        var target = evt.target;
        if (!target.hasAttribute("data-row-field")) return;
        if (target.getAttribute("data-row-field") === "type") {
          updateFieldVisibility(stage);
        }
        fetchSystem(null, { previewOnly: true });
      });
      stage.addEventListener("input", function (evt) {
        if (evt.target.hasAttribute("data-row-field")) debouncedPreview();
      });
    }

    function clearStagingItemFields() {
      if (!stage) return;
      ["length", "fitting", "quantity", "label", "dp"].forEach(function (f) {
        var input = stage.querySelector('[data-row-field="' + f + '"]');
        if (!input) return;
        if (input.tagName === "SELECT") {
          if (input.options.length) input.selectedIndex = 0;
        } else if (f === "length") {
          input.value = DEFAULT_RAW.length || "";
        } else if (f === "quantity") {
          input.value = DEFAULT_RAW.quantity || "1";
        } else if (f === "label") {
          input.value = DEFAULT_RAW.label || "";
        } else if (f === "dp") {
          input.value = DEFAULT_RAW.dp || "";
        } else {
          input.value = "";
        }
      });
    }

    if (addBtn) {
      addBtn.addEventListener("click", function () {
        if (!stage) return;
        var existingCount = table.getDataCount();
        var stagingRaw = readFieldsFrom(stage);
        var overrides = { sys_row_count: String(existingCount + 1) };
        ROW_FIELDS.forEach(function (f) {
          overrides["sys_" + f + "_" + existingCount] = stagingRaw[f];
        });
        fetchSystem(overrides).then(function () {
          clearStagingItemFields();
          updateFieldVisibility(stage);
          fetchSystem(null, { previewOnly: true });
        });
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        applying = true;
        table.replaceData([]).then(function () {
          applying = false;
          if (safetyMargin) safetyMargin.value = "0";
          fetchSystem(null, { allowEmpty: true });
        });
      });
    }

    if (safetyMargin) {
      safetyMargin.addEventListener("input", debounce(function () { fetchSystem(); }, 300));
      safetyMargin.addEventListener("change", function () { fetchSystem(); });
    }

    // System parameters (circuit / lift)
    panel.addEventListener("change", function (evt) {
      var t = evt.target;
      if (!t) return;
      if (t.name === "circuit_ui") {
        syncLiftVisibility(t.value);
        syncCircuitHidden(t.value);
        debouncedFetch();
      }
    });
    panel.addEventListener("input", function (evt) {
      var t = evt.target;
      if (t && t.id === "lift") {
        syncLiftHidden(t.value || "0");
        debouncedFetch();
      }
    });

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

    var checkedCircuit = panel.querySelector('input[name="circuit_ui"]:checked');
    if (checkedCircuit) syncLiftVisibility(checkedCircuit.value);

    function syncGlycol() {
      var fluid = document.getElementById("fluid");
      var glycol = document.getElementById("glycol-field");
      var glycolSel = document.getElementById("glycol_pct");
      if (!fluid || !glycol || !glycolSel) return;
      var isWater = fluid.value === "water";
      glycol.hidden = isWater;
      if (isWater) return;
      var opts = GLYCOL_BY_FLUID[fluid.value] || [];
      var current = glycolSel.value;
      glycolSel.innerHTML = "";
      opts.forEach(function (opt) {
        var el = document.createElement("option");
        el.value = String(opt.pct);
        el.textContent = opt.label;
        if (String(opt.pct) === current) el.selected = true;
        glycolSel.appendChild(el);
      });
      if (!glycolSel.value && opts.length) {
        glycolSel.value = String(opts[Math.floor(opts.length / 2)].pct);
      }
    }

    form.addEventListener("submit", function (evt) { evt.preventDefault(); });
    form.addEventListener("change", function (evt) {
      if (evt.target && evt.target.id === "fluid") syncGlycol();
      debouncedFetch();
    });
    form.addEventListener("input", function (evt) {
      if (evt.target && (evt.target.tagName === "INPUT" || evt.target.tagName === "SELECT")) {
        debouncedFetch();
      }
    });
    syncGlycol();

    applyTotals(INITIAL);
    updateStagePreview(INITIAL);
    applyHeadState(INITIAL.head);
    rewriteSizeLinks();
    if (restoreParams) {
      lastGoodParams = restoreParams;
      fetchSystem(null, { params: restoreParams });
    } else if ((INITIAL.rows || []).length) {
      persistDraft(paramsFromSystemApi(INITIAL));
      fetchSystem();
    } else {
      fetchSystem(null, { previewOnly: true });
    }

    window.addEventListener("pagehide", function () {
      try { persistDraft(lastGoodParams); } catch (e) { /* ignore */ }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
