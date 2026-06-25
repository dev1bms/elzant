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


# Cloudflare returns these for anonymous proxies / Tor / unknown — not real countries.
_NON_COUNTRY = {"XX", "T1", "AP", "A1", "A2", "O1"}

# Minimal Arabic country names for the tooltip/admin. The flag still works without
# a name; unknown codes simply get an empty name.
COUNTRY_NAMES_AR = {
    "PS": "فلسطين", "EG": "مصر", "SA": "السعودية", "JO": "الأردن",
    "AE": "الإمارات", "KW": "الكويت", "QA": "قطر", "BH": "البحرين",
    "OM": "عُمان", "LB": "لبنان", "SY": "سوريا", "IQ": "العراق",
    "YE": "اليمن", "SD": "السودان", "LY": "ليبيا", "TN": "تونس",
    "DZ": "الجزائر", "MA": "المغرب", "MR": "موريتانيا", "SO": "الصومال",
    "DJ": "جيبوتي", "KM": "جزر القمر", "TR": "تركيا", "IR": "إيران",
    "US": "الولايات المتحدة", "CA": "كندا", "GB": "بريطانيا", "DE": "ألمانيا",
    "FR": "فرنسا", "NL": "هولندا", "SE": "السويد", "NO": "النرويج",
    "DK": "الدنمارك", "BE": "بلجيكا", "CH": "سويسرا", "AT": "النمسا",
    "ES": "إسبانيا", "IT": "إيطاليا", "AU": "أستراليا", "NZ": "نيوزيلندا",
    "MY": "ماليزيا", "ID": "إندونيسيا", "PK": "باكستان", "IN": "الهند",
}


def flag_from_code(code):
    """Regional-indicator flag emoji from a 2-letter country code, or ''."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def country_from_request(request):
    """Best-effort (country_code, arabic_name) for the visitor — never raises.

    Prefers Cloudflare's ``CF-IPCountry`` header (set by the tunnel/proxy, needs
    no database or external call); falls back to a GeoIP lookup if enabled.
    Returns ("", "") locally / when the country is unknown.
    """
    cc = (request.META.get("HTTP_CF_IPCOUNTRY") or "").strip().upper()
    if not (len(cc) == 2 and cc.isalpha() and cc not in _NON_COUNTRY):
        cc, _ = lookup_country(get_client_ip(request))
        cc = (cc or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha() or cc in _NON_COUNTRY:
        return ("", "")
    return (cc, COUNTRY_NAMES_AR.get(cc, ""))


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
