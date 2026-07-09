from django.conf import settings
from django.templatetags.static import static

from .models import WeddingConfig


def wedding(request):
    """Expose the wedding config and Open Graph helpers to every template."""
    site_url = settings.SITE_URL.rstrip("/")
    config = WeddingConfig.get()
    # OG must be an absolute URL. Prefer the admin-uploaded image, else the
    # generated static one.
    og_path = config.og_image.url if config.og_image else static("img/og-image.jpg")
    return {
        "config": config,
        "site_url": site_url,
        "canonical_url": f"{site_url}{request.path}",
        "og_image": f"{site_url}{og_path}",
    }
