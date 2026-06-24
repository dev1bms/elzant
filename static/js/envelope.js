// Close handlers for the digital envelope. The overlay is revealed by a small
// inline script in _envelope.html; here we dismiss it and remember the choice.
(function () {
  "use strict";

  var html = document.documentElement;
  var overlay = document.getElementById("envelope");
  if (!overlay) return;

  var KEY = "elzant_envelope_opened";
  var closed = false;

  function close() {
    if (closed) return;
    closed = true;
    try {
      localStorage.setItem(KEY, "1");
    } catch (e) {}
    overlay.classList.add("is-closing");
    // After the fade, drop the scroll lock and remove the overlay from flow.
    window.setTimeout(function () {
      html.classList.remove("show-envelope");
      overlay.style.display = "none";
    }, 500);
  }

  var openBtn = document.getElementById("envelope-open");
  var skipBtn = document.getElementById("envelope-skip");
  if (openBtn) openBtn.addEventListener("click", close);
  if (skipBtn) skipBtn.addEventListener("click", close);

  // Convenience: close on Escape or when clicking the backdrop.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
  });
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) close();
  });
})();
