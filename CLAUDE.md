# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`elzant.com` — a luxury Arabic (RTL) wedding site for محمود & رينان. Django 6 + SQLite + Tailwind CSS v4. Guests open a private invitation link, write a greeting (optionally with a photo), get a shareable keepsake card, and their greeting publishes to a public moderated wall. Everything user-facing is Arabic; keep new UI strings Arabic and RTL.

## Commands

```bash
# One-time / after dependency changes
source .venv/bin/activate && pip install -r requirements.txt
npm install

# Frontend build (Tailwind + generated OG image)
npm run css:build          # tailwind/input.css -> static/css/output.css (minified)
npm run css:watch          # rebuild CSS on change during dev
npm run assets:build       # regenerate static/img/og-image.jpg from static/img/hero-bg.jpg (needs sharp)

# Django
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver          # http://127.0.0.1:8000  (admin at /admin/)
python manage.py makemigrations core

# Tests (core/tests.py is currently a stub — no real suite yet)
python manage.py test
python manage.py test core.tests.SomeTest.test_method   # single test
```

There is no linter configured. `python manage.py check` and `check --deploy` are the sanity gates.

## Environment / config

Settings read from `.env` via `django-environ` (`elzant/settings.py`). `SECRET_KEY` is read straight from `os.environ` (not the env-parser) because `django-environ` treats a leading `$` as a variable reference. Copy `.env.example` → `.env`. Key vars: `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` (used to build absolute OG/invitation URLs), `SQLITE_PATH`, `MEDIA_ROOT`, `SERVE_MEDIA`, `GEOIP_ENABLED`/`GEOIP_PATH`, SMTP `EMAIL_*`.

Security auto-hardens when `DEBUG=False` (SSL redirect, secure cookies, proxy SSL header). HSTS is left at 0 until HTTPS is confirmed on the VPS. Deploy target is Gunicorn behind a trusted proxy/tunnel (Cloudflare) — client-IP and country detection **assume** a trusted proxy; direct public exposure lets clients spoof those headers. Full deploy guide in `deploy/DEPLOY.md`.

## Architecture

Single Django app: `core`. Only four public URLs (`core/urls.py`): `home` (`/`), `thank_you` (`/tahnia/shukran/`), `invitation` (`/i/<token>/`), `privacy`. Everything else is the Django admin, which is the entire content-management surface.

**Data model (`core/models.py`):**
- `WeddingConfig` — enforced singleton (`pk=1`, `.get()` classmethod). All event details, texts, and message templates live here so they change from admin without a redeploy. Exposed to every template via the `core.context_processors.wedding` context processor as `config`.
- `WeddingGuest` — an invited guest with an unguessable `invitation_token`. `invitation_status` tracks the funnel (draft → ready → sent → opened → greeted).
- `Greeting` — a visitor's message + optional processed photo + chosen `card_template`. **Post-moderation model:** greetings publish immediately (`status=APPROVED` on save); the admin *hides/bans* bad ones afterward. `Greeting.visible()` = everything except `REJECTED`.
- `GreetingSuggestion` — ready-made greeting texts offered as one-tap chips.

**Moderation is post-publish, and banning must delete the photo file.** `/media/` is served by path with no auth, so `Greeting.hide()` deletes the photo + thumbnail from storage (not just flips status). The `post_delete` signal cleans up orphaned files and forces Django to not fast-delete on bulk admin delete. Don't "optimize" `hide()`/bulk actions into a single `.update()` — that would leave banned photos still served.

**Greeting submission flow (`core/views.home`):** POST → `GreetingForm` validates (honeypot `website`, length limits) → optional photo runs through `core.imaging.process_image` → greeting saved as APPROVED with client IP + best-effort country → card data stashed in `request.session["card"]` (never the pk) → redirect to `thank_you`, which pops the session card once. Guests coming from `/i/<token>/` have their token in the session so the greeting links back to the guest and flips them to `GREETED`.

**Image handling (`core/imaging.py`) is security-sensitive.** Uploads are validated (size/type), re-decoded to strip ALL metadata/EXIF/GPS, orientation-fixed, transparency-flattened, and re-encoded to a display JPEG (≤1600px) + thumbnail (≤480px) with unguessable `secrets`-based filenames. The original upload is never stored. There's a decompression-bomb guard (`Image.MAX_IMAGE_PIXELS`) checked before pixel allocation. Format allow-list is enforced on the *decoded* format, not the client-supplied extension/content-type.

**Anti-spam is deliberately not in-app throttling.** Defenses are CSRF + hidden honeypot + model/form length limits + manual moderation. Request rate-limiting is intentionally left to the edge/proxy (Cloudflare WAF) because a per-process LocMem bucket is unreliable across Gunicorn workers. Don't add in-process rate limiting — see the comment in `views.py`.

**Admin (`core/admin.py`) is the operator's whole toolkit:** per-guest ready-to-send WhatsApp links and email previews (built by substituting `{{ placeholders }}` via `core.utils.render_message`), CSV exports, bulk invitation actions, and the greeting hide/show (ban/unban) actions.

**Country/IP (`core/utils.py`):** `country_from_request` prefers Cloudflare's `CF-IPCountry` header, falls back to optional GeoIP. Only the flag/name is ever shown publicly; IP is stored for moderation only and never displayed. `get_client_ip` trusts proxy headers in a specific most-trusted-first order.

## Frontend

Templates in `templates/` (`base.html` + `core/` pages and `core/partials/`). Styling is Tailwind CSS v4 configured entirely in `tailwind/input.css` via `@theme` (no `tailwind.config.js`) — that file holds the design tokens (the "Sunset on the Mediterranean" palette, self-hosted font stacks). `@source` directives there tell Tailwind to scan templates and `static/js/**`, so class names used only from JS must stay discoverable. Vanilla JS per-feature in `static/js/` (`cards.js`, `envelope.js`, `countdown.js`, `suggestions.js`, etc.) — no framework, no bundler.

`static/img/hero-bg.jpg` is the tracked source artwork; `og-image.jpg` is generated by `npm run assets:build` and gitignored — regenerate it rather than editing it, and rebuild before wide sharing (WhatsApp caches OG images hard).

**Build order before serving in production:** `npm run assets:build` → `npm run css:build` → `collectstatic`. WhiteNoise serves static files (compressed+hashed manifest storage when `DEBUG=False`); it never serves `/media/`, which has its own route in `elzant/urls.py`.

## Conventions

- Arabic-first, RTL. `LANGUAGE_CODE="ar"`, only Arabic active; i18n scaffolding (LocaleMiddleware, `locale/`) is in place to add English later but English is not wired up.
- `TIME_ZONE="Africa/Cairo"`, `USE_TZ=True` — the wedding datetime and countdown depend on Cairo time; store aware datetimes.
- Content and copy belong in `WeddingConfig`/`GreetingSuggestion` (admin-editable), not hardcoded in templates, wherever an operator might want to change them.
