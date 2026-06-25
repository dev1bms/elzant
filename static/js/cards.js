// Photo greeting cards — live-preview modal.
// The visitor picks a local photo (never uploaded until the form is sent),
// sees it rendered inside every frame using the SAME .wed-card markup/CSS as
// the final shareable card, chooses one, and confirms. Keeps the form compact.
(function () {
  "use strict";

  var picker = document.getElementById("id_photo");          // real <input type=file>, hidden
  var tplInput = document.getElementById("id_card_template"); // hidden template value
  if (!picker || !tplInput) return;

  var modal = document.getElementById("card-modal");
  var openBtn = document.getElementById("photo-open");
  var summary = document.getElementById("photo-summary");
  var summaryImg = document.getElementById("photo-summary-img");
  var summaryTpl = document.getElementById("photo-summary-tpl");
  var editBtn = document.getElementById("photo-edit");
  var removeBtn = document.getElementById("photo-remove");
  var strip = document.getElementById("frame-strip");
  var bigCard = document.getElementById("preview-card");
  var doneBtn = document.getElementById("modal-done");
  var repickBtn = document.getElementById("modal-repick");
  var nameInput = document.getElementById("id_name");
  var msgInput = document.getElementById("id_message");

  var LABELS = {
    photo_frame: "إطار أنيق", photo_story: "ستوري", family_warm: "عائلي دافئ",
    palestinian_soft: "لمسة فلسطينية", cairo_evening: "غروب القاهرة", no_photo_minimal: "بدون صورة",
  };
  var DEFAULT_TPL = "photo_frame";
  var objectUrl = null;
  var lastFocus = null;

  // ---- preview geometry (mirrors card.js: 1080×1350 scaled, origin top-left) ----
  function fitStage(stage) {
    var card = stage.querySelector(".wed-card");
    if (!card) return;
    var s = stage.clientWidth / 1080;
    card.style.transform = "scale(" + s + ")";
    stage.style.height = 1350 * s + "px";
  }
  function fitAll() {
    (modal || document).querySelectorAll(".prev-stage").forEach(fitStage);
  }
  // mirror card.js length-based message sizing so the preview matches the export
  function sizeMessage(el, text) {
    var len = (text || "").trim().length;
    var fs = 46;
    if (len > 120) fs = 40;
    if (len > 240) fs = 34;
    if (len > 360) fs = 28;
    el.style.fontSize = fs + "px";
  }
  function syncContent() {
    var msg = (msgInput && msgInput.value.trim()) || "رسالتك ستظهر هنا";
    var who = (nameInput && nameInput.value.trim()) || "اسمك";
    document.querySelectorAll(".prev-msg").forEach(function (el) {
      el.textContent = msg;
      sizeMessage(el, msg);
    });
    document.querySelectorAll(".prev-from").forEach(function (el) {
      el.textContent = "— " + who;
    });
  }
  function setPreviewSrc(url) {
    document.querySelectorAll(".prev-img").forEach(function (img) { img.src = url; });
  }

  // ---- template selection ----
  function selectTemplate(tpl) {
    tplInput.value = tpl;
    if (bigCard) {
      bigCard.className = "wed-card wed-card--" + tpl;
      bigCard.setAttribute("data-template", tpl);
    }
    if (strip) {
      strip.querySelectorAll(".frame-opt").forEach(function (opt) {
        var on = opt.getAttribute("data-template") === tpl;
        opt.classList.toggle("is-active", on);
        opt.setAttribute("aria-selected", on ? "true" : "false");
      });
    }
    var lg = modal && modal.querySelector(".prev-stage--lg");
    if (lg) fitStage(lg);
  }

  // ---- modal open/close ----
  function openModal() {
    if (!modal) return;
    syncContent();
    modal.classList.remove("hidden");
    modal.removeAttribute("hidden");
    document.documentElement.style.overflow = "hidden";
    lastFocus = document.activeElement;
    requestAnimationFrame(fitAll);
    if (doneBtn) doneBtn.focus();
  }
  function commitSummary() {
    if (!(picker.files && picker.files.length)) return;
    if (summaryImg && objectUrl) summaryImg.src = objectUrl;
    if (summaryTpl) summaryTpl.textContent = LABELS[tplInput.value] || LABELS[DEFAULT_TPL];
    if (summary) { summary.classList.remove("hidden"); summary.classList.add("flex"); }
    if (openBtn) openBtn.classList.add("hidden");
  }
  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("hidden", "");
    document.documentElement.style.overflow = "";
    commitSummary();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // ---- file handling ----
  function onFile() {
    var f = picker.files && picker.files[0];
    if (!f) return;
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    objectUrl = URL.createObjectURL(f);
    setPreviewSrc(objectUrl);
    var keep = LABELS[tplInput.value] && tplInput.value !== "no_photo_minimal";
    selectTemplate(keep ? tplInput.value : DEFAULT_TPL);
    openModal();
  }

  if (openBtn) openBtn.addEventListener("click", function () { picker.click(); });
  if (editBtn) editBtn.addEventListener("click", function () {
    if (objectUrl) { syncContent(); openModal(); } else { picker.click(); }
  });
  if (repickBtn) repickBtn.addEventListener("click", function () { picker.click(); });
  picker.addEventListener("change", onFile);

  if (strip) strip.addEventListener("click", function (e) {
    var opt = e.target.closest && e.target.closest(".frame-opt");
    if (opt) selectTemplate(opt.getAttribute("data-template"));
  });

  if (doneBtn) doneBtn.addEventListener("click", closeModal);

  if (removeBtn) removeBtn.addEventListener("click", function () {
    picker.value = "";
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    selectTemplate("no_photo_minimal");
    if (summary) { summary.classList.add("hidden"); summary.classList.remove("flex"); }
    if (openBtn) openBtn.classList.remove("hidden");
  });

  // ---- close + a11y ----
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target.hasAttribute("data-close")) closeModal();
    });
    // simple focus trap
    modal.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var f = Array.prototype.filter.call(
        modal.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])'),
        function (el) { return el.offsetParent !== null; }
      );
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal && !modal.classList.contains("hidden")) closeModal();
  });
  window.addEventListener("resize", function () {
    if (modal && !modal.classList.contains("hidden")) fitAll();
  });
  if (msgInput) msgInput.addEventListener("input", function () { if (objectUrl) syncContent(); });
})();
