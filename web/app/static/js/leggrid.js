/* Index Leg — compact composer + Tabulator results grid.
 *
 * Primary entry is the 2-row #leg-stage form; Add commits into the spreadsheet
 * table below. Committed rows remain editable in-place. All calc/unit work
 * stays in blueprints/duct.py via GET /api/leg-state.
 */
(function () {
  "use strict";

  var ROW_FIELDS = ["type", "shape", "volume", "diameter", "width", "height",
                    "major", "minor", "length", "fitting", "label", "dp"];

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
    var mount = document.getElementById("leg-grid");
    var panel = document.getElementById("leg-panel");
    var stage = document.getElementById("leg-stage");
    if (!mount || !panel || typeof Tabulator === "undefined") return;

    var INITIAL = window.DUCT_LEG_INITIAL || {};
    var LEG_API_URL = (window.DUCT_API_BASE || window.location.pathname).replace(/\/$/, "") + "/api/leg-state";
    var TYPE_OPTIONS = INITIAL.type_options || [];
    var SHAPE_OPTIONS = INITIAL.shape_options || [];
    var FITTINGS_BY_SHAPE = INITIAL.fittings_by_shape || {};
    var DEFAULT_RAW = INITIAL.default_row_raw || {
      type: "straight", shape: "circular", volume: "1800", diameter: "200",
      width: "400", height: "200", major: "400", minor: "200", length: "3.0",
      fitting: "", label: "Accessory", dp: "10"
    };
    var SYMS = {
      velocity_pressure: INITIAL.velocity_pressure_sym || ""
    };

    var errorBox = document.getElementById("leg-error");
    var stageResultCell = document.getElementById("leg-stage-result-cell");
    var addBtn = document.getElementById("leg-add-row");
    var clearBtn = document.getElementById("leg-clear-table");
    var exportLink = document.getElementById("leg-export-csv");
    var safetyMargin = document.getElementById("leg-safety-margin");
    var EXPORT_BASE_HREF = exportLink ? exportLink.href.split("?")[0] : "";

    var applying = false;
    var table = null;

    function typeValues() {
      var o = {};
      TYPE_OPTIONS.forEach(function (opt) { o[opt.key] = opt.label; });
      return o;
    }

    function shapeValues() {
      var o = {};
      SHAPE_OPTIONS.forEach(function (opt) { o[opt.key] = opt.label; });
      return o;
    }

    function fittingValues(shape) {
      var o = {};
      (FITTINGS_BY_SHAPE[shape] || []).forEach(function (f) {
        o[f.key] = f.label + " (K=" + Number(f.k).toFixed(2) + ")";
      });
      return o;
    }

    function fittingLabel(shape, key) {
      var list = FITTINGS_BY_SHAPE[shape] || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].key === key) return list[i].label;
      }
      return key || "";
    }

    function fittingOptionsHtml(shape, selectedKey) {
      var list = FITTINGS_BY_SHAPE[shape] || [];
      return list.map(function (f) {
        return '<option value="' + f.key + '"' + (f.key === selectedKey ? " selected" : "") +
          ">" + f.label + "</option>";
      }).join("");
    }

    function parseSizeEdit(text, shape) {
      var t = String(text == null ? "" : text).trim();
      var empty = { diameter: "", width: "", height: "", major: "", minor: "" };
      if (!t) return empty;
      var parts = t.split(/\s*[x×,]\s*/i);
      if (shape === "circular" || parts.length < 2) {
        var one = parts[0].replace(/[^\d.+-eE]/g, "");
        if (shape === "rectangular") return { diameter: "", width: one, height: one, major: "", minor: "" };
        if (shape === "flat_oval") return { diameter: "", width: "", height: "", major: one, minor: one };
        return { diameter: one, width: "", height: "", major: "", minor: "" };
      }
      var a = parts[0].replace(/[^\d.+-eE]/g, "");
      var b = parts[1].replace(/[^\d.+-eE]/g, "");
      if (shape === "rectangular") return { diameter: "", width: a, height: b, major: "", minor: "" };
      if (shape === "flat_oval") return { diameter: "", width: "", height: "", major: a, minor: b };
      return { diameter: a, width: "", height: "", major: "", minor: "" };
    }

    function sizeEditFromRaw(raw, shape) {
      raw = raw || {};
      shape = shape || "circular";
      if (shape === "rectangular") {
        if (raw.width && raw.height) return raw.width + " x " + raw.height;
        return raw.width || raw.height || "";
      }
      if (shape === "flat_oval") {
        if (raw.major && raw.minor) return raw.major + " x " + raw.minor;
        return raw.major || raw.minor || "";
      }
      return raw.diameter || "";
    }

    function detailFromApi(row) {
      var raw = row.raw || {};
      var type = row.type || raw.type || "straight";
      if (type === "fitting") return row.fitting_key || raw.fitting || "";
      if (type === "accessory") return raw.label || row.label || "";
      return raw.length || row.length_display || "";
    }

    function pamFromApi(row) {
      var type = row.type || (row.raw && row.raw.type) || "straight";
      if (type === "accessory") return "—";
      if (type === "fitting" && row.k != null && row.k !== "") {
        return "K=" + Number(row.k).toFixed(2);
      }
      return row.friction_rate_display || "—";
    }

    function gridRowFromApi(row) {
      var raw = Object.assign({}, DEFAULT_RAW, row.raw || {});
      var type = row.type || raw.type || "straight";
      var shape = row.shape || raw.shape || "circular";
      if (type === "accessory") shape = raw.shape || "circular";
      var size = row.size_edit || sizeEditFromRaw(raw, shape || "circular");
      return {
        type: type,
        shape: shape || "circular",
        volume: raw.volume || row.volume_display || "",
        size: size,
        velocity: row.velocity_display || "—",
        vp: row.velocity_pressure_display || "—",
        pam: pamFromApi(row),
        detail: detailFromApi(row),
        pd: type === "accessory" ? (raw.dp || row.dp_display || "") : (row.dp_display || "—"),
        diameter: raw.diameter || "",
        width: raw.width || "",
        height: raw.height || "",
        major: raw.major || "",
        minor: raw.minor || "",
        length: raw.length || "",
        fitting: row.fitting_key || raw.fitting || "",
        label: raw.label || "",
        dp: raw.dp || "",
        error: row.error || null
      };
    }

    function rawFromGridRow(d) {
      var shape = d.shape || "circular";
      var sizeParts = parseSizeEdit(d.size, shape);
      var type = d.type || "straight";
      var raw = {
        type: type,
        shape: type === "accessory" ? "" : shape,
        volume: d.volume || "",
        diameter: sizeParts.diameter || d.diameter || "",
        width: sizeParts.width || d.width || "",
        height: sizeParts.height || d.height || "",
        major: sizeParts.major || d.major || "",
        minor: sizeParts.minor || d.minor || "",
        length: "",
        fitting: "",
        label: "",
        dp: ""
      };
      if (type === "straight" || type === "flex") {
        raw.length = d.detail != null ? String(d.detail) : (d.length || "");
      } else if (type === "fitting") {
        raw.fitting = d.detail || d.fitting || "";
        if (!raw.fitting) {
          var opts = FITTINGS_BY_SHAPE[shape] || [];
          if (opts.length) raw.fitting = opts[0].key;
        }
      } else if (type === "accessory") {
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

    function showError(msg) {
      if (!errorBox) return;
      errorBox.innerHTML = "";
      if (!msg) return;
      var div = document.createElement("div");
      div.className = "error";
      div.textContent = msg;
      errorBox.appendChild(div);
    }

    function updateStagePreview(leg) {
      if (!stageResultCell) return;
      stageResultCell.innerHTML = "";
      if (leg.stage_error) {
        var errDiv = document.createElement("div");
        errDiv.className = "error";
        errDiv.id = "leg-stage-error";
        errDiv.style.margin = "0";
        errDiv.textContent = leg.stage_error;
        stageResultCell.appendChild(errDiv);
        return;
      }
      var s = leg.stage;
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
      metric("stage-velocity", "V", s.velocity_display);
      metric("stage-vp", "VP", s.velocity_pressure_display);

      var fkWrap = document.createElement("span");
      fkWrap.id = "stage-fk-wrap";
      var fkLabel = document.createElement("span");
      fkLabel.id = "stage-fk-label";
      var fkVal = document.createElement("span");
      fkVal.id = "stage-friction";
      if (s.type === "fitting" && s.k != null) {
        fkLabel.textContent = "K";
        fkVal.textContent = Number(s.k).toFixed(2);
      } else if (s.type === "straight" || s.type === "flex") {
        fkLabel.textContent = "ΔP/L";
        fkVal.textContent = s.friction_rate_display || "—";
      } else {
        fkLabel.textContent = "—";
        fkVal.textContent = "";
      }
      fkWrap.appendChild(fkLabel);
      fkWrap.appendChild(document.createTextNode(" "));
      fkWrap.appendChild(fkVal);
      metrics.appendChild(fkWrap);

      var dpLine = document.createElement("div");
      dpLine.className = "leg-preview-dp";
      var dpSpan = document.createElement("span");
      dpSpan.id = "stage-dp-preview";
      dpSpan.textContent = s.dp_display;
      dpLine.appendChild(dpSpan);
      dpLine.appendChild(document.createTextNode(" "));
      var symSpan = document.createElement("span");
      symSpan.className = "u";
      symSpan.textContent = SYMS.velocity_pressure || "";
      dpLine.appendChild(symSpan);

      stageResultCell.appendChild(metrics);
      stageResultCell.appendChild(dpLine);
    }

    function buildLegParams(opts) {
      opts = opts || {};
      var p = new URLSearchParams();
      var data = table ? table.getData() : [];
      p.set("leg_row_count", String(data.length));
      p.set("leg_safety_margin", safetyMargin ? (safetyMargin.value || "0") : "0");
      data.forEach(function (row, i) {
        var raw = rawFromGridRow(row);
        ROW_FIELDS.forEach(function (f) {
          p.set("leg_" + f + "_" + i, raw[f] == null ? "" : String(raw[f]));
        });
      });
      if (!opts.skipStaging && stage) {
        var stageRaw = readFieldsFrom(stage);
        ROW_FIELDS.forEach(function (f) {
          p.set("stage_" + f, stageRaw[f] == null ? "" : String(stageRaw[f]));
        });
      }
      return p;
    }

    function syncReportForm(leg) {
      var form = document.querySelector("form[action$=\"/report\"]");
      if (!form) return;
      Array.prototype.slice.call(form.querySelectorAll("input[name^=\"leg_\"]")).forEach(function (el) {
        el.parentNode.removeChild(el);
      });
      function addHidden(name, val) {
        var inp = document.createElement("input");
        inp.type = "hidden";
        inp.name = name;
        inp.value = val == null ? "" : String(val);
        form.appendChild(inp);
      }
      addHidden("leg_row_count", leg.row_count || 0);
      addHidden("leg_safety_margin", leg.safety_margin || 0);
      (leg.rows || []).forEach(function (row) {
        var i = row.index;
        var raw = row.raw || {};
        ROW_FIELDS.forEach(function (f) {
          var v = raw[f];
          if (f === "type") v = row.type || raw.type || "";
          if (f === "shape") v = row.shape || raw.shape || "";
          addHidden("leg_" + f + "_" + i, v == null ? "" : String(v));
        });
      });
    }

    function applyTotals(leg) {
      setText("leg-total", leg.total_display);
      setText("leg-total-sym", leg.total_sym);
      setText("leg-margin-amount", leg.margin_amount_display || "0");
      setText("leg-margin-sym", leg.total_sym);
      setText("leg-total-margin", leg.total_with_margin_display || leg.total_display);
      setText("leg-total-margin-sym", leg.total_sym);
      if (safetyMargin && document.activeElement !== safetyMargin) {
        safetyMargin.value = String(Math.round(leg.safety_margin || 0));
      }
      if (exportLink && EXPORT_BASE_HREF) {
        exportLink.href = EXPORT_BASE_HREF + "?" + buildLegParams().toString();
      }
      syncReportForm(leg);
    }

    function applyLegState(leg, opts) {
      opts = opts || {};
      applying = true;
      try {
        if (!opts.previewOnly) {
          var rows = (leg.rows || []).map(gridRowFromApi);
          table.replaceData(rows);
        }
        updateStagePreview(leg);
        applyTotals(leg);
        showError(null);
      } finally {
        applying = false;
      }
    }

    function fetchLegState(overrides, opts) {
      var params = buildLegParams(opts);
      if (overrides) {
        Object.keys(overrides).forEach(function (k) { params.set(k, overrides[k]); });
      }
      return fetch(LEG_API_URL + "?" + params.toString(), {
        headers: { "Accept": "application/json" }
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          applyLegState(data, opts);
          return data;
        })
        .catch(function () {
          showError("Could not reach the server — check your connection and try again.");
        });
    }

    var debouncedFetch = debounce(function () { fetchLegState(); }, 280);
    var debouncedPreview = debounce(function () {
      fetchLegState(null, { previewOnly: true });
    }, 280);

    function isEditable(cell) {
      var field = cell.getField();
      var d = cell.getRow().getData();
      var type = d.type || "straight";
      if (field === "type") return true;
      if (field === "shape" || field === "volume" || field === "size") {
        return type !== "accessory";
      }
      if (field === "detail") return true;
      if (field === "pd") return type === "accessory";
      return false;
    }

    function detailEditor(cell, onRendered, success, cancel) {
      var d = cell.getRow().getData();
      var type = d.type || "straight";
      if (type === "fitting") {
        var sel = document.createElement("select");
        sel.className = "leg-grid-editor";
        var values = fittingValues(d.shape || "circular");
        Object.keys(values).forEach(function (key) {
          var opt = document.createElement("option");
          opt.value = key;
          opt.textContent = values[key];
          if (key === (d.detail || d.fitting)) opt.selected = true;
          sel.appendChild(opt);
        });
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
      if (type === "fitting") return fittingLabel(d.shape || "circular", val);
      if (type === "accessory") return val || "";
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
      reactiveData: false,
      selectableRows: false,
      rowHeight: 22,
      placeholder: "No rows yet — fill the form above and press Add.",
      columnHeaderVertAlign: "middle",
      rowFormatter: rowFormatter,
      columns: [
        {
          title: "Item", field: "item", width: 40,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          formatter: function (cell) { return String(cell.getRow().getPosition(true)); }
        },
        {
          title: "Type", field: "type", width: 72,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          editor: "list", editorParams: { values: typeValues() },
          formatter: function (cell) {
            var map = { straight: "Straight", flex: "Flex", fitting: "Fitting", accessory: "Accessory" };
            return map[cell.getValue()] || cell.getValue() || "";
          },
          editable: isEditable
        },
        {
          title: "Shape", field: "shape", width: 72,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          editor: "list", editorParams: { values: shapeValues() },
          formatter: function (cell) {
            var map = { circular: "Circ", rectangular: "Rect", flat_oval: "FO" };
            return map[cell.getValue()] || cell.getValue() || "";
          },
          editable: isEditable
        },
        {
          title: "Volume", field: "volume", width: 64,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          editor: "input", editable: isEditable
        },
        {
          title: "Dia/AxB", field: "size", width: 78,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          editor: "input", editable: isEditable
        },
        {
          title: "Vel", field: "velocity", width: 52,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, editable: false
        },
        {
          title: "VP", field: "vp", width: 52,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, editable: false
        },
        {
          title: "Pa/m", field: "pam", width: 58,
          hozAlign: "center", headerHozAlign: "center", headerSort: false, editable: false
        },
        {
          title: "m", field: "detail", width: 72,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
          editor: detailEditor, formatter: detailFormatter, editable: isEditable,
          tooltip: true
        },
        {
          title: "PD", field: "pd", width: 58,
          hozAlign: "center", headerHozAlign: "center", headerSort: false,
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
          title: "", field: "_del", width: 32, hozAlign: "center", headerSort: false,
          formatter: function () {
            return "<button type=\"button\" class=\"btn-ghost leg-grid-remove\" aria-label=\"Remove row\">✕</button>";
          },
          cellClick: function (e, cell) {
            if (!e.target.closest(".leg-grid-remove")) return;
            cell.getRow().delete().then(function () { fetchLegState(); });
          }
        }
      ]
    });

    table.on("cellEdited", function (cell) {
      if (applying) return;
      var field = cell.getField();
      var row = cell.getRow();
      var d = row.getData();

      if (field === "type") {
        if (d.type === "accessory") {
          row.update({
            shape: "circular", velocity: "—", vp: "—", pam: "—",
            detail: d.detail || DEFAULT_RAW.label, pd: d.pd || DEFAULT_RAW.dp
          });
        } else if (d.type === "fitting") {
          var fits = FITTINGS_BY_SHAPE[d.shape || "circular"] || [];
          var fk = d.fitting || (fits[0] && fits[0].key) || "";
          row.update({ detail: fk, fitting: fk });
        } else if (!d.detail) {
          row.update({ detail: DEFAULT_RAW.length });
        }
      }
      if (field === "shape" && d.type === "fitting") {
        var fits2 = FITTINGS_BY_SHAPE[d.shape || "circular"] || [];
        var fk2 = (fits2[0] && fits2[0].key) || "";
        row.update({ detail: fk2, fitting: fk2 });
      }
      if (field === "size" || field === "shape") {
        row.update(parseSizeEdit(d.size, d.shape || "circular"));
      }
      debouncedFetch();
    });

    // -- Composer: live preview; Add commits into the grid -----------------
    if (stage) {
      updateFieldVisibility(stage);
      stage.addEventListener("change", function (evt) {
        var target = evt.target;
        if (!target.hasAttribute("data-row-field")) return;
        if (target.getAttribute("data-row-field") === "shape") {
          refreshFittingOptions(stage, target.value);
        }
        if (target.getAttribute("data-row-field") === "type" ||
            target.getAttribute("data-row-field") === "shape") {
          updateFieldVisibility(stage);
        }
        fetchLegState(null, { previewOnly: true });
      });
      stage.addEventListener("input", function (evt) {
        if (evt.target.hasAttribute("data-row-field")) debouncedPreview();
      });
    }

    function clearStagingItemFields() {
      if (!stage) return;
      ["length", "fitting", "label", "dp"].forEach(function (f) {
        var input = stage.querySelector('[data-row-field="' + f + '"]');
        if (!input) return;
        if (input.tagName === "SELECT") {
          if (input.options.length) input.selectedIndex = 0;
        } else if (f === "length") {
          input.value = DEFAULT_RAW.length || "";
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
        var overrides = { leg_row_count: String(existingCount + 1) };
        ROW_FIELDS.forEach(function (f) {
          overrides["leg_" + f + "_" + existingCount] = stagingRaw[f];
        });
        // Include existing rows in params; override count + new row fields
        fetchLegState(overrides).then(function () {
          clearStagingItemFields();
          updateFieldVisibility(stage);
          fetchLegState(null, { previewOnly: true });
        });
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        applying = true;
        table.replaceData([]).then(function () {
          applying = false;
          if (safetyMargin) safetyMargin.value = "0";
          fetchLegState();
        });
      });
    }

    if (safetyMargin) {
      safetyMargin.addEventListener("input", debounce(function () { fetchLegState(); }, 300));
      safetyMargin.addEventListener("change", function () { fetchLegState(); });
    }

    applyTotals(INITIAL);
    updateStagePreview(INITIAL);
    if ((INITIAL.rows || []).length) {
      fetchLegState();
    } else {
      fetchLegState(null, { previewOnly: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
