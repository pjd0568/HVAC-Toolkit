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

  var menuBtn = document.getElementById("v2-menu-btn");
  var menu = document.getElementById("v2-menu");
  var climateBtn = document.getElementById("v2-climate-btn");
  var climate = document.getElementById("v2-climate-sheet");

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
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var willOpen = !drop.classList.contains("open");
      closeNavDrops();
      if (willOpen) {
        drop.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
      }
    });
  });

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
