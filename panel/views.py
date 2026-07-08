"""Family invite panel — mobile-first Arabic UI for sending WhatsApp invitations.

Access + data isolation live in panel.access (enforced in the view layer). The
add flow normalizes the phone, detects duplicates ("invited by X"), and only
sends after an explicit confirm. Sending is delegated to core.whatsapp, which
honours safe mode and writes the audit log + guest tracking fields.
"""

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from core.models import WeddingGuest, WhatsAppConfig, WhatsAppStatus
from core.qr import qr_svg
from core.whatsapp import normalize_phone, send_invitation

from .access import can_view_all, guest_or_403, inviter_required, visible_guests
from .forms import GuestInviteForm

_DELIVERED_PLUS = (WhatsAppStatus.DELIVERED, WhatsAppStatus.READ)


def _invitation_url(guest):
    return settings.SITE_URL.rstrip("/") + guest.get_absolute_url()


def _counters(qs):
    """Funnel counts for a guest queryset (one aggregate query)."""
    return qs.aggregate(
        total=Count("id"),
        sent=Count("id", filter=Q(send_count__gt=0)),
        delivered=Count("id", filter=Q(wa_status__in=_DELIVERED_PLUS)),
        read=Count("id", filter=Q(wa_status=WhatsAppStatus.READ)),
        opened=Count("id", filter=Q(last_opened_at__isnull=False)),
        greeted=Count("id", filter=Q(invitation_status=WeddingGuest.Status.GREETED)),
    )


_SENT_PLUS = (WhatsAppStatus.SENT, WhatsAppStatus.DELIVERED, WhatsAppStatus.READ)


def _last_log(guest):
    """Most recent send attempt (or None) — carries the safe-mode flag + errors."""
    return guest.message_logs.order_by("-created_at").first()


def _timeline(guest, log=None):
    """Ordered, honest status steps for the guest card.

    Each step carries a ``state``: ``done`` (✓), ``active`` (a live spinner while
    awaiting Twilio's next callback), ``failed`` (✕ + reason), ``simulated``
    (safe-mode: recorded, NOT actually sent), or ``idle`` (not reached yet).
    Crucially, a safe-mode "send" never shows as done — it was never sent.
    """
    wa = guest.wa_status
    simulated = bool(log and (log.payload or {}).get("simulated"))
    # A failed *attempt* doesn't always flip wa_status — send_invitation's
    # invalid-phone early return only writes a FAILED log — so trust the log too.
    last_failed = bool(log and log.status == WhatsAppStatus.FAILED)
    failed = wa == WhatsAppStatus.FAILED or last_failed
    sent = wa in _SENT_PLUS                 # truly handed off to Twilio
    delivered = wa in _DELIVERED_PLUS
    read = wa == WhatsAppStatus.READ

    error = ""
    if failed:
        fl = guest.message_logs.filter(status=WhatsAppStatus.FAILED).order_by("-created_at").first()
        error = (fl.error if fl else "") or "تعذّر الإرسال. تحقّق من إعدادات واتساب ورقم الهاتف."

    def step(label, state, when=None, detail=""):
        return {"label": label, "state": state, "when": when, "detail": detail}

    # 1) Sent — the step the safe-mode bug used to fake with a ✓.
    if failed:
        s_send = step("تعذّر الإرسال", "failed", guest.last_sent_at, error)
    elif simulated:
        s_send = step("وضع تجريبي — لم تُرسل فعلياً", "simulated", guest.last_sent_at,
                      "فعّل «الإرسال الحيّ» من إعدادات واتساب لإرسالها حقيقةً.")
    elif sent:
        s_send = step("أُرسلت", "done", guest.last_sent_at)
    else:
        s_send = step("لم تُرسل بعد", "idle")

    # 2) Delivered — spins until Twilio's delivery callback lands.
    if delivered:
        s_deliv = step("سُلّمت", "done", guest.delivered_at)
    elif sent:
        s_deliv = step("بانتظار التسليم…", "active")
    else:
        s_deliv = step("سُلّمت", "idle")

    # 3) Read — a bonus signal only. Recipients can turn read receipts off, so
    # never spin forever waiting on it: it's either read or simply not-yet.
    if read:
        s_read = step("قُرئت", "done", guest.read_at)
    else:
        s_read = step("قُرئت", "idle")

    # 4) Opened the link
    opened = guest.last_opened_at is not None
    s_open = step("فتح الرابط", "done" if opened else "idle", guest.last_opened_at)

    # 5) Wrote a greeting
    greeted = guest.invitation_status == WeddingGuest.Status.GREETED
    s_greet = step("كتب تهنئة", "done" if greeted else "idle")

    return [s_send, s_deliv, s_read, s_open, s_greet]


def _notify_result(request, guest, result):
    if result.simulated:
        messages.warning(request, f"وضع آمن: سُجِّلت الدعوة لـ«{guest.full_name}» بلا إرسال فعلي.")
    elif result.ok:
        messages.success(request, f"أُرسلت الدعوة إلى «{guest.full_name}» ✓")
    else:
        messages.error(request, f"تعذّر الإرسال إلى «{guest.full_name}»: {result.error}")


@inviter_required
def dashboard(request):
    mine = visible_guests(request.user, "mine")
    ctx = {
        "mine": _counters(mine),
        "recent": mine.order_by("-created_at")[:8],
        "view_all": can_view_all(request.user),
    }
    if ctx["view_all"]:
        ctx["all"] = _counters(visible_guests(request.user, "all"))
    return render(request, "panel/dashboard.html", ctx)


@inviter_required
def guests_list(request):
    scope = request.GET.get("scope", "mine")
    if scope == "all" and not can_view_all(request.user):
        scope = "mine"
    qs = visible_guests(request.user, scope).order_by("full_name")
    return render(request, "panel/guests_list.html", {
        "guests": qs,
        "scope": scope,
        "view_all": can_view_all(request.user),
        "counters": _counters(qs),
    })


@inviter_required
def guest_add(request):
    config = WhatsAppConfig.get()
    if request.method == "POST":
        form = GuestInviteForm(request.POST)
        confirm = request.POST.get("confirm") == "1"
        action = request.POST.get("action", "")
        if form.is_valid():
            full_name = form.cleaned_data["full_name"].strip()
            phone = form.cleaned_data["phone"].strip()
            e164 = normalize_phone(phone, config.default_country_code)
            if not e164:
                form.add_error("phone", "رقم الهاتف غير صالح — تأكّد منه.")
            else:
                existing = WeddingGuest.objects.select_related(
                    "invited_by__inviter_profile").filter(phone_e164=e164).first()
                # Duplicate found and not yet confirmed → show the attribution card.
                if existing and not confirm:
                    return render(request, "panel/guest_confirm.html", {
                        "existing": existing, "full_name": full_name, "phone": phone,
                    })
                if existing and action == "resend":
                    guest = existing            # same guest, same link — keep attribution
                else:
                    guest = WeddingGuest.objects.create(
                        full_name=full_name, phone_number=phone, phone_e164=e164,
                        invited_by=request.user,
                    )
                result = send_invitation(guest, sender=request.user)
                _notify_result(request, guest, result)
                return redirect("panel:guest_detail", guest_id=guest.id)
    else:
        form = GuestInviteForm()
    return render(request, "panel/guest_add.html", {"form": form, "config": config})


@inviter_required
def guest_detail(request, guest_id):
    guest = guest_or_403(request.user, guest_id)
    invitation_url = _invitation_url(guest)
    log = _last_log(guest)
    timeline = _timeline(guest, log)
    return render(request, "panel/guest_detail.html", {
        "guest": guest,
        "timeline": timeline,
        # Any step still "active" (awaiting a Twilio callback) → let the page
        # auto-refresh so the status advances without a manual reload.
        "has_pending": any(s["state"] == "active" for s in timeline),
        "invitation_url": invitation_url,
        "qr_svg": qr_svg(invitation_url),
        "can_edit": can_view_all(request.user) or guest.invited_by_id == request.user.id,
        "wa_live": WhatsAppConfig.get().enabled,
    })


@inviter_required
def guest_resend(request, guest_id):
    guest = guest_or_403(request.user, guest_id)
    if request.method == "POST":
        result = send_invitation(guest, sender=request.user)
        _notify_result(request, guest, result)
        return redirect("panel:guest_detail", guest_id=guest.id)
    return render(request, "panel/guest_resend.html", {"guest": guest})
