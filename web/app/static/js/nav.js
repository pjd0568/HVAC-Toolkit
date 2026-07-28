/* Collapsible sidebar nav groups — remembers open/closed in localStorage.
   Default: collapsed. Section with the active page stays open. */
(function () {
  "use strict";

  var STORAGE_KEY = "hvac-nav-groups-v2";
  var nav = document.getElementById("sidebar-nav");
  if (!nav) return;

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function saveState(state) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) { /* ignore quota / private mode */ }
  }

  function setExpanded(group, expanded) {
    group.classList.toggle("collapsed", !expanded);
    var btn = group.querySelector(".nav-group-toggle");
    if (btn) btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  var state = loadState();
  var groups = nav.querySelectorAll("[data-nav-group]");

  groups.forEach(function (group) {
    var id = group.getAttribute("data-nav-id") || "";
    var hasActive = !!group.querySelector(".nav-item.active");
    var expanded;
    if (hasActive) {
      expanded = true; // always open the section you're in
    } else if (Object.prototype.hasOwnProperty.call(state, id)) {
      expanded = !!state[id];
    } else {
      expanded = false; // default collapsed
    }
    setExpanded(group, expanded);

    var btn = group.querySelector(".nav-group-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var next = group.classList.contains("collapsed");
      setExpanded(group, next);
      state[id] = next;
      saveState(state);
    });
  });
})();
