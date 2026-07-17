// Wall extras: "show more" batching + a small lightbox for photo greetings.
// Progressive enhancement — with JS off, every greeting is simply visible and
// photos are plain images (CSS hides .wall-hidden only under html.js).
(function () {
  "use strict";

  var BATCH = 12;

  // ---- Show more (reveals the server-rendered extras in batches) ----
  var moreWrap = document.getElementById("wall-more-wrap");
  var moreBtn = document.getElementById("wall-more");
  if (moreWrap && moreBtn) {
    moreWrap.hidden = false;
    moreBtn.addEventListener("click", function () {
      var hidden = document.querySelectorAll(".wall-extra.wall-hidden");
      for (var i = 0; i < Math.min(BATCH, hidden.length); i++) {
        hidden[i].classList.remove("wall-hidden");
      }
      if (hidden.length <= BATCH) moreWrap.hidden = true;
    });
  }

  // ---- Lightbox ----
  var box = document.getElementById("lightbox");
  if (!box) return;
  var img = document.getElementById("lightbox-img");
  var cap = document.getElementById("lightbox-cap");
  var closeBtn = box.querySelector("[data-lb-close]");
  var prevBtn = box.querySelector("[data-lb-prev]");
  var nextBtn = box.querySelector("[data-lb-next]");
  var frames = Array.prototype.slice.call(document.querySelectorAll(".msg-frame[data-full]"));
  if (!frames.length) return;

  var index = -1;
  var lastFocus = null;

  function show(i) {
    index = (i + frames.length) % frames.length;
    var f = frames[index];
    img.src = f.getAttribute("data-full");
    cap.textContent = f.getAttribute("data-name") || "";
    var single = frames.length < 2;
    prevBtn.hidden = single;
    nextBtn.hidden = single;
  }
  function open(i) {
    lastFocus = document.activeElement;
    show(i);
    box.hidden = false;
    document.documentElement.style.overflow = "hidden";
    closeBtn.focus();
  }
  function close() {
    box.hidden = true;
    img.src = "";
    document.documentElement.style.overflow = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  frames.forEach(function (f, i) {
    f.addEventListener("click", function () { open(i); });
  });
  closeBtn.addEventListener("click", close);
  prevBtn.addEventListener("click", function () { show(index - 1); });
  nextBtn.addEventListener("click", function () { show(index + 1); });
  box.addEventListener("click", function (e) {
    if (e.target === box) close();  // tap outside the photo
  });

  document.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "Escape") close();
    // RTL: the "previous" arrow points right, so ArrowRight = previous.
    else if (e.key === "ArrowRight") show(index - 1);
    else if (e.key === "ArrowLeft") show(index + 1);
    else if (e.key === "Tab") {
      // Tiny focus trap across the three controls.
      var f = [closeBtn, prevBtn, nextBtn].filter(function (b) { return !b.hidden; });
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // Swipe between photos (horizontal), swipe down to dismiss.
  var touchX = null, touchY = null;
  box.addEventListener("touchstart", function (e) {
    if (e.touches.length !== 1) return;
    touchX = e.touches[0].clientX;
    touchY = e.touches[0].clientY;
  }, { passive: true });
  box.addEventListener("touchend", function (e) {
    if (touchX === null) return;
    var dx = e.changedTouches[0].clientX - touchX;
    var dy = e.changedTouches[0].clientY - touchY;
    touchX = touchY = null;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) {
      // RTL: swiping right pulls the previous photo back into view.
      show(dx > 0 ? index - 1 : index + 1);
    } else if (dy > 72 && Math.abs(dy) > Math.abs(dx)) {
      close();
    }
  }, { passive: true });
})();
