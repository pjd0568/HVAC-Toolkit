/* First-party product events. Posts allowlisted names to /e. No calculation values. */
(function () {
  "use strict";

  function attributionProps() {
    var props = {};
    try {
      if (!sessionStorage.getItem("hvac.attr.sent")) {
        sessionStorage.setItem("hvac.attr.sent", "1");
        if (document.referrer) props.referrer = document.referrer;
        props.landing = window.location.pathname || "";
      }
    } catch (e) { /* private mode */ }
    return props;
  }

  function send(event, props) {
    var merged = Object.assign({}, attributionProps(), props || {});
    var body = JSON.stringify({ event: event, props: merged });
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

  function toolFrom(host) {
    return (host && host.getAttribute("data-calculator")) || "";
  }

  function markStarted(host) {
    if (!host || host.getAttribute("data-calc-started")) return false;
    host.setAttribute("data-calc-started", "1");
    send("calculator_start", { tool: toolFrom(host) });
    return true;
  }

  function calcHostFromEvent(e) {
    var t = e.target;
    if (!t || !t.closest) return null;
    return t.closest("[data-calculator]");
  }

  // Once per journey: first real edit or Calculate — never on page load / demo paint.
  document.addEventListener("focusin", function (e) {
    var host = calcHostFromEvent(e);
    if (!host) return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag !== "input" && tag !== "select" && tag !== "textarea") return;
    markStarted(host);
  });

  document.addEventListener("change", function (e) {
    var host = calcHostFromEvent(e);
    if (!host) return;
    markStarted(host);
  });

  document.addEventListener("input", function (e) {
    var host = calcHostFromEvent(e);
    if (!host) return;
    markStarted(host);
  }, true);

  document.addEventListener("submit", function (e) {
    var host = calcHostFromEvent(e);
    if (!host) return;
    markStarted(host);
    var form = e.target;
    if (form && form.tagName === "FORM" && form.method && form.method.toLowerCase() === "get") {
      // Mark intentional calc so server can ignore draft-restore / shared demo URLs.
      if (!form.querySelector('input[name="calc"]')) {
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "calc";
        hidden.value = "1";
        form.appendChild(hidden);
      }
    }
  }, true);

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var btn = t.closest('button[type="submit"], button[name="action"], [data-calc-submit]');
    if (!btn) return;
    var host = btn.closest("[data-calculator]");
    if (host) markStarted(host);
  }, true);

  function ctaProps(el) {
    return {
      source: el.getAttribute("data-cta-source") || el.getAttribute("data-pro-cta") || "",
      target: el.getAttribute("data-cta-target") || "",
      placement: el.getAttribute("data-cta-placement") || "",
      tool: el.getAttribute("data-cta-source") || "",
      calc_count: el.getAttribute("data-calc-count") || "",
      journey: el.getAttribute("data-journey-id") || "",
    };
  }

  function emitCtaView(el) {
    if (el.getAttribute("data-cta-viewed")) return;
    el.setAttribute("data-cta-viewed", "1");
    send("pro_cta_view", ctaProps(el));
  }

  function watchCtaVisibility(el) {
    if (!("IntersectionObserver" in window)) {
      emitCtaView(el);
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && entry.intersectionRatio > 0) {
          emitCtaView(el);
          obs.disconnect();
        }
      });
    }, { threshold: 0.25 });
    obs.observe(el);
  }

  document.querySelectorAll("[data-pro-cta]").forEach(function (el) {
    var needsResult = el.hasAttribute("data-cta-after-result");
    var hasResult = !!document.querySelector("[data-calc-complete]");
    function arm() {
      watchCtaVisibility(el);
    }
    if (!needsResult || hasResult) {
      arm();
    } else {
      document.addEventListener("hvac:calc-complete", arm);
    }
    el.addEventListener("click", function () {
      send("pro_cta_click", ctaProps(el));
    });
  });

  // Registration funnel
  if (document.querySelector("[data-registration-form]")) {
    send("register_page_view", {});
    send("registration_start", {}); // legacy name kept for older reports
    var regForm = document.querySelector("[data-registration-form]");
    if (regForm) {
      regForm.addEventListener("submit", function () {
        send("register_submit", {});
      });
    }
  }
})();
