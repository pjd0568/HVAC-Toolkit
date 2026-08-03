(function () {
  var root = document.querySelector("[data-v2-wizard]");
  if (!root) return;

  var steps = Array.prototype.slice.call(root.querySelectorAll("[data-step]"));
  if (!steps.length) return;

  var labelEl = root.querySelector("[data-step-label]");
  var backBtn = root.querySelector("[data-step-back]");
  var nextBtn = root.querySelector("[data-step-next]");
  var initial = parseInt(root.getAttribute("data-initial-step") || "1", 10);
  if (isNaN(initial) || initial < 1) initial = 1;

  var params = new URLSearchParams(window.location.search);
  var fromQuery = parseInt(params.get("step") || "", 10);
  var current = !isNaN(fromQuery) && fromQuery >= 1 ? fromQuery : initial;
  if (current > steps.length) current = steps.length;

  function titles() {
    return steps.map(function (s) {
      return s.getAttribute("data-step-title") || ("Step " + s.getAttribute("data-step"));
    });
  }

  function show(n) {
    current = Math.max(1, Math.min(steps.length, n));
    steps.forEach(function (s) {
      var id = parseInt(s.getAttribute("data-step"), 10);
      s.classList.toggle("active", id === current);
    });
    if (labelEl) {
      labelEl.textContent = "Step " + current + " of " + steps.length + " · " + titles()[current - 1];
    }
    if (backBtn) backBtn.hidden = current <= 1;
    if (nextBtn) {
      var last = current >= steps.length;
      nextBtn.hidden = last;
      nextBtn.textContent = last ? "Done" : "Continue";
    }
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("step", String(current));
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (e) { /* ignore */ }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (backBtn) {
    backBtn.addEventListener("click", function () { show(current - 1); });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () { show(current + 1); });
  }

  show(current);
})();
