// Gentle fade-up reveal on scroll. Degrades gracefully: if IntersectionObserver
// is unavailable, everything is shown immediately.
(function () {
  "use strict";

  var els = document.querySelectorAll(".reveal");
  if (!els.length) return;

  if (!("IntersectionObserver" in window)) {
    els.forEach(function (e) { e.classList.add("is-visible"); });
    return;
  }

  var io = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );

  els.forEach(function (e) { io.observe(e); });
})();

// Sticky mobile action bar: slides in once the hero is scrolled past, steps
// aside at the footer. JS-only by design — without JS the bar never shows and
// the in-page buttons still cover every action.
(function () {
  "use strict";

  var bar = document.getElementById("actionbar");
  var sentinel = document.getElementById("actionbar-sentinel");
  if (!bar || !sentinel || !("IntersectionObserver" in window)) return;

  bar.hidden = false;
  var pastHero = false;
  var nearFooter = false;
  function sync() {
    bar.classList.toggle("is-on", pastHero && !nearFooter);
  }

  new IntersectionObserver(function (entries) {
    var e = entries[0];
    pastHero = !e.isIntersecting && e.boundingClientRect.top < 0;
    sync();
  }).observe(sentinel);

  var footer = document.querySelector("body > footer");
  if (footer) {
    new IntersectionObserver(function (entries) {
      nearFooter = entries[0].isIntersecting;
      sync();
    }).observe(footer);
  }
})();
