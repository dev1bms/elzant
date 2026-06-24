// Regenerate static image assets:
//   - static/img/og-image.png  (rasterized from og-image.svg, 1200×630)
//   - static/img/qr.svg        (QR code for the site URL)
// Run with: npm run assets:build   (override domain via SITE_URL env var)
import sharp from "sharp";
import QRCode from "qrcode";

const SITE = process.env.SITE_URL || "https://elzant.com";

await sharp("static/img/og-image.svg", { density: 200 })
  .resize(1200, 630, { fit: "fill" })
  .png()
  .toFile("static/img/og-image.png");
console.log("✓ static/img/og-image.png (1200×630)");

await QRCode.toFile("static/img/qr.svg", SITE, {
  margin: 1,
  color: { dark: "#6e1f36", light: "#0000" }, // burgundy on transparent
});
console.log("✓ static/img/qr.svg →", SITE);
