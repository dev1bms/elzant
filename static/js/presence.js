// Approximate «time on site» for an invited guest: while the page is visible,
// beacon 15s heartbeats to the guest's ping endpoint (server caps per-ping and
// total). No cookies, no fingerprinting — just seconds, tied to the private
// token the guest is already using.
(function () {
  "use strict";

  var el = document.querySelector("[data-ping-url]");
  if (!el || !("sendBeacon" in navigator)) return;
  var url = el.getAttribute("data-ping-url");
  var STEP = 15; // seconds per heartbeat

  function ping(seconds) {
    try {
      navigator.sendBeacon(
        url,
        new Blob([JSON.stringify({ seconds: seconds })], { type: "application/json" })
      );
    } catch (e) { /* best-effort only */ }
  }

  var visibleSince = document.visibilityState === "visible" ? Date.now() : null;

  setInterval(function () {
    if (document.visibilityState === "visible") ping(STEP);
  }, STEP * 1000);

  // Count the tail end of a visit (page closed between heartbeats).
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      visibleSince = Date.now();
    } else if (visibleSince) {
      var tail = Math.round(((Date.now() - visibleSince) / 1000) % STEP);
      if (tail > 2) ping(tail);
      visibleSince = null;
    }
  });
})();
