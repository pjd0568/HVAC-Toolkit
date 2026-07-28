/* Live altitude → barometric pressure preview for Site Conditions.
   Mirrors hvac_engine.psychrometrics.pressure_from_altitude (ASHRAE HOF Ch.1 eqn 3).
   Conversion factors come from data-* on the wrapper (set by the unit view). */
(function () {
  "use strict";

  var P_ATM = 101.325;          // kPa
  var LAPSE = 2.25577e-5;       // 1/m
  var EXP = 5.2559;
  var Z_MIN = -500.0;
  var Z_MAX = 9000.0;

  function pressureFromAltitudeM(zM) {
    if (!(zM >= Z_MIN && zM <= Z_MAX)) return null;
    return P_ATM * Math.pow(1.0 - LAPSE * zM, EXP);
  }

  function format(n, decimals) {
    var f = Math.pow(10, decimals);
    return (Math.round(n * f) / f).toFixed(decimals);
  }

  function bind(root) {
    var alt = root.querySelector("[data-site-altitude]");
    var out = root.querySelector("[data-site-pressure]");
    if (!alt || !out) return;

    var altToM = parseFloat(root.getAttribute("data-alt-to-m") || "1");
    var pFromKpa = parseFloat(root.getAttribute("data-p-from-kpa") || "1");
    var decimals = parseInt(root.getAttribute("data-p-decimals") || "3", 10);

    function update() {
      var raw = String(alt.value || "").trim().replace(",", ".");
      var displayAlt = parseFloat(raw);
      if (!isFinite(displayAlt)) {
        out.value = "—";
        return;
      }
      var pKpa = pressureFromAltitudeM(displayAlt * altToM);
      out.value = pKpa == null ? "—" : format(pKpa * pFromKpa, decimals);
    }

    alt.addEventListener("input", update);
    alt.addEventListener("change", update);
    update();
  }

  document.querySelectorAll("[data-site-conditions]").forEach(bind);
})();
