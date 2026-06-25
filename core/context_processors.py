from django.conf import settings
from django.templatetags.static import static

from .models import WeddingConfig


def wedding(request):
    """Expose the wedding config and Open Graph helpers to every template."""
    site_url = settings.SITE_URL.rstrip("/")
    return {
        "config": WeddingConfig.get(),
        "site_url": site_url,
        "canonical_url": f"{site_url}{request.path}",
        "og_image": f"{site_url}{static('img/og-image.jpg')}",
    }
