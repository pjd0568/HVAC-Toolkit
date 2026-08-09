/* Drafts for V2 calculator modules — survive switching related pages in-tab. */
(function (global) {
  "use strict";

  var PREFIX = "hvac.v2.draft.";

  function paramsToObject(params) {
    var obj = {};
    if (!params) return obj;
    if (typeof params.forEach === "function") {
      params.forEach(function (value, k) {
        if (value === null || value === undefined) return;
        obj[k] = String(value);
      });
    } else {
      Object.keys(params).forEach(function (k) {
        var value = params[k];
        if (value === null || value === undefined) return;
        obj[k] = String(value);
      });
    }
    return obj;
  }

  function save(key, params) {
    try {
      var obj = paramsToObject(params);
      sessionStorage.setItem(PREFIX + key, JSON.stringify(obj));
    } catch (e) { /* private mode / quota */ }
  }

  function load(key) {
    try {
      var raw = sessionStorage.getItem(PREFIX + key);
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || typeof obj !== "object") return null;
      return obj;
    } catch (e) {
      return null;
    }
  }

  function clear(key) {
    try {
      sessionStorage.removeItem(PREFIX + key);
    } catch (e) { /* ignore */ }
  }

  function toParams(obj) {
    var p = new URLSearchParams();
    if (!obj) return p;
    Object.keys(obj).forEach(function (k) {
      if (obj[k] === null || obj[k] === undefined) return;
      p.set(k, String(obj[k]));
    });
    return p;
  }

  function pick(obj, keys) {
    var out = {};
    if (!obj) return out;
    keys.forEach(function (k) {
      if (obj[k] !== null && obj[k] !== undefined) out[k] = String(obj[k]);
    });
    return out;
  }

  function rowCount(objOrParams, prefix) {
    prefix = prefix || "leg";
    var key = prefix + "_row_count";
    var raw;
    if (!objOrParams) return 0;
    if (typeof objOrParams.get === "function") raw = objOrParams.get(key);
    else raw = objOrParams[key];
    var n = parseInt(raw || "0", 10);
    return isNaN(n) ? 0 : Math.max(0, n);
  }

  /**
   * Save draft, but never replace a draft that has rows with an empty one
   * unless opts.allowEmpty is true (Clear table).
   */
  function saveProtectRows(key, params, rowPrefix, opts) {
    opts = opts || {};
    var incoming = rowCount(params, rowPrefix);
    if (incoming === 0 && !opts.allowEmpty) {
      var existing = load(key);
      if (existing && rowCount(existing, rowPrefix) > 0) return false;
    }
    save(key, params);
    return true;
  }

  function urlIsBare() {
    var s = window.location.search || "";
    return s === "" || s === "?";
  }

  function restoreViaReload(key, fallbackKeys) {
    if (!urlIsBare()) return false;
    var draft = load(key);
    if ((!draft || !Object.keys(draft).length) && fallbackKeys && fallbackKeys.length) {
      for (var i = 0; i < fallbackKeys.length; i++) {
        draft = load(fallbackKeys[i]);
        if (draft && Object.keys(draft).length) break;
        draft = null;
      }
    }
    if (!draft || !Object.keys(draft).length) return false;
    var qs = toParams(draft).toString();
    if (!qs) return false;
    window.location.replace(window.location.pathname + "?" + qs);
    return true;
  }

  function saveFromUrl(key) {
    if (urlIsBare()) return;
    save(key, new URLSearchParams(window.location.search));
  }

  global.HvacDraft = {
    save: save,
    load: load,
    clear: clear,
    toParams: toParams,
    pick: pick,
    rowCount: rowCount,
    saveProtectRows: saveProtectRows,
    urlIsBare: urlIsBare,
    restoreViaReload: restoreViaReload,
    saveFromUrl: saveFromUrl,
    KEYS: {
      ductSizer: "duct.sizer",
      ductIndexLeg: "duct.index_leg",
      pipeSizer: "pipe.sizer",
      pipeSystem: "pipe.system",
      pipeDuty: "pipe.duty"
    },
    PIPE_DUTY_KEYS: [
      "mode", "application", "fluid", "material", "glycol_pct",
      "load", "delta_t", "lwt", "flow_ls", "selected_dn"
    ]
  };
})(window);
