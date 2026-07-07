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

# Tests (real suite in core/tests.py + panel/tests.py — WhatsApp/Twilio, RSVP, moderation)
python manage.py test
python manage.py test core.tests.RsvpPageTests.test_declined_recorded   # single test
```

`makemigrations` takes two apps: `python manage.py makemigrations core panel`.

There is no linter configured. `python manage.py check` and `check --deploy` are the sanity gates.

## Environment / config

Settings read from `.env` via `django-environ` (`elzant/settings.py`). `SECRET_KEY` is read straight from `os.environ` (not the env-parser) because `django-environ` treats a leading `$` as a variable reference. Copy `.env.example` → `.env`. Key vars: `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` (builds absolute OG/invitation URLs **and** anchors Twilio webhook signature validation — must match the public origin exactly), `SQLITE_PATH`, `MEDIA_ROOT`, `SERVE_MEDIA`, `GEOIP_ENABLED`/`GEOIP_PATH`, SMTP `EMAIL_*`. **Twilio/WhatsApp secrets are deliberately NOT in `.env`** — they live in the `WhatsAppConfig` DB singleton, edited from the admin.

Security auto-hardens when `DEBUG=False` (SSL redirect, secure cookies, proxy SSL header). HSTS is left at 0 until HTTPS is confirmed on the VPS. Deploy target is Gunicorn behind a trusted proxy/tunnel (Cloudflare) — client-IP and country detection **assume** a trusted proxy; direct public exposure lets clients spoof those headers. Full deploy guide in `deploy/DEPLOY.md`.

## Architecture

Two Django apps: **`core`** (the public site + all data models + admin) and **`panel`** (a self-service dashboard for family members who send invitations — `/panel/`, its own auth, templates, and access control; it owns no models, only views over `core`'s). Public URLs (`core/urls.py`): `home` (`/`), `thank_you` (`/tahnia/shukran/`), `invitation` (`/i/<token>/`), `rsvp` (`/i/<token>/rsvp/`, POST), `privacy`, plus two signature-verified Twilio webhooks (`/webhooks/twilio/`, `/webhooks/twilio/inbound/`). Everything else is the Django admin, which is the operator's full content-management surface.

**Data model (`core/models.py`):** every "config" model is a `pk=1` singleton with a `.get()` classmethod and admin-only editing (no redeploy to change content/secrets).
- `WeddingConfig` — event details, message templates, and RSVP button copy. Exposed to every template via the `core.context_processors.wedding` context processor as `config`.
- `WeddingGuest` — an invited guest with an unguessable `invitation_token`. `invitation_status` tracks the funnel (draft → ready → sent → opened → greeted); `wa_status` mirrors Twilio delivery; `rsvp`/`rsvp_at` hold the attendance reply. `invited_by` (a Django user) is who sent the invite — the basis for panel data isolation. `set_rsvp()` is the shared write path for both the web page and the inbound-WhatsApp webhook.
- `Greeting` — a visitor's message + optional processed photo + chosen `card_template`. **Post-moderation model:** greetings publish immediately (`status=APPROVED` on save); the admin *hides/bans* bad ones afterward. `Greeting.visible()` = everything except `REJECTED`.
- `GreetingSuggestion` — ready-made greeting texts offered as one-tap chips.
- `InviterProfile` — one-to-one with a Django user; its existence (or superuser) is what grants panel access. `can_view_all` unlocks the all-guests view.
- `WhatsAppConfig` — Twilio credentials **and** the live `enabled` flag, all in the DB (no `.env`). The Auth Token lives here; the admin masks it and restricts the screen to superusers — protect the SQLite file and its backups.
- `WhatsAppTemplate` — a Meta-approved template the sender can pick; `variables_map` orders the `{{1}},{{2}}…` slots to context keys. `MessageLog` — audit trail of every send attempt (never stores secrets).

**Moderation is post-publish, and banning must delete the photo file.** `/media/` is served by path with no auth, so `Greeting.hide()` deletes the photo + thumbnail from storage (not just flips status). The `post_delete` signal cleans up orphaned files and forces Django to not fast-delete on bulk admin delete. Don't "optimize" `hide()`/bulk actions into a single `.update()` — that would leave banned photos still served.

**Greeting submission flow (`core/views.home`):** POST → `GreetingForm` validates (honeypot `website`, length limits) → optional photo runs through `core.imaging.process_image` → greeting saved as APPROVED with client IP + best-effort country → card data stashed in `request.session["card"]` (never the pk) → redirect to `thank_you`, which pops the session card once. Guests coming from `/i/<token>/` have their token in the session so the greeting links back to the guest and flips them to `GREETED`.

**Image handling (`core/imaging.py`) is security-sensitive.** Uploads are validated (size/type), re-decoded to strip ALL metadata/EXIF/GPS, orientation-fixed, transparency-flattened, and re-encoded to a display JPEG (≤1600px) + thumbnail (≤480px) with unguessable `secrets`-based filenames. The original upload is never stored. There's a decompression-bomb guard (`Image.MAX_IMAGE_PIXELS`) checked before pixel allocation. Format allow-list is enforced on the *decoded* format, not the client-supplied extension/content-type.

**Anti-spam is deliberately not in-app throttling.** Defenses are CSRF + hidden honeypot + model/form length limits + manual moderation. Request rate-limiting is intentionally left to the edge/proxy (Cloudflare WAF) because a per-process LocMem bucket is unreliable across Gunicorn workers. Don't add in-process rate limiting — see the comment in `views.py`.

**WhatsApp sending (`core/whatsapp.py`, `core/webhooks.py`) goes through Twilio Content Templates.** `send_invitation(guest)` reads `WhatsAppConfig`, and when `enabled=False` runs in **safe mode** — it logs a simulated `MessageLog` and advances the guest's send bookkeeping without any network call or cost. Never bypass this flag. Delivery/read callbacks and inbound RSVP button taps both arrive as Twilio webhooks; both are gated by `validate_twilio_request` (HMAC over `SITE_URL + path`, *not* `build_absolute_uri`, so a Cloudflare SSL-terminating proxy doesn't break the signature). Webhooks must never return 5xx (Twilio retries) — the inbound handler swallows processing errors and always answers 200/TwiML. Phone numbers are normalized to E.164-without-`+` via `normalize_phone` (that normalized `phone_e164` is the duplicate-detection key and how inbound replies match a guest).

**Family panel (`panel/`) is view-layer access control, enforced in Python, not templates.** Every guest lookup goes through `panel/access.py` (`inviter_required`, `visible_guests`, `guest_or_403`): a non-superuser sender sees/acts on only the guests whose `invited_by` is them, so guessing another sender's guest id in a URL 403s. `can_view_all` on the profile widens the scope. Don't fetch `WeddingGuest` directly in a panel view — always through those helpers.

**Admin (`core/admin.py`) is the operator's whole toolkit:** per-guest ready-to-send WhatsApp links and email previews (built by substituting `{{ placeholders }}` via `core.utils.render_message`), a live-send action (honors safe mode), CSV exports, bulk invitation actions, and the greeting hide/show (ban/unban) actions.

**Country/IP (`core/utils.py`):** `country_from_request` prefers Cloudflare's `CF-IPCountry` header, falls back to optional GeoIP. Only the flag/name is ever shown publicly; IP is stored for moderation only and never displayed. `get_client_ip` trusts proxy headers in a specific most-trusted-first order.

## Frontend

Templates in `templates/` (`base.html` + `core/` pages and `core/partials/`). Styling is Tailwind CSS v4 configured entirely in `tailwind/input.css` via `@theme` (no `tailwind.config.js`) — that file holds the design tokens (the "Sunset on the Mediterranean" palette, self-hosted font stacks). `@source` directives there tell Tailwind to scan templates and `static/js/**`, so class names used only from JS must stay discoverable. Vanilla JS per-feature in `static/js/` (`cards.js`, `envelope.js`, `countdown.js`, `suggestions.js`, etc.) — no framework, no bundler.

`static/img/hero-bg.jpg` is the tracked source artwork; `og-image.jpg` is generated by `npm run assets:build` and gitignored — regenerate it rather than editing it, and rebuild before wide sharing (WhatsApp caches OG images hard).

**Build order before serving in production:** `npm run assets:build` → `npm run css:build` → `collectstatic`. WhiteNoise serves static files (compressed+hashed manifest storage when `DEBUG=False`); it never serves `/media/`, which has its own route in `elzant/urls.py`.

## Conventions

- Arabic-first, RTL. `LANGUAGE_CODE="ar"`, only Arabic active; i18n scaffolding (LocaleMiddleware, `locale/`) is in place to add English later but English is not wired up.
- `TIME_ZONE="Africa/Cairo"`, `USE_TZ=True` — the wedding datetime and countdown depend on Cairo time; store aware datetimes.
- Content and copy belong in `WeddingConfig`/`GreetingSuggestion` (admin-editable), not hardcoded in templates, wherever an operator might want to change them.
