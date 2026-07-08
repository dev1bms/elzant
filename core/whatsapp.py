"""WhatsApp notifications via Twilio.

Sends WhatsApp "Content Template" messages through Twilio and validates Twilio's
status-callback signature. Credentials live in the admin (WhatsAppConfig) — the
Auth Token is masked + superuser-only, never in .env, never logged, never
returned to clients.

``send_invitation`` honours ``WhatsAppConfig.enabled``: when off (safe mode) it
logs a simulated "would send" and performs NO network call — zero cost. The
``twilio`` package is imported lazily inside the send/validate helpers so importing
this module (and running unrelated tests) never requires the dependency.
"""

import json
import re
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


class WhatsAppError(Exception):
    """A send failed. Message is safe to store in MessageLog / show to admin."""


@dataclass
class SendResult:
    ok: bool
    message_id: str = ""
    simulated: bool = False   # True in safe-mode (enabled=False) — no real send
    error: str = ""


# --------------------------------------------------------------------------- #
# Phone helpers
# --------------------------------------------------------------------------- #
def normalize_phone(raw, default_cc="20"):
    """Return an E.164 number (digits only, no ``+``) or ``None`` if invalid.

    Handles spaces/dashes/parentheses, a leading ``+`` or ``00`` international
    prefix, and a local trunk ``0`` (which is replaced by ``default_cc``). A bare
    local number without a trunk zero gets ``default_cc`` prepended unless it
    already starts with it. ``default_cc`` is the country's calling code digits
    (Egypt=20). Returns None for anything that isn't 8–15 digits.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    default_cc = re.sub(r"\D", "", str(default_cc or ""))

    if s.startswith("+"):
        digits = re.sub(r"\D", "", s)                      # + dropped → international
    else:
        digits = re.sub(r"\D", "", s)
        if digits.startswith("00"):
            digits = digits[2:]                            # 00 = international prefix
        elif digits.startswith("0"):
            digits = default_cc + digits.lstrip("0")       # local trunk zero
        elif default_cc and not digits.startswith(default_cc):
            digits = default_cc + digits                   # bare local, no trunk zero

    if not digits or not (8 <= len(digits) <= 15):
        return None
    return digits


def to_whatsapp_address(e164):
    """Twilio WhatsApp address: ``whatsapp:+<digits>`` (or "" for empty input)."""
    digits = re.sub(r"\D", "", str(e164 or ""))
    return f"whatsapp:+{digits}" if digits else ""


def _site_base():
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def status_callback_url():
    """Absolute URL Twilio posts delivery/read status to (must match SITE_URL)."""
    base = _site_base()
    return base + reverse("twilio_status") if base else ""


def invitation_url(guest):
    base = _site_base()
    return base + reverse("invitation", args=[guest.invitation_token]) if base else ""


def build_invitation_variables(guest):
    """Content variables for the invitation template:
    ``{{1}}`` = guest name, ``{{2}}`` = venue/map link, ``{{3}}`` = the guest's
    personal invitation link.

    WhatsApp/Twilio REJECT an approved Content Template when any variable
    resolves to an empty string (errors 21656 / 92007 / 63013), which would fail
    every live send. So each slot falls back to a non-empty value: the venue
    slot degrades map → address → hall name → the invitation link, and the link
    itself degrades to the site origin.
    """
    from .models import WeddingConfig

    config = WeddingConfig.get()
    link = invitation_url(guest) or _site_base() or "elzant.com"
    location = config.map_url or config.venue_address or config.venue_name or link
    return {
        "1": guest.full_name or "ضيفنا الكريم",
        "2": location,
        "3": link,
        "4": guest.invitation_token,  # RSVP button URLs: i/confirm/{{4}}, i/decline/{{4}}
    }


# --------------------------------------------------------------------------- #
# Low-level Twilio send
# --------------------------------------------------------------------------- #
def _twilio_client(config):
    from twilio.rest import Client  # lazy import — only needed for a real send

    if not (config.twilio_account_sid and config.twilio_auth_token):
        raise WhatsAppError("إعدادات Twilio ناقصة (Account SID أو Auth Token).")
    return Client(config.twilio_account_sid, config.twilio_auth_token)


def send_content_message(to_e164, content_sid, variables, *, config):
    """Send a Twilio WhatsApp Content Template message. Returns the message SID.

    Raises WhatsAppError with a friendly, secret-free message on any failure.
    """
    from twilio.base.exceptions import TwilioRestException

    if not content_sid:
        raise WhatsAppError("لا يوجد Content Template SID مُعرَّف في الإعدادات.")
    to = to_whatsapp_address(to_e164)
    if not to:
        raise WhatsAppError("رقم المُستقبِل غير صالح.")

    kwargs = {
        "to": to,
        "content_sid": content_sid,
        "content_variables": json.dumps(variables or {}),
    }
    if config.messaging_service_sid:
        kwargs["messaging_service_sid"] = config.messaging_service_sid
    elif config.twilio_from:
        kwargs["from_"] = to_whatsapp_address(config.twilio_from)
    else:
        raise WhatsAppError("لا يوجد مُرسِل (رقم واتساب أو Messaging Service) في الإعدادات.")

    callback = status_callback_url()
    if callback:
        kwargs["status_callback"] = callback

    client = _twilio_client(config)
    try:
        message = client.messages.create(**kwargs)
    except TwilioRestException as exc:
        raise WhatsAppError(f"خطأ من Twilio ({exc.code}): {exc.msg}") from exc
    except Exception as exc:  # noqa: BLE001 — network/other, keep it friendly
        raise WhatsAppError(f"تعذّر الاتصال بـ Twilio: {exc}") from exc

    if not getattr(message, "sid", ""):
        raise WhatsAppError("لم تُعد Twilio معرّف رسالة.")
    return message.sid


# --------------------------------------------------------------------------- #
# Status webhook signature validation
# --------------------------------------------------------------------------- #
def validate_twilio_request(request):
    """True iff X-Twilio-Signature matches (RequestValidator over the configured
    callback URL + POST params). Uses SITE_URL + path — not build_absolute_uri —
    so an SSL-terminating proxy (Cloudflare) doesn't break validation.
    """
    from .models import WhatsAppConfig

    token = WhatsAppConfig.get().twilio_auth_token
    if not token:
        return False
    from twilio.request_validator import RequestValidator

    signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    base = _site_base()
    url = (base + request.path) if base else request.build_absolute_uri()
    params = request.POST.dict()
    try:
        return RequestValidator(token).validate(url, params, signature)
    except Exception:  # noqa: BLE001 — never let validation raise
        return False


# --------------------------------------------------------------------------- #
# Orchestration — honour safe mode, log, update the guest
# --------------------------------------------------------------------------- #
def send_invitation(guest, *, sender=None, force=False):
    """Send (or safe-mode simulate) the invitation Content Template to a guest.

    Reads WhatsAppConfig for the content SID / sender / enabled flag, writes a
    MessageLog, and updates the guest's WhatsApp tracking fields. Returns a
    SendResult (never raises for an ordinary send failure — captured in the
    result + log).
    """
    from .models import MessageLog, WeddingGuest, WhatsAppConfig, WhatsAppStatus

    config = WhatsAppConfig.get()
    to = guest.phone_e164 or normalize_phone(guest.phone_number, config.default_country_code)
    if not to:
        result = SendResult(ok=False, error="رقم الهاتف غير صالح للإرسال.")
        MessageLog.objects.create(guest=guest, sender=sender, status=WhatsAppStatus.FAILED,
                                  error=result.error)
        return result

    now = timezone.now()
    variables = build_invitation_variables(guest)

    # Safe mode: log the intent, no network call, no cost.
    if not config.enabled:
        MessageLog.objects.create(
            guest=guest, sender=sender, template_name=config.content_sid,
            status=WhatsAppStatus.QUEUED, error="",
            payload={"simulated": True, "to": to, "vars": variables},
        )
        _touch_sent(guest, WhatsAppStatus.QUEUED, message_id="", now=now)
        return SendResult(ok=True, simulated=True)

    try:
        sid = send_content_message(to, config.content_sid, variables, config=config)
    except WhatsAppError as exc:
        MessageLog.objects.create(guest=guest, sender=sender, template_name=config.content_sid,
                                  status=WhatsAppStatus.FAILED, error=str(exc))
        guest.wa_status = WhatsAppStatus.FAILED
        guest.save(update_fields=["wa_status", "updated_at"])
        return SendResult(ok=False, error=str(exc))

    MessageLog.objects.create(guest=guest, sender=sender, template_name=config.content_sid,
                              wa_message_id=sid, status=WhatsAppStatus.SENT)
    _touch_sent(guest, WhatsAppStatus.SENT, message_id=sid, now=now)
    return SendResult(ok=True, message_id=sid)


def _touch_sent(guest, wa_status, *, message_id, now):
    """Update a guest's send bookkeeping after a (real or simulated) send."""
    from .models import WeddingGuest

    guest.wa_status = wa_status
    if message_id:
        guest.wa_message_id = message_id
    guest.invitation_status = WeddingGuest.Status.SENT_WHATSAPP
    guest.send_count = (guest.send_count or 0) + 1
    guest.last_sent_at = now
    if not guest.invited_at:
        guest.invited_at = now
    guest.save(update_fields=[
        "wa_status", "wa_message_id", "invitation_status", "send_count",
        "last_sent_at", "invited_at", "updated_at",
    ])


def send_test_message(recipient_e164):
    """Send a one-off test of the invitation Content Template to any recipient.

    Used by the admin "test send" button. Honours safe mode. Returns SendResult.
    """
    from .models import WhatsAppConfig

    config = WhatsAppConfig.get()
    to = normalize_phone(recipient_e164, config.default_country_code)
    if not to:
        return SendResult(ok=False, error="رقم الاختبار غير صالح.")
    if not config.enabled:
        return SendResult(ok=True, simulated=True)
    if not config.content_sid:
        return SendResult(ok=False, error="لا يوجد Content Template SID مُعرَّف.")
    variables = {
        "1": "اختبار",
        "2": "https://maps.google.com/",
        "3": _site_base() or "https://elzant.com",
        "4": "test",  # RSVP button token slot ({{4}}) — must be non-empty
    }
    try:
        sid = send_content_message(to, config.content_sid, variables, config=config)
    except WhatsAppError as exc:
        return SendResult(ok=False, error=str(exc))
    return SendResult(ok=True, message_id=sid)
