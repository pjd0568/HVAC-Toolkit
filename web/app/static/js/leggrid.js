/* Index Leg — Tabulator spreadsheet grid.
 *
 * Presentation only: every calc/unit conversion stays in blueprints/duct.py
 * via GET /api/leg-state. Columns match the Excel-style schedule
 * (# | Type | Shape | Volume | Dia/AxB | Vel | VP | Pa/m | m | PD) with
 * Type driving which cells are editable and what the m / Pa/m columns mean.
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
      duct_flow: INITIAL.duct_flow_sym || "",
      duct_dimension: INITIAL.duct_dimension_sym || "",
      duct_run_length: INITIAL.duct_run_length_sym || "",
      velocity_pressure: INITIAL.velocity_pressure_sym || "",
      friction_rate: INITIAL.friction_rate_sym || ""
    };

    var errorBox = document.getElementById("leg-error");
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
      if (type === "accessory") shape = raw.shape || "";
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

    function showError(msg) {
      if (!errorBox) return;
      errorBox.innerHTML = "";
      if (!msg) return;
      var div = document.createElement("div");
      div.className = "error";
      div.textContent = msg;
      errorBox.appendChild(div);
    }

    function buildLegParams() {
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

    function applyLegState(leg) {
      applying = true;
      try {
        var rows = (leg.rows || []).map(gridRowFromApi);
        table.replaceData(rows);
        applyTotals(leg);
        showError(null);
      } finally {
        applying = false;
      }
    }

    function fetchLegState() {
      return fetch(LEG_API_URL + "?" + buildLegParams().toString(), {
        headers: { "Accept": "application/json" }
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          applyLegState(data);
          return data;
        })
        .catch(function () {
          showError("Could not reach the server — check your connection and try again.");
        });
    }

    var debouncedFetch = debounce(function () { fetchLegState(); }, 280);

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
      layout: "fitColumns",
      reactiveData: false,
      selectableRows: false,
      placeholder: "No rows — click “+ Add row” to start the index leg.",
      columnHeaderVertAlign: "middle",
      rowFormatter: rowFormatter,
      columns: [
        {
          title: "Item",
          field: "item",
          width: 54,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          formatter: function (cell) {
            return String(cell.getRow().getPosition(true));
          }
        },
        {
          title: "Type",
          field: "type",
          width: 118,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: "list",
          editorParams: { values: typeValues() },
          formatter: "lookup",
          formatterParams: typeValues(),
          editable: isEditable
        },
        {
          title: "Shape",
          field: "shape",
          width: 100,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: "list",
          editorParams: { values: shapeValues() },
          formatter: "lookup",
          formatterParams: shapeValues(),
          editable: isEditable
        },
        {
          title: "Volume",
          field: "volume",
          width: 78,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: "input",
          editable: isEditable
        },
        {
          title: "Dia/AxB",
          field: "size",
          width: 100,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: "input",
          editable: isEditable
        },
        {
          title: "Vel",
          field: "velocity",
          width: 70,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editable: false
        },
        {
          title: "VP",
          field: "vp",
          width: 70,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editable: false
        },
        {
          title: "Pa/m",
          field: "pam",
          width: 78,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editable: false
        },
        {
          title: "m",
          field: "detail",
          minWidth: 120,
          widthGrow: 1,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: detailEditor,
          formatter: detailFormatter,
          editable: isEditable
        },
        {
          title: "PD",
          field: "pd",
          width: 78,
          hozAlign: "center",
          headerHozAlign: "center",
          headerSort: false,
          editor: "input",
          editable: isEditable,
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
          title: "",
          field: "_del",
          width: 44,
          hozAlign: "center",
          headerSort: false,
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
          row.update({ shape: "circular", velocity: "—", vp: "—", pam: "—",
            detail: d.detail || DEFAULT_RAW.label, pd: d.pd || DEFAULT_RAW.dp });
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
        var parts = parseSizeEdit(d.size, d.shape || "circular");
        row.update(parts);
      }

      debouncedFetch();
    });

    if (addBtn) {
      addBtn.addEventListener("click", function () {
        var data = table.getData();
        var last = data.length ? data[data.length - 1] : null;
        var base = Object.assign({}, DEFAULT_RAW);
        if (last) {
          base.type = last.type || base.type;
          base.shape = last.shape || base.shape;
          base.volume = last.volume || base.volume;
          base.diameter = last.diameter || base.diameter;
          base.width = last.width || base.width;
          base.height = last.height || base.height;
          base.major = last.major || base.major;
          base.minor = last.minor || base.minor;
        }
        var seed = gridRowFromApi({
          type: base.type,
          shape: base.shape,
          size_edit: sizeEditFromRaw(base, base.shape),
          velocity_display: "…",
          velocity_pressure_display: "…",
          friction_rate_display: "…",
          dp_display: "…",
          fitting_key: base.fitting,
          raw: base,
          k: null,
          error: null
        });
        if (seed.type === "straight" || seed.type === "flex") seed.detail = base.length;
        table.addRow(seed).then(function () { fetchLegState(); });
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

    // Initial totals + export URL from server-rendered state
    applyTotals(INITIAL);
    if ((INITIAL.rows || []).length) {
      // Recompute once so Dia/AxB / displays are consistent with current units
      fetchLegState();
    } else if (exportLink && EXPORT_BASE_HREF) {
      exportLink.href = EXPORT_BASE_HREF + "?" + buildLegParams().toString();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
