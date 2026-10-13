/* First-party product events. Posts allowlisted names to /e. No calculation values. */
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

  document.addEventListener("focusin", function (e) {
    var host = e.target && e.target.closest && e.target.closest("[data-calculator]");
    if (!host || host.getAttribute("data-calc-started")) return;
    host.setAttribute("data-calc-started", "1");
    send("calculator_start", {
      tool: host.getAttribute("data-calculator") || "",
    });
  });

  document.querySelectorAll("[data-pro-cta]").forEach(function (el) {
    var source = el.getAttribute("data-cta-source") || el.getAttribute("data-pro-cta") || "";
    var target = el.getAttribute("data-cta-target") || "";
    if (el.getAttribute("data-cta-viewed")) return;
    el.setAttribute("data-cta-viewed", "1");
    send("pro_cta_view", { source: source, target: target });
    el.addEventListener("click", function () {
      send("pro_cta_click", { source: source, target: target });
    });
  });

  if (document.querySelector("[data-registration-form]")) {
    send("registration_start", {});
  }
})();
