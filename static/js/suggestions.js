// Ready-made greeting chips: tapping one fills the message box (editable after).
(function () {
  "use strict";
  var msg = document.getElementById("id_message");
  var chips = document.querySelectorAll(".suggestion-chip");
  if (!msg || !chips.length) return;
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var text = chip.getAttribute("data-text");
      if (text) {
        msg.value = text;
        msg.focus();
      }
    });
  });
})();
