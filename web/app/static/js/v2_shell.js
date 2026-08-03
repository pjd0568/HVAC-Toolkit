(function () {
  function closeAll() {
    document.querySelectorAll(".v2-menu.open, .v2-climate-sheet.open").forEach(function (el) {
      el.classList.remove("open");
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
      el.addEventListener("click", closeAll);
    });
  }
  if (climateBtn && climate) {
    climateBtn.addEventListener("click", function () {
      climate.classList.add("open");
    });
    climate.querySelectorAll("[data-v2-close]").forEach(function (el) {
      el.addEventListener("click", closeAll);
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll();
  });
})();
