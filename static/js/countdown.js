// Live countdown to a fixed instant. The target carries a timezone offset
// (derived from Cairo time) so every visitor counts down to the same moment
// regardless of their device timezone.
(function () {
  "use strict";

  var el = document.getElementById("countdown");
  if (!el) return;

  var target = new Date(el.dataset.target).getTime();
  if (isNaN(target)) return;

  var units = {
    days: el.querySelector('[data-unit="days"]'),
    hours: el.querySelector('[data-unit="hours"]'),
    minutes: el.querySelector('[data-unit="minutes"]'),
    seconds: el.querySelector('[data-unit="seconds"]'),
  };
  var doneEl = el.querySelector("[data-countdown-done]") ||
    document.querySelector("[data-countdown-done]");

  function toArabic(n) {
    return String(n).replace(/[0-9]/g, function (d) {
      return "٠١٢٣٤٥٦٧٨٩"[d];
    });
  }
  function pad(n) {
    return n < 10 ? "0" + n : "" + n;
  }
  function set(node, value) {
    if (node) node.textContent = toArabic(value);
  }

  var timer;
  function tick() {
    var diff = target - Date.now();
    if (diff <= 0) {
      set(units.days, 0);
      set(units.hours, "00");
      set(units.minutes, "00");
      set(units.seconds, "00");
      if (doneEl) doneEl.classList.remove("hidden");
      if (timer) clearInterval(timer);
      return;
    }
    var total = Math.floor(diff / 1000);
    set(units.days, Math.floor(total / 86400));
    set(units.hours, pad(Math.floor((total % 86400) / 3600)));
    set(units.minutes, pad(Math.floor((total % 3600) / 60)));
    set(units.seconds, pad(total % 60));
  }

  tick();
  timer = setInterval(tick, 1000);
})();
