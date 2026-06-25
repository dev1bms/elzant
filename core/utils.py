import ipaddress
import re

_PLACEHOLDER_RE = re.compile(r"{{\s*(\w+)\s*}}")


def render_message(template, mapping):
    """Substitute {{ key }} placeholders in an admin-edited template string.

    Unknown placeholders are left as-is. No code execution — plain text only.
    """
    if not template:
        return ""
    return _PLACEHOLDER_RE.sub(
        lambda m: str(mapping.get(m.group(1), m.group(0))), template
    )


def lookup_country(ip):
    """Best-effort (country_code, country_name); disabled by default, never raises.

    Enable with GEOIP_ENABLED=True + a local MaxMind GeoLite2-Country.mmdb
    (GEOIP_PATH) and ``pip install geoip2`` — no external API call per request.
    Results are cached per IP for 24h. Returns (None, None) when unavailable.
    """
    from django.conf import settings
    from django.core.cache import cache

    if not ip or not getattr(settings, "GEOIP_ENABLED", False):
        return (None, None)

    cache_key = f"geoip:{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = (None, None)
    try:  # all optional — any failure leaves the country blank
        from django.contrib.gis.geoip2 import GeoIP2

        info = GeoIP2().country(ip)
        result = (info.get("country_code") or "", info.get("country_name") or "")
    except Exception:
        result = (None, None)

    cache.set(cache_key, result, 60 * 60 * 24)
    return result


def _valid_ip(value):
    """Return the value if it is a syntactically valid IP, else None."""
    if not value:
        return None
    value = value.strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    return value


def get_client_ip(request):
    """Best-effort client IP for moderation / anti-spam (never shown publicly).

    Only meaningful when Gunicorn sits behind a *trusted* proxy/tunnel
    (e.g. Cloudflare Tunnel, Caddy). Preference order, most-trusted first:

      1. CF-Connecting-IP  — set by Cloudflare
      2. X-Real-IP         — set by most reverse proxies
      3. last hop of X-Forwarded-For — the address the closest proxy appended
         (NOT the first, which is client-supplied and trivially spoofable)
      4. REMOTE_ADDR

    Each candidate is validated; invalid values are skipped. If Gunicorn is
    exposed directly to the public (no trusted proxy), these headers can be
    forged — so direct public exposure should be avoided. See DEPLOY.md.
    """
    meta = request.META

    cf = _valid_ip(meta.get("HTTP_CF_CONNECTING_IP"))
    if cf:
        return cf

    real = _valid_ip(meta.get("HTTP_X_REAL_IP"))
    if real:
        return real

    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        last_hop = _valid_ip(forwarded.split(",")[-1])
        if last_hop:
            return last_hop

    return _valid_ip(meta.get("REMOTE_ADDR"))
