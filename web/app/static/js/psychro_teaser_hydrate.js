/* After signup, apply homepage `hvac_teaser_state` into Single Point. */
(function () {
  "use strict";

  var STORAGE_KEY = "hvac_teaser_state";
  var raw;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    return;
  }
  if (!raw) return;

  var data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e2) { /* ignore */ }
    return;
  }

  function clear() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
  }

  function hydrate(payload) {
    return fetch("/psychrometrics/hydrate-teaser", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res.json().then(function (body) {
        return { okHttp: res.ok, body: body };
      });
    });
  }

  function go(url) {
    clear();
    window.location.replace(url || "/psychrometrics/");
  }

  if (data.si && data.si.t_db != null) {
    hydrate({ system: data.system || "SI", si: data.si })
      .then(function (result) {
        if (result.okHttp && result.body && result.body.ok) {
          go(result.body.redirect || "/psychrometrics/");
        } else {
          clear();
        }
      })
      .catch(function () { clear(); });
    return;
  }

  if (!data.pendingInputs) {
    clear();
    return;
  }

  fetch("/api/psychro/teaser", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(data.pendingInputs),
  })
    .then(function (res) { return res.json(); })
    .then(function (calc) {
      if (!calc || !calc.ok || !calc.si) {
        clear();
        return null;
      }
      return hydrate({ system: calc.system || data.system || "SI", si: calc.si });
    })
    .then(function (result) {
      if (!result) return;
      if (result.okHttp && result.body && result.body.ok) {
        go(result.body.redirect || "/psychrometrics/");
      } else {
        clear();
      }
    })
    .catch(function () { clear(); });
})();
