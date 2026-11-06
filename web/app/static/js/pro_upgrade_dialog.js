/* Open/close the shared Free→Pro upgrade dialog. No calculation data. */
(function () {
  "use strict";

  function findDialog(key) {
    if (!key) return null;
    return document.querySelector(
      'dialog[data-pro-upgrade-dialog][data-pro-prompt-key="' + key + '"]'
    );
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
      return;
    }
    dialog.setAttribute("open", "");
    dialog.removeAttribute("hidden");
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") {
      dialog.close();
      return;
    }
    dialog.removeAttribute("open");
    dialog.setAttribute("hidden", "");
  }

  document.addEventListener("click", function (event) {
    var openBtn = event.target.closest && event.target.closest("[data-pro-upgrade-open]");
    if (openBtn) {
      event.preventDefault();
      openDialog(findDialog(openBtn.getAttribute("data-pro-prompt-key")));
      return;
    }
    var dismiss = event.target.closest && event.target.closest("[data-pro-upgrade-dismiss]");
    if (dismiss) {
      event.preventDefault();
      closeDialog(dismiss.closest("dialog[data-pro-upgrade-dialog]"));
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    document.querySelectorAll("dialog[data-pro-upgrade-dialog][open]").forEach(closeDialog);
  });
})();
