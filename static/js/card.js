// Render the HTML congratulations card to a PNG in the browser and let the
// visitor download or share it. modern-screenshot handles Arabic/RTL fonts far
// better than html2canvas; we await document.fonts.ready before capturing.
import { domToPng } from "./vendor/modern-screenshot.mjs";

const card = document.getElementById("card");
const stage = document.getElementById("card-stage");
if (card && stage) {
  // Shrink the message a little for long greetings so they fit the card.
  const msg = card.querySelector(".wed-card__message");
  if (msg) {
    const len = msg.textContent.trim().length;
    let fs = 46;
    if (len > 120) fs = 40;
    if (len > 240) fs = 34;
    if (len > 360) fs = 28;
    msg.style.fontSize = fs + "px";
  }

  // Scale the fixed 1080×1350 card down to fit the viewport.
  function fit() {
    const scale = Math.min(1, stage.clientWidth / 1080);
    card.style.transform = "scale(" + scale + ")";
    stage.style.height = 1350 * scale + "px";
  }
  fit();
  window.addEventListener("resize", fit);

  async function renderDataUrl() {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
    return domToPng(card, {
      width: 1080,
      height: 1350,
      scale: 2, // crisp export (2160×2700)
      backgroundColor: "#fdfbf7",
      style: { transform: "none", margin: "0" },
    });
  }

  function withBusy(btn, fn) {
    return async function (e) {
      const target = e.currentTarget;
      const label = target.textContent;
      target.disabled = true;
      target.textContent = "جارٍ التجهيز…";
      try {
        await fn();
      } catch (err) {
        if (!err || err.name !== "AbortError") {
          console.error(err);
          alert("تعذّر إنشاء صورة البطاقة، يرجى المحاولة مرة أخرى.");
        }
      } finally {
        target.disabled = false;
        target.textContent = label;
      }
    };
  }

  const downloadBtn = document.getElementById("card-download");
  if (downloadBtn) {
    downloadBtn.addEventListener(
      "click",
      withBusy(downloadBtn, async function () {
        const dataUrl = await renderDataUrl();
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = "tahnia-elzant.png";
        document.body.appendChild(a);
        a.click();
        a.remove();
      })
    );
  }

  const shareBtn = document.getElementById("card-share");
  if (shareBtn) {
    shareBtn.addEventListener(
      "click",
      withBusy(shareBtn, async function () {
        const dataUrl = await renderDataUrl();
        const blob = await (await fetch(dataUrl)).blob();
        const file = new File([blob], "tahnia-elzant.png", { type: "image/png" });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share({ files: [file], title: "تهنئة", text: "شاركت تهنئتي للعروسين 🤍" });
        } else {
          // wa.me can't attach an image — share the site link as text instead.
          window.open(
            "https://wa.me/?text=" +
              encodeURIComponent("شاركت تهنئتي للعروسين 🤍 " + location.origin),
            "_blank"
          );
        }
      })
    );
  }
}
