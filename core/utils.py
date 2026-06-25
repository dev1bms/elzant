import ipaddress


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
