from django.conf import settings
from django.templatetags.static import static

from .models import WeddingConfig


def _og_path(config):
    """Relative path of the share (OG) image — never raises.

    Order: admin upload → generated og-image.jpg → tracked hero-bg.jpg → "".
    og-image.jpg is generated (gitignored), so under production manifest
    storage `static()` RAISES if `npm run assets:build` wasn't run before
    collectstatic — and this processor runs on EVERY request, which would
    500 the whole site. Degrade instead of dying.
    """
    if config.og_image:
        return config.og_image.url
    for candidate in ("img/og-image.jpg", "img/hero-bg.jpg"):
        try:
            return static(candidate)
        except Exception:
            continue
    return ""


def wedding(request):
    """Expose the wedding config and Open Graph helpers to every template."""
    site_url = settings.SITE_URL.rstrip("/")
    config = WeddingConfig.get()
    og_path = _og_path(config)
    return {
        "config": config,
        "site_url": site_url,
        # Bare display domain for footers/cards/og:site_name (e.g. "elzant.com").
        "site_domain": site_url.split("//")[-1].split("/")[0],
        "canonical_url": f"{site_url}{request.path}",
        "og_image": f"{site_url}{og_path}" if og_path else "",
    }
