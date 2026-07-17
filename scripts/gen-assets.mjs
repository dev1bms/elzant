// Regenerate static image assets:
//   - static/img/og-image.jpg  (1200×630) — the wedding artwork with the couple,
//     a warm bottom scrim, and the names: premium when shared on WhatsApp.
//   - static/img/hero-720.jpg / hero-1080.jpg — responsive variants of the hero
//     artwork for the <img srcset>; phones fetch ~half the bytes (LCP).
// Run with: npm run assets:build
import sharp from "sharp";

// Fallback favicon (used until the admin uploads one): a small sunset-palette
// mark so the browser never 404s on /favicon.ico.
const FAV = 64;
await sharp(
  Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${FAV}" height="${FAV}" viewBox="0 0 64 64">
    <defs>
      <linearGradient id="s" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#f4c088"/><stop offset="55%" stop-color="#d9835f"/><stop offset="100%" stop-color="#7c2b37"/>
      </linearGradient>
    </defs>
    <rect width="64" height="64" rx="14" fill="#fbf4e8"/>
    <circle cx="32" cy="32" r="21" fill="url(#s)"/>
    <circle cx="32" cy="32" r="21" fill="none" stroke="#c9a86a" stroke-width="3"/>
  </svg>`)
).png().toFile("static/img/favicon.png");
console.log("✓ static/img/favicon.png (fallback icon)");

// Responsive hero variants (the 1600px source stays the largest candidate).
for (const w of [720, 1080]) {
  const out = `static/img/hero-${w}.jpg`;
  await sharp("static/img/hero-bg.jpg")
    .resize({ width: w })
    .jpeg({ quality: 78, mozjpeg: true })
    .toFile(out);
  console.log(`✓ ${out}`);
}

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

// JPEG (not PNG): a 1200×630 photograph as lossless RGBA PNG is ~1.4 MB, over
// WhatsApp's link-preview budget; opaque JPEG q82 is ~120 KB with the same look.
await sharp(art)
  .composite([{ input: overlay }])
  .flatten({ background: "#fbf4e8" })
  .jpeg({ quality: 82, mozjpeg: true })
  .toFile("static/img/og-image.jpg");
console.log("✓ static/img/og-image.jpg (1200×630, artwork + names)");
