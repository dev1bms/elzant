"""
Django settings for the elzant project (elzant.com wedding site).

Configuration is read from a .env file via django-environ so that secrets and
environment-specific values never live in source control. See .env.example.
"""

import os
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# Read SECRET_KEY straight from the environment: django-environ treats values
# starting with "$" as references to other variables, which would break a random
# key that happens to start with "$". read_env() has populated os.environ above.
SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Canonical site URL — used to build absolute Open Graph URLs (og:url/og:image).
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files; must come right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware (i18n) must come after SessionMiddleware, before Common.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "elzant.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "core.context_processors.wedding",
            ],
        },
    },
]

WSGI_APPLICATION = "elzant.wsgi.application"

# ---------------------------------------------------------------------------
# Database — SQLite for the MVP (no external DB server needed).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Path is configurable so production can store the DB on a persistent,
        # backed-up volume outside the code directory (SQLITE_PATH).
        "NAME": env("SQLITE_PATH", default=str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            # WAL + a busy timeout keep SQLite reliable under a few Gunicorn
            # workers with light, concurrent writes (greetings).
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA foreign_keys=ON;"
            ),
        },
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization — Arabic (RTL) now, English structurally ready.
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "ar"
# Keep only Arabic active so the whole site stays RTL/Arabic regardless of the
# visitor's browser language. The i18n machinery (USE_I18N, LocaleMiddleware,
# LOCALE_PATHS) is in place — enabling English later is: uncomment the line,
# add translations under locale/, and wrap remaining strings in {% trans %}.
LANGUAGES = [
    ("ar", "العربية"),
    # ("en", "English"),  # enable once English translations exist
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# Timezone — critical for the countdown. Stored/derived against Cairo time.
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, images)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Use WhiteNoise's compressed+hashed storage only in production. In DEBUG keep
# the plain storage so {% static %} works without running collectstatic.
if DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Security — relaxed for local development, enforced when DEBUG is False.
# Harden further on the VPS (HSTS) once HTTPS is confirmed.
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0  # enable after HTTPS is verified on the VPS
# Trust the X-Forwarded-Proto header when behind a reverse proxy (production).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Spam control — django-ratelimit toggle (only effective if the package is
# installed and compatible). Honeypot + manual moderation remain primary.
# ---------------------------------------------------------------------------
RATELIMIT_ENABLE = env.bool("RATELIMIT_ENABLE", default=False)
