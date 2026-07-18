"""Twilio WhatsApp status-callback webhook.

Twilio POSTs delivery status (queued/sent/delivered/read/failed/undelivered) as
form-encoded data. We validate Twilio's ``X-Twilio-Signature`` before trusting
anything, update the matching guest + MessageLog, and always answer 200 fast so
Twilio does not retry. An unsigned/forged request is rejected with 403.
"""

import logging
import re

from django.conf import settings
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


# --------------------------------------------------------------------------- #
# Inbound WhatsApp — quick-reply RSVP buttons (تأكيد الحضور / اعتذار)
# --------------------------------------------------------------------------- #
# Stable payload ids to set on the quick-reply buttons in Twilio's Content
# Template Builder. If the operator uses these ids, the reply is matched
# regardless of the (freely worded) button text.
_RSVP_PAYLOADS = {
    "rsvp_yes": WeddingGuest.Rsvp.ATTENDING,
    "rsvp_attend": WeddingGuest.Rsvp.ATTENDING,
    "rsvp_no": WeddingGuest.Rsvp.DECLINED,
    "rsvp_decline": WeddingGuest.Rsvp.DECLINED,
}


def _rsvp_choice_from_text(text, config):
    """Best-effort map of a tapped button's text / free reply to an RSVP choice.

    Prefers an exact match against the admin-configured labels, then falls back
    to unambiguous Arabic keywords so a slightly different reply still counts.
    """
    t = (text or "").strip()
    if not t:
        return ""
    if t == (config.rsvp_attend_label or "").strip():
        return WeddingGuest.Rsvp.ATTENDING
    if t == (config.rsvp_decline_label or "").strip():
        return WeddingGuest.Rsvp.DECLINED
    if any(k in t for k in ("سأحضر", "أحضر", "حاضر", "نعم", "بإذن الله")):
        return WeddingGuest.Rsvp.ATTENDING
    if any(k in t for k in ("أعتذر", "اعتذر", "معتذر", "لن أحضر", "لا أستطيع")):
        return WeddingGuest.Rsvp.DECLINED
    return ""


@csrf_exempt
@require_POST
def twilio_inbound_webhook(request):
    """Record an RSVP from a WhatsApp quick-reply button (or a free-text reply).

    Twilio POSTs inbound messages with ``From=whatsapp:+E164`` and, for a tapped
    quick reply, ``ButtonText`` (+ ``ButtonPayload`` for Content templates). We
    verify the signature, match the guest by phone, store the reply, and answer
    with a TwiML thank-you (allowed inside the 24-hour session an inbound message
    opens). Unknown senders / replies get an empty 200 — never a 500 (retries).
    """
    if not validate_twilio_request(request):
        return HttpResponseForbidden("invalid signature")

    reply_text = ""
    try:
        recorded = _handle_inbound_rsvp(request)
        if recorded is None:
            # Not an RSVP — keep the reply visible to the operator (the number
            # lives on the API; nobody has a WhatsApp app open to read it).
            _log_inbound_message(request)
        else:
            reply_text = recorded
    except Exception:  # noqa: BLE001 — never 500 on Twilio; that triggers retries
        log.exception("twilio inbound webhook processing error")

    return _twiml_reply(reply_text)


def _handle_inbound_rsvp(request):
    """Apply the inbound reply to the matching guest; return a thank-you string
    when an RSVP was recorded, or ``None`` when this wasn't an RSVP."""
    from .models import WeddingConfig, WhatsAppConfig
    from .whatsapp import normalize_phone

    config = WeddingConfig.get()
    if not config.rsvp_enabled:
        return None

    sender = request.POST.get("From", "") or request.POST.get("WaId", "")
    digits = re.sub(r"\D", "", sender)
    e164 = normalize_phone(digits, WhatsAppConfig.get().default_country_code)
    guest = WeddingGuest.objects.filter(phone_e164=e164).first() if e164 else None
    if not guest:
        return None

    payload = (request.POST.get("ButtonPayload", "") or "").strip().lower()
    choice = _RSVP_PAYLOADS.get(payload) or _rsvp_choice_from_text(
        request.POST.get("ButtonText") or request.POST.get("Body"), config
    )
    if not guest.set_rsvp(choice):
        return None

    MessageLog.objects.create(
        guest=guest, template_name="rsvp_inbound",
        status=WhatsAppStatus.READ, error="",
        payload={"rsvp": choice, "button": request.POST.get("ButtonText", "")},
    )
    return (config.rsvp_thanks_attending if choice == WeddingGuest.Rsvp.ATTENDING
            else config.rsvp_thanks_declined)


def _log_inbound_message(request):
    """Store a non-RSVP inbound reply (text/media) in MessageLog so the family
    sees it in the admin, and optionally email them (INBOUND_NOTIFY_EMAIL)."""
    from .models import WhatsAppConfig
    from .whatsapp import normalize_phone

    body = (request.POST.get("Body") or "").strip()
    try:
        num_media = int(request.POST.get("NumMedia") or 0)
    except ValueError:
        num_media = 0
    if not body and not num_media:
        return

    sender = request.POST.get("From", "") or request.POST.get("WaId", "")
    digits = re.sub(r"\D", "", sender)
    e164 = normalize_phone(digits, WhatsAppConfig.get().default_country_code)
    guest = WeddingGuest.objects.filter(phone_e164=e164).first() if e164 else None
    profile = (request.POST.get("ProfileName") or "").strip()

    MessageLog.objects.create(
        guest=guest,
        template_name="inbound_text",
        status=WhatsAppStatus.READ,
        wa_message_id=request.POST.get("MessageSid", ""),
        payload={
            "body": body[:2000],
            "from": e164 or digits,
            "profile": profile[:80],
            "media": num_media,
        },
    )
    _notify_inbound(guest, profile, e164 or digits, body, num_media)


def _notify_inbound(guest, profile, phone, body, num_media):
    """Best-effort email to the family about a new WhatsApp reply. Active only
    when INBOUND_NOTIFY_EMAIL is set; never raises (fail_silently)."""
    to = getattr(settings, "INBOUND_NOTIFY_EMAIL", "")
    if not to:
        return
    from django.core.mail import send_mail

    who = guest.full_name if guest else (profile or phone)
    lines = [f"من: {who} ({phone})"]
    if body:
        lines.append(f"النص: {body}")
    if num_media:
        lines.append(f"مرفقات: {num_media}")
    lines.append("التفاصيل الكاملة في «سجل الرسائل» بلوحة الأدمن.")
    send_mail(
        f"رد واتساب جديد من {who}",
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [to],
        fail_silently=True,
    )


def _twiml_reply(text):
    """A TwiML MessagingResponse (thank-you) or an empty 200 when there's nothing
    to say. Falls back to an empty 200 if the twilio SDK isn't importable."""
    if not text:
        return HttpResponse("")
    try:
        from twilio.twiml.messaging_response import MessagingResponse
    except Exception:  # noqa: BLE001 — SDK missing shouldn't break the webhook
        return HttpResponse("")
    resp = MessagingResponse()
    resp.message(text)
    return HttpResponse(str(resp), content_type="text/xml")
