// Regenerate static image assets:
//   - static/img/og-image.png  (rasterized from og-image.svg, 1200×630)
// Run with: npm run assets:build
import sharp from "sharp";

await sharp("static/img/og-image.svg", { density: 200 })
  .resize(1200, 630, { fit: "fill" })
  .png()
  .toFile("static/img/og-image.png");
console.log("✓ static/img/og-image.png (1200×630)");
