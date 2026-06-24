def get_client_ip(request):
    """Best-effort client IP for moderation/anti-spam.

    Honours X-Forwarded-For (first hop) when present — relevant once the site
    runs behind a reverse proxy on the VPS — otherwise REMOTE_ADDR.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
