// Regenerate static image assets:
//   - static/img/og-image.png  (1200×630) — the wedding artwork with the couple,
//     a warm bottom scrim, and the names: premium when shared on WhatsApp.
// Run with: npm run assets:build
import sharp from "sharp";

const W = 1200, H = 630;

// The artwork is the soul of the share card too. Cover-crop keeping the couple.
const art = await sharp("static/img/hero-bg.jpg")
  .resize(W, H, { fit: "cover", position: "top" })
  .modulate({ saturation: 1.04 })
  .toBuffer();

// Warm scrim rising from the bottom + the names, mirroring the site composition.
const overlay = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="scrim" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%"  stop-color="#fbf4e8" stop-opacity="0.97"/>
      <stop offset="34%" stop-color="#fbf4e8" stop-opacity="0.80"/>
      <stop offset="62%" stop-color="#fbf4e8" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#scrim)"/>
  <g text-anchor="middle" font-family="Georgia, serif">
    <text x="600" y="438" font-style="italic" font-size="28" letter-spacing="7" fill="#c0863f">An Invitation</text>
    <text x="600" y="528" font-family="'Geeza Pro','Markazi Text',serif" font-size="104" font-weight="700" fill="#4f1822">محمود &amp; رينان</text>
    <text x="600" y="586" font-size="34" letter-spacing="7" fill="#5a4030">22 . 07 . 2026</text>
  </g>
</svg>`);

await sharp(art).composite([{ input: overlay }]).png().toFile("static/img/og-image.png");
console.log("✓ static/img/og-image.png (1200×630, artwork + names)");
