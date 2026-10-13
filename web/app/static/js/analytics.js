/* First-party product events. Posts to /e; does not set a cookie. */
(function () {
  "use strict";

  function send(event, props) {
    var body = JSON.stringify({ event: event, props: props || {} });
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        if (navigator.sendBeacon("/e", blob)) return;
      }
    } catch (e) { /* fall through */ }
    try {
      fetch("/e", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
        credentials: "same-origin",
      }).catch(function () {});
    } catch (e2) { /* ignore */ }
  }

  window.HvacEvents = { send: send };

  send("page_view", { route: location.pathname });

  document.addEventListener("focusin", function (e) {
    var host = e.target && e.target.closest && e.target.closest("[data-calculator]");
    if (!host || host.getAttribute("data-calc-started")) return;
    host.setAttribute("data-calc-started", "1");
    send("calculator_start", {
      calculator: host.getAttribute("data-calculator") || "",
      route: location.pathname,
    });
  });

  document.querySelectorAll("[data-calc-complete]").forEach(function (el) {
    send("calculator_complete", {
      calculator: el.getAttribute("data-calc-complete") || "",
      route: location.pathname,
    });
  });

  document.querySelectorAll("[data-pro-cta]").forEach(function (el) {
    send("pro_cta_view", {
      calculator: el.getAttribute("data-pro-cta") || "",
      route: location.pathname,
    });
    el.addEventListener("click", function () {
      send("pro_cta_click", {
        calculator: el.getAttribute("data-pro-cta") || "",
        route: location.pathname,
      });
    });
  });

  if (document.querySelector("[data-registration-form]")) {
    send("registration_start", { route: location.pathname });
  }
})();
