// Close handlers for the digital envelope. The overlay is revealed by a small
// inline script in _envelope.html; here we dismiss it and remember the choice.
(function () {
  "use strict";

  var html = document.documentElement;
  var overlay = document.getElementById("envelope");
  if (!overlay) return;

  // Per-page remember key (the private invitation page uses a per-guest key so
  // its personalized intro shows even after the public page was visited).
  var KEY = overlay.getAttribute("data-key") || "elzant_envelope_opened";
  var closed = false;

  function onKeydown(e) {
    if (e.key === "Escape") close();
  }

  function close() {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKeydown); // no lingering listener
    try {
      localStorage.setItem(KEY, "1");
    } catch (e) {}
    overlay.classList.add("is-closing");
    // After the fade (CSS transition is 0.7s), drop the scroll lock and remove
    // the overlay from flow, handing focus to the page's heading.
    window.setTimeout(function () {
      html.classList.remove("show-envelope");
      overlay.style.display = "none";
      // The overlay's own (now hidden) h1 comes first in the DOM — target the
      // page content's heading specifically.
      var h1 = document.querySelector("main h1");
      if (h1) {
        h1.setAttribute("tabindex", "-1");
        h1.focus({ preventScroll: true });
      }
    }, 700);
  }

  var openBtn = document.getElementById("envelope-open");
  var skipBtn = document.getElementById("envelope-skip");
  if (openBtn) openBtn.addEventListener("click", close);
  if (skipBtn) skipBtn.addEventListener("click", close);

  // Dialog a11y: move focus into the overlay when shown, and keep Tab cycling
  // between its two controls while it is open.
  if (html.classList.contains("show-envelope") && openBtn) {
    openBtn.focus({ preventScroll: true });
    overlay.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || closed || !skipBtn) return;
      e.preventDefault();
      (document.activeElement === openBtn ? skipBtn : openBtn).focus();
    });
  }

  // Convenience: close on Escape or when clicking the backdrop.
  document.addEventListener("keydown", onKeydown);
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) close();
  });
})();
