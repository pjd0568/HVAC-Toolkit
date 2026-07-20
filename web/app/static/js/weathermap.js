// Site Data - Weather & Design Conditions: Leaflet map + Open-Meteo geocoding
// search. Both interactions resolve to setting the hidden lat/lon/elevation/
// place fields on #weather-form and submitting it -- a normal GET, same as
// every other tool's auto-submitting selects (see SPEC-weather-climate-data.md).
// `WEATHER_MAP` (lat, lon, hasLocation, searchUrl, elevationUrl) is set inline
// by weather.html before this script loads.
(function () {
  "use strict";

  const form = document.getElementById("weather-form");
  const dayForm = document.getElementById("day-form");
  const fieldLat = document.getElementById("field-lat");
  const fieldLon = document.getElementById("field-lon");
  const fieldElevation = document.getElementById("field-elevation");
  const fieldPlace = document.getElementById("field-place");
  const searchInput = document.getElementById("location-search");
  const resultsBox = document.getElementById("location-results");
  const statusBox = document.getElementById("map-status");
  const loadingOverlay = document.getElementById("weather-loading");

  // Selecting a location (or picking an On This Day date) triggers a full
  // page reload while the server fetches history -- a few seconds for the
  // multi-year percentile calc, near-instant for a single day, but the
  // overlay covers both the same way for a consistent feel.
  // Note: form.submit() called from JS does NOT fire the form's "submit"
  // event (a real DOM quirk), so this has to be called explicitly at every
  // submit site below rather than attached once as a listener. Never
  // explicitly hidden -- the whole page gets replaced once the new page
  // (with results) arrives, taking the overlay with it.
  function submitFormWithOverlay(formEl) {
    loadingOverlay.classList.add("open");
    formEl.submit();
  }
  function submitWeatherForm() {
    submitFormWithOverlay(form);
  }
  window.submitWeatherForm = submitWeatherForm; // used by the Years-of-record <select>'s onchange
  window.submitDayForm = function () {
    // Deliberately a separate form/submit path from #weather-form: picking a
    // date never re-triggers (or depends on) the multi-year percentile fetch
    // above it -- see fetch_hourly_for_date's docstring in weather_client.py.
    if (dayForm) submitFormWithOverlay(dayForm);
  };

  // Design Conditions: one shared "tier" (0.4%/1%/2%) drives both the
  // Summer and Winter blocks together -- every .pct-block (in either column)
  // carries a data-tier attribute (Winter's maps its own heating label back
  // to the matching cooling tier, e.g. 99.6% -> "0.4"), so a single radio
  // selection shows/hides across both columns at once. Blocks are all
  // pre-rendered server-side (correct units/formatting already baked in);
  // this is pure show/hide, no client-side recompute or reformatting.
  window.setPctTier = function (radio) {
    const tier = radio.value;
    document.querySelectorAll(".pct-block").forEach(function (block) {
      block.style.display = block.dataset.tier === tier ? "" : "none";
    });
  };
  const checkedTier = document.querySelector('input[name="pct-tier"]:checked');
  if (checkedTier) {
    // Defensive -- the template's inline display:none already matches the
    // checked radio, but this keeps the two in sync if that ever drifts.
    window.setPctTier(checkedTier);
  }

  // Return Period Extremes: a single radio group picks the return period n
  // (5/10/20/50); each .rp-block carries a data-period, so this is pure
  // show/hide of pre-rendered blocks -- same approach as setPctTier, no
  // client-side recompute or reformatting.
  window.setReturnPeriod = function (radio) {
    const period = radio.value;
    document.querySelectorAll(".rp-block").forEach(function (block) {
      block.style.display = block.dataset.period === period ? "" : "none";
    });
  };
  const checkedPeriod = document.querySelector('input[name="return-period"]:checked');
  if (checkedPeriod) {
    window.setReturnPeriod(checkedPeriod);
  }

  const startZoom = WEATHER_MAP.hasLocation ? 9 : 5;
  const map = L.map("weather-map").setView([WEATHER_MAP.lat, WEATHER_MAP.lon], startZoom);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  let marker = null;
  function setMarker(lat, lon) {
    if (marker) {
      marker.setLatLng([lat, lon]);
    } else {
      marker = L.marker([lat, lon]).addTo(map);
    }
  }
  if (WEATHER_MAP.hasLocation) {
    setMarker(WEATHER_MAP.lat, WEATHER_MAP.lon);
  }

  function selectLocation(lat, lon, elevationM, place) {
    fieldLat.value = lat;
    fieldLon.value = lon;
    fieldElevation.value = elevationM;
    fieldPlace.value = place || "";
    submitWeatherForm();
  }

  // -- Map click: no geocoder result to take a name/elevation from, so look up
  // elevation separately before submitting (see app/weather_client.fetch_elevation).
  map.on("click", function (e) {
    const lat = e.latlng.lat;
    const lon = e.latlng.lng;
    setMarker(lat, lon);
    statusBox.textContent = "Looking up site elevation…";
    fetch(`${WEATHER_MAP.elevationUrl}?lat=${lat}&lon=${lon}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          statusBox.textContent = "Could not look up elevation for this point: " + data.error;
          return;
        }
        selectLocation(lat, lon, data.elevation_m, "");
      })
      .catch(() => {
        statusBox.textContent = "Could not reach the elevation lookup service.";
      });
  });

  // -- Search box: debounced typeahead against /weather/search.
  let debounceTimer = null;
  let activeResults = [];
  let activeIndex = -1; // keyboard-highlighted row, -1 = none

  function closeDropdown() {
    resultsBox.classList.remove("open");
    resultsBox.innerHTML = "";
    activeResults = [];
    activeIndex = -1;
  }

  function pickResult(r) {
    searchInput.value = r.label;
    closeDropdown();
    map.setView([r.lat, r.lon], 10);
    setMarker(r.lat, r.lon);
    selectLocation(r.lat, r.lon, r.elevation_m, r.label);
  }

  function highlight(index) {
    const options = resultsBox.querySelectorAll(".location-option");
    options.forEach((el) => el.classList.remove("active"));
    if (index >= 0 && index < options.length) {
      options[index].classList.add("active");
      options[index].scrollIntoView({ block: "nearest" });
    }
    activeIndex = index;
  }

  function renderResults(results) {
    activeResults = results;
    activeIndex = -1;
    if (results.length === 0) {
      resultsBox.innerHTML = '<div class="location-empty">No matches</div>';
    } else {
      // Same name can exist in more than one country (e.g. Leeds, England vs
      // Leeds, Alabama) -- r.label already carries region + country, but a
      // header makes it unmistakable that a choice is needed when there's
      // more than one hit, rather than the list looking like a stray extra.
      const header = results.length > 1
        ? `<div class="location-hint">${results.length} matches — select one</div>`
        : "";
      resultsBox.innerHTML = header + results
        .map((r, i) => `<div class="location-option" data-index="${i}">${r.label}</div>`)
        .join("");
    }
    resultsBox.classList.add("open");
  }

  function showPending() {
    resultsBox.innerHTML = '<div class="location-empty">Searching…</div>';
    resultsBox.classList.add("open");
  }

  function runSearch(q) {
    fetch(`${WEATHER_MAP.searchUrl}?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          resultsBox.innerHTML = `<div class="location-empty">${data.error}</div>`;
          resultsBox.classList.add("open");
          return;
        }
        renderResults(data);
      })
      .catch(() => {
        resultsBox.innerHTML = '<div class="location-empty">Search unavailable right now</div>';
        resultsBox.classList.add("open");
      });
  }

  // Cancel any pending debounced search and clear whatever's currently shown
  // -- called at the start of every new search attempt so a fast typist (or
  // an Enter/click that lands mid-debounce) can never act on a *previous*
  // query's results. This was the root cause of "overwriting the search does
  // nothing" (or worse, silently reselects the old location): the old
  // results/activeIndex stayed live in memory until the new fetch resolved,
  // so an Enter pressed in that window acted on stale data instead of the
  // text actually in the box.
  function resetSearchState() {
    clearTimeout(debounceTimer);
    activeResults = [];
    activeIndex = -1;
  }

  resultsBox.addEventListener("click", function (e) {
    const el = e.target.closest(".location-option");
    if (!el) return;
    const r = activeResults[Number(el.dataset.index)];
    if (r) pickResult(r);
  });

  searchInput.addEventListener("input", function () {
    const q = searchInput.value.trim();
    resetSearchState();
    if (q.length < 2) {
      closeDropdown();
      return;
    }
    showPending();
    debounceTimer = setTimeout(function () { runSearch(q); }, 300);
  });

  // Clicking into the box to search again previously left the last-picked
  // location's full label sitting there, needing a manual select-all-and-
  // delete before typing a new query. Auto-clear on focus removes that step
  // -- this field always reads as "type here", never "edit the current text".
  searchInput.addEventListener("focus", function () {
    if (searchInput.value) {
      searchInput.value = "";
      resetSearchState();
      closeDropdown();
    }
  });

  document.addEventListener("click", function (e) {
    if (e.target !== searchInput && !resultsBox.contains(e.target)) {
      closeDropdown();
    }
  });

  // The search box lives inside #weather-form, so Enter would otherwise
  // submit that form immediately with the hidden lat/lon fields still blank
  // (wiping out whatever was just typed). Enter here always means "resolve
  // the typed search", never "submit the page" -- arrow keys move the
  // highlight, Enter picks the highlighted row (or the only match), and if
  // nothing is settled yet it runs the search immediately rather than doing
  // nothing.
  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeDropdown();
      return;
    }
    if (e.key === "ArrowDown" && activeResults.length) {
      e.preventDefault();
      highlight((activeIndex + 1) % activeResults.length);
      return;
    }
    if (e.key === "ArrowUp" && activeResults.length) {
      e.preventDefault();
      highlight((activeIndex - 1 + activeResults.length) % activeResults.length);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && activeResults[activeIndex]) {
        pickResult(activeResults[activeIndex]);
      } else if (activeResults.length === 1) {
        pickResult(activeResults[0]);
      } else {
        const q = searchInput.value.trim();
        resetSearchState();
        if (q.length >= 2) {
          showPending();
          runSearch(q);
        }
      }
    }
  });
})();
