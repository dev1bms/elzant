"""WhatsApp Cloud API webhook — subscription check (GET) + status events (POST).

Meta calls this endpoint to (a) verify the subscription and (b) push delivery
status updates (sent/delivered/read/failed). The POST path verifies Meta's
HMAC-SHA256 signature before trusting anything, updates the matching guest +
MessageLog, and always answers 200 fast so Meta does not retry. An unsigned or
forged request is rejected with 403 (it isn't from Meta, so no retry is wanted).
"""

import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import MessageLog, WeddingGuest, WhatsAppStatus
from .whatsapp import verify_webhook_signature

log = logging.getLogger("core.whatsapp")

# Cloud API status → (guest.wa_status, timestamp field to stamp)
_STATUS_MAP = {
    "sent": (WhatsAppStatus.SENT, None),
    "delivered": (WhatsAppStatus.DELIVERED, "delivered_at"),
    "read": (WhatsAppStatus.READ, "read_at"),
    "failed": (WhatsAppStatus.FAILED, None),
}

# Ordering so an out-of-order/late event never downgrades a further-along status.
_RANK = {
    WhatsAppStatus.NONE: 0, WhatsAppStatus.QUEUED: 1, WhatsAppStatus.SENT: 2,
    WhatsAppStatus.DELIVERED: 3, WhatsAppStatus.READ: 4, WhatsAppStatus.FAILED: 5,
}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        return _verify_subscription(request)

    # POST — verify the signature before trusting the body.
    if not verify_webhook_signature(request):
        return HttpResponseForbidden("invalid signature")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        _process_events(payload)
    except Exception:  # noqa: BLE001 — never 500 on Meta; that triggers retries
        log.exception("whatsapp webhook processing error")
    # Always 200 so Meta stops retrying a delivered event.
    return HttpResponse("ok")


def _verify_subscription(request):
    """GET subscription handshake: echo hub.challenge iff the verify token matches."""
    mode = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge", "")
    from .models import WhatsAppConfig
    expected = WhatsAppConfig.get().verify_token
    if mode == "subscribe" and expected and token == expected:
        return HttpResponse(challenge)
    return HttpResponseForbidden("verification failed")


def _process_events(payload):
    """Walk entry[].changes[].value.statuses[] and update guests + logs."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            for status in value.get("statuses", []):
                _apply_status(status)


def _apply_status(status):
    message_id = status.get("id")
    state = status.get("status")
    if not message_id or state not in _STATUS_MAP:
        return
    new_status, ts_field = _STATUS_MAP[state]
    when = _ts_to_datetime(status.get("timestamp"))

    guest = WeddingGuest.objects.filter(wa_message_id=message_id).first()
    if guest:
        # Don't let a late/duplicate event downgrade a further-along status.
        if _RANK.get(new_status, 0) >= _RANK.get(guest.wa_status, 0) or state == "failed":
            guest.wa_status = new_status
            fields = ["wa_status", "updated_at"]
            if ts_field and getattr(guest, ts_field) is None:
                setattr(guest, ts_field, when)
                fields.append(ts_field)
            guest.save(update_fields=fields)

    err = ""
    if state == "failed":
        errors = status.get("errors") or []
        if errors:
            err = errors[0].get("title") or errors[0].get("message") or "failed"
    MessageLog.objects.create(
        guest=guest, template_name="", wa_message_id=message_id,
        status=new_status, error=err,
    )


def _ts_to_datetime(ts):
    """Epoch-seconds string → aware datetime (UTC); falls back to None."""
    try:
        return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)
    except (TypeError, ValueError):
        from django.utils import timezone
        return timezone.now()
