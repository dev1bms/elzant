"""WhatsApp Cloud API integration — server-to-server, dependency-free.

Sends Meta-approved template messages via the Graph API and verifies inbound
webhook signatures. Uses the standard-library ``urllib`` (no ``requests``
dependency) with explicit timeouts and friendly error handling.

SECURITY:
- Secrets (token, app secret, verify token) are managed in the admin
  (WhatsAppConfig) — masked and superuser-only — never returned to clients and
  never logged verbatim. Protect the SQLite file and its backups accordingly.
- ``verify_webhook_signature`` enforces HMAC-SHA256 over the raw body; unsigned
  or mismatched requests are rejected.
- ``send_invitation`` honours WhatsAppConfig.enabled: when off (safe mode) it
  logs a simulated "would send" and performs NO network call — zero cost.
"""

import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.utils import timezone

GRAPH_BASE = "https://graph.facebook.com"
REQUEST_TIMEOUT = 15  # seconds — every network call is bounded


class WhatsAppError(Exception):
    """A send failed. Message is safe to store in MessageLog / show to admin."""


@dataclass
class SendResult:
    ok: bool
    message_id: str = ""
    simulated: bool = False   # True when safe-mode (enabled=False) — no real send
    error: str = ""


# --------------------------------------------------------------------------- #
# Phone normalization → E.164 without the leading "+"
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


# --------------------------------------------------------------------------- #
# Webhook signature verification (HMAC-SHA256 over the raw body)
# --------------------------------------------------------------------------- #
def verify_webhook_signature(request):
    """True iff X-Hub-Signature-256 matches HMAC-SHA256(app_secret, raw_body).

    Rejects (False) when the app secret is unset or the header is missing/malformed
    so an unsigned request can never be treated as authentic.
    """
    from .models import WhatsAppConfig
    secret = (WhatsAppConfig.get().app_secret or "").encode()
    if not secret:
        return False
    header = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
    if not header.startswith("sha256="):
        return False
    sent = header.split("=", 1)[1].strip()
    expected = hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sent, expected)


# --------------------------------------------------------------------------- #
# Low-level Graph API template send
# --------------------------------------------------------------------------- #
def _graph_url(phone_number_id, version="v21.0"):
    return f"{GRAPH_BASE}/{version or 'v21.0'}/{phone_number_id}/messages"


def send_template(to_e164, template_name, lang, components, *, phone_number_id, token, api_version="v21.0"):
    """POST a template message to the Cloud API. Returns the wa_message_id.

    Raises WhatsAppError with a friendly, secret-free message on any failure.
    """
    if not (token and phone_number_id):
        raise WhatsAppError("إعدادات واتساب ناقصة (التوكن أو Phone Number ID).")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang or "ar"},
            "components": components or [],
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _graph_url(phone_number_id, api_version),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise WhatsAppError(_graph_error_message(exc)) from exc
    except urllib.error.URLError as exc:
        raise WhatsAppError(f"تعذّر الاتصال بخدمة واتساب: {exc.reason}") from exc
    except (ValueError, TimeoutError) as exc:  # bad JSON / socket timeout
        raise WhatsAppError(f"استجابة غير متوقّعة من واتساب: {exc}") from exc

    messages = body.get("messages") or []
    if not messages or not messages[0].get("id"):
        raise WhatsAppError("لم تُعد خدمة واتساب معرّف رسالة.")
    return messages[0]["id"]


def _graph_error_message(http_error):
    """Extract Meta's error text from an HTTPError body (no secrets involved)."""
    try:
        body = json.loads(http_error.read().decode("utf-8") or "{}")
        err = body.get("error") or {}
        msg = err.get("message") or ""
        code = err.get("code")
        return f"خطأ من واتساب ({code}): {msg}" if msg else f"خطأ HTTP {http_error.code} من واتساب."
    except Exception:  # noqa: BLE001 — never let error parsing raise
        return f"خطأ HTTP {http_error.code} من واتساب."


# --------------------------------------------------------------------------- #
# Orchestration — build components, honour safe mode, log, update the guest
# --------------------------------------------------------------------------- #
def build_invitation_components(guest_name, token):
    """Body {{1}} = guest name; dynamic URL button {{1}} = invitation token.

    Matches the Utility template in GOAL §6.3 (base URL https://elzant.com/i/ +
    the token). The button param must be the token only, not the full URL.
    """
    return [
        {"type": "body", "parameters": [{"type": "text", "text": guest_name or ""}]},
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": token}],
        },
    ]


def send_invitation(guest, *, sender=None, template_name=None, force=False):
    """Send (or safe-mode simulate) the invitation template to a guest.

    Reads WhatsAppConfig for the phone_number_id / default template / enabled
    flag, builds the components from the guest, writes a MessageLog, and updates
    the guest's WhatsApp tracking fields. Returns a SendResult (never raises for
    an ordinary send failure — the failure is captured in the result + log).
    """
    from .models import MessageLog, WeddingGuest, WhatsAppConfig, WhatsAppStatus

    config = WhatsAppConfig.get()
    to = guest.phone_e164 or normalize_phone(guest.phone_number, config.default_country_code)
    if not to:
        result = SendResult(ok=False, error="رقم الهاتف غير صالح للإرسال.")
        MessageLog.objects.create(guest=guest, sender=sender, status=WhatsAppStatus.FAILED,
                                  error=result.error)
        return result

    tpl = template_name or config.default_template_name
    if not tpl:
        result = SendResult(ok=False, error="لا يوجد قالب واتساب مُعرَّف في الإعدادات.")
        MessageLog.objects.create(guest=guest, sender=sender, status=WhatsAppStatus.FAILED,
                                  error=result.error, template_name="")
        return result

    components = build_invitation_components(guest.full_name, guest.invitation_token)
    now = timezone.now()

    # Safe mode: log the intent, no network call, no cost.
    if not config.enabled:
        MessageLog.objects.create(
            guest=guest, sender=sender, template_name=tpl,
            status=WhatsAppStatus.QUEUED, error="", payload={"simulated": True, "to": to},
        )
        _touch_sent(guest, WhatsAppStatus.QUEUED, message_id="", now=now)
        return SendResult(ok=True, simulated=True)

    try:
        message_id = send_template(
            to, tpl, config.template_lang, components,
            phone_number_id=config.phone_number_id,
            token=config.api_token,
            api_version=config.api_version,
        )
    except WhatsAppError as exc:
        MessageLog.objects.create(guest=guest, sender=sender, template_name=tpl,
                                  status=WhatsAppStatus.FAILED, error=str(exc))
        guest.wa_status = WhatsAppStatus.FAILED
        guest.save(update_fields=["wa_status", "updated_at"])
        return SendResult(ok=False, error=str(exc))

    MessageLog.objects.create(guest=guest, sender=sender, template_name=tpl,
                              wa_message_id=message_id, status=WhatsAppStatus.SENT)
    _touch_sent(guest, WhatsAppStatus.SENT, message_id=message_id, now=now)
    return SendResult(ok=True, message_id=message_id)


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
    """Send a one-off test of the default template to an arbitrary recipient.

    Used by the admin "test send" button. Honours safe mode. Returns SendResult.
    """
    from .models import WhatsAppConfig

    config = WhatsAppConfig.get()
    to = normalize_phone(recipient_e164, config.default_country_code)
    if not to:
        return SendResult(ok=False, error="رقم الاختبار غير صالح.")
    if not config.default_template_name:
        return SendResult(ok=False, error="لا يوجد قالب افتراضي مُعرَّف.")
    if not config.enabled:
        return SendResult(ok=True, simulated=True)
    components = build_invitation_components("اختبار", "test-token")
    try:
        mid = send_template(
            to, config.default_template_name, config.template_lang, components,
            phone_number_id=config.phone_number_id,
            token=config.api_token,
            api_version=config.api_version,
        )
    except WhatsAppError as exc:
        return SendResult(ok=False, error=str(exc))
    return SendResult(ok=True, message_id=mid)
