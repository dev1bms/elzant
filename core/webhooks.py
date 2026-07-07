"""Twilio WhatsApp status-callback webhook.

Twilio POSTs delivery status (queued/sent/delivered/read/failed/undelivered) as
form-encoded data. We validate Twilio's ``X-Twilio-Signature`` before trusting
anything, update the matching guest + MessageLog, and always answer 200 fast so
Twilio does not retry. An unsigned/forged request is rejected with 403.
"""

import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import MessageLog, WeddingGuest, WhatsAppStatus
from .whatsapp import validate_twilio_request

log = logging.getLogger("core.whatsapp")

# Twilio MessageStatus → (guest.wa_status, timestamp field to stamp)
_STATUS_MAP = {
    "accepted": (WhatsAppStatus.QUEUED, None),
    "scheduled": (WhatsAppStatus.QUEUED, None),
    "queued": (WhatsAppStatus.QUEUED, None),
    "sending": (WhatsAppStatus.QUEUED, None),
    "sent": (WhatsAppStatus.SENT, None),
    "delivered": (WhatsAppStatus.DELIVERED, "delivered_at"),
    "read": (WhatsAppStatus.READ, "read_at"),
    "undelivered": (WhatsAppStatus.FAILED, None),
    "failed": (WhatsAppStatus.FAILED, None),
}

# Ordering so a late/out-of-order event never downgrades a further-along status.
_RANK = {
    WhatsAppStatus.NONE: 0, WhatsAppStatus.QUEUED: 1, WhatsAppStatus.SENT: 2,
    WhatsAppStatus.DELIVERED: 3, WhatsAppStatus.READ: 4, WhatsAppStatus.FAILED: 5,
}


@csrf_exempt
@require_POST
def twilio_status_webhook(request):
    # Verify Twilio's signature before trusting the body.
    if not validate_twilio_request(request):
        return HttpResponseForbidden("invalid signature")

    try:
        message_sid = request.POST.get("MessageSid") or request.POST.get("SmsSid") or ""
        state = (request.POST.get("MessageStatus") or request.POST.get("SmsStatus") or "").lower()
        error_code = request.POST.get("ErrorCode") or ""
        _apply_status(message_sid, state, error_code)
    except Exception:  # noqa: BLE001 — never 500 on Twilio; that triggers retries
        log.exception("twilio webhook processing error")

    # Twilio expects an empty 200 for status callbacks (no TwiML needed).
    return HttpResponse("")


def _apply_status(message_sid, state, error_code):
    if not message_sid or state not in _STATUS_MAP:
        return
    new_status, ts_field = _STATUS_MAP[state]

    guest = WeddingGuest.objects.filter(wa_message_id=message_sid).first()
    if guest:
        # Don't let a late/duplicate event downgrade a further-along status.
        if _RANK.get(new_status, 0) >= _RANK.get(guest.wa_status, 0) or new_status == WhatsAppStatus.FAILED:
            guest.wa_status = new_status
            fields = ["wa_status", "updated_at"]
            if ts_field and getattr(guest, ts_field) is None:
                setattr(guest, ts_field, timezone.now())
                fields.append(ts_field)
            guest.save(update_fields=fields)

    err = f"Twilio error {error_code}" if (state in ("failed", "undelivered") and error_code) else ""
    MessageLog.objects.create(
        guest=guest, template_name="", wa_message_id=message_sid,
        status=new_status, error=err,
    )
