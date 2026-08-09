(function () {
  function closeSheets() {
    document.querySelectorAll(".v2-menu.open, .v2-climate-sheet.open").forEach(function (el) {
      el.classList.remove("open");
    });
  }

  function closeNavDrops(except) {
    document.querySelectorAll(".v2-nav-drop.open").forEach(function (el) {
      if (except && el === except) return;
      el.classList.remove("open");
      var btn = el.querySelector(".v2-nav-drop-btn");
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
  }

  function openNavDrop(drop) {
    if (!drop) return;
    closeNavDrops(drop);
    drop.classList.add("open");
    var btn = drop.querySelector(".v2-nav-drop-btn");
    if (btn) btn.setAttribute("aria-expanded", "true");
  }

  var menuBtn = document.getElementById("v2-menu-btn");
  var menu = document.getElementById("v2-menu");
  var climateBtn = document.getElementById("v2-climate-btn");
  var climate = document.getElementById("v2-climate-sheet");
  var suiteNav = document.querySelector(".v2-suite-nav");
  var hoverCloseTimer = null;

  if (menuBtn && menu) {
    menuBtn.addEventListener("click", function () {
      menu.classList.add("open");
    });
    menu.querySelectorAll("[data-v2-close]").forEach(function (el) {
      el.addEventListener("click", closeSheets);
    });
  }
  if (climateBtn && climate) {
    climateBtn.addEventListener("click", function () {
      climate.classList.add("open");
    });
    climate.querySelectorAll("[data-v2-close]").forEach(function (el) {
      el.addEventListener("click", closeSheets);
    });
  }

  document.querySelectorAll(".v2-nav-drop").forEach(function (drop) {
    var btn = drop.querySelector(".v2-nav-drop-btn");
    if (!btn) return;

    // Desktop: open on hover; stays open until another suite item is hovered
    // or the pointer leaves the whole suite nav.
    drop.addEventListener("mouseenter", function () {
      if (hoverCloseTimer) {
        clearTimeout(hoverCloseTimer);
        hoverCloseTimer = null;
      }
      openNavDrop(drop);
    });

    // Keyboard / touch: click toggles.
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (drop.classList.contains("open")) {
        closeNavDrops();
      } else {
        openNavDrop(drop);
      }
    });
  });

  if (suiteNav) {
    suiteNav.addEventListener("mouseleave", function () {
      hoverCloseTimer = setTimeout(function () {
        closeNavDrops();
        hoverCloseTimer = null;
      }, 120);
    });
    suiteNav.addEventListener("mouseenter", function () {
      if (hoverCloseTimer) {
        clearTimeout(hoverCloseTimer);
        hoverCloseTimer = null;
      }
    });
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".v2-nav-drop")) closeNavDrops();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeSheets();
      closeNavDrops();
    }
  });
})();
