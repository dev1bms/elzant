from datetime import timedelta, timezone as datetime_timezone

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import GreetingForm
from .imaging import ImageError, process_image
from .models import Greeting, GreetingSuggestion, WeddingConfig, WeddingGuest
from .utils import country_from_request, flag_from_code, get_client_ip, has_arabic


# Newest greetings shown on the wall — keeps the homepage fast as submissions
# grow (each renders a photo thumbnail); older ones remain in the DB/admin.
WALL_LIMIT = 100


# سهرة الشباب — الثلاثاء 21/07/2026 الساعة 8:30 مساءً بتوقيت القاهرة (17:30Z).
# حدث لمرة واحدة قبل الزفاف بيوم؛ مثبَّت هنا عمداً (لا حقل إعدادات له).
YOUTH_EVENING_DT = timezone.datetime(2026, 7, 21, 17, 30, tzinfo=datetime_timezone.utc)


def _countdown_initial(target=None):
    """Server-side initial countdown values so the flip boxes show real numbers
    immediately (and without JS) instead of zeros until countdown.js kicks in."""
    remaining = (target or WeddingConfig.get().wedding_datetime) - timezone.now()
    total = max(int(remaining.total_seconds()), 0)
    return {
        "days": total // 86400,
        "hours": f"{(total % 86400) // 3600:02d}",
        "minutes": f"{(total % 3600) // 60:02d}",
        "seconds": f"{total % 60:02d}",
        "done": total == 0,
        "target": target,
    }


# Spam defenses are: CSRF, the hidden honeypot, model/form length limits, and
# manual moderation (nothing reaches the wall unapproved). Request throttling is
# intentionally NOT handled in-app — a per-process LocMem bucket is unreliable
# across Gunicorn workers and can unfairly block guests. Throttling is an
# edge/proxy responsibility (e.g. Cloudflare WAF / tunnel rules). See DEPLOY.md.
def home(request):
    guest = _guest_from_session(request)             # an invited visitor, or None
    vcode, vname = country_from_request(request)     # visitor country (Cloudflare/GeoIP)

    if request.method == "POST":
        form = GreetingForm(request.POST, request.FILES)
        if form.is_valid():
            # Process the optional photo first (resize/EXIF-strip/thumbnail). A
            # bad image re-renders the form with a friendly error and never saves.
            photo = form.cleaned_data.get("photo")
            display = thumb = None
            if photo:
                try:
                    display, thumb = process_image(photo)
                except ImageError as exc:
                    form.add_error("photo", str(exc))
            if not form.errors:
                greeting = form.save(commit=False)
                # Post-moderation for Arabic greetings (publish immediately); hold
                # entirely non-Arabic ones for review — spam here is almost always
                # non-Arabic. Links are already rejected by the form.
                is_ar = has_arabic(greeting.message)
                greeting.status = Greeting.Status.APPROVED if is_ar else Greeting.Status.HELD
                greeting.approved_at = timezone.now() if is_ar else None
                greeting.ip_address = get_client_ip(request)
                # Visitor country → flag on the wall (best-effort; never blocks the save).
                if vcode:
                    greeting.country_code = vcode
                if vname:
                    greeting.country_name = vname
                if display is not None:
                    greeting.uploaded_photo.save(display.name, display, save=False)
                    greeting.photo_thumbnail.save(thumb.name, thumb, save=False)
                # Link to the guest if they came from a private invitation link.
                if guest:
                    greeting.guest = guest
                greeting.save()
                if guest and guest.invitation_status != WeddingGuest.Status.GREETED:
                    guest.invitation_status = WeddingGuest.Status.GREETED
                    guest.save(update_fields=["invitation_status", "updated_at"])
                # Pass card data to the thank-you page via the session (not the
                # pk) so records can't be enumerated or read by URL.
                request.session["card"] = {
                    "name": greeting.name,
                    "message": greeting.message,
                    "photo": greeting.uploaded_photo.url if greeting.has_photo else "",
                    "template": greeting.effective_template(),
                }
                return redirect("thank_you")
    else:
        # Invited visitor → pre-fill their name (still editable).
        form = GreetingForm(initial={"name": guest.full_name}) if guest else GreetingForm()
    return render(
        request,
        "core/home.html",
        {
            "form": form,
            "greetings": Greeting.visible()[:WALL_LIMIT],
            "suggestions": GreetingSuggestion.active_suggestions(),
            "guest": guest,
            "visitor_flag": flag_from_code(vcode),
            "visitor_country": vname,
            "cd": _countdown_initial(),
            "cd_youth": _countdown_initial(YOUTH_EVENING_DT),
            # يختفي القسم كله بعد انتهاء السهرة بست ساعات
            "show_youth": timezone.now() < YOUTH_EVENING_DT + timedelta(hours=6),
        },
    )


def thank_you(request):
    card = request.session.pop("card", None)  # consumed once
    if not card:
        return redirect("home")
    return render(request, "core/thank_you.html", {"card": card})


def invitation(request, token):
    """Personalized invitation page reached via a guest's private link."""
    guest = get_object_or_404(WeddingGuest, invitation_token=token)

    # Mark as opened (without downgrading a guest who already greeted).
    if guest.invitation_status != WeddingGuest.Status.GREETED:
        guest.invitation_status = WeddingGuest.Status.OPENED
    guest.last_opened_at = timezone.now()
    guest.save(update_fields=["invitation_status", "last_opened_at", "updated_at"])

    # Remember the token so a greeting written next gets linked to this guest.
    request.session["invitation_token"] = token
    return render(
        request,
        "core/invitation.html",
        {"guest": guest, "suggestions": GreetingSuggestion.active_suggestions(),
         "cd": _countdown_initial(),
         "show_youth": timezone.now() < YOUTH_EVENING_DT + timedelta(hours=6)},
    )


def rsvp(request, token):
    """Record a guest's attendance reply (تأكيد الحضور / اعتذار) from their
    private invitation page. POST-only + CSRF; idempotent (a second reply just
    updates the choice). Redirects back to the invitation, which then reflects
    the stored state and the tactful thank-you configured in the admin."""
    guest = get_object_or_404(WeddingGuest, invitation_token=token)
    if request.method == "POST" and WeddingConfig.get().rsvp_enabled:
        choice = request.POST.get("choice", "")
        guest.set_rsvp(choice)  # silently ignores anything but attending/declined
    return redirect("invitation", token=token)


def rsvp_link(request, token, choice):
    """One-tap RSVP from a WhatsApp URL button (GET ``/r/y|n/<token>/``). Records
    the reply and shows a warm thank-you page. Idempotent — re-tapping (or tapping
    the other button) just updates the choice. The token is unguessable, so only
    the guest reaches this."""
    guest = get_object_or_404(WeddingGuest, invitation_token=token)
    config = WeddingConfig.get()
    if config.rsvp_enabled:
        guest.set_rsvp(choice)  # ignores anything but attending/declined
    thanks = ""
    if guest.rsvp == WeddingGuest.Rsvp.ATTENDING:
        thanks = config.rsvp_thanks_attending
    elif guest.rsvp == WeddingGuest.Rsvp.DECLINED:
        thanks = config.rsvp_thanks_declined
    return render(request, "core/rsvp_thanks.html", {
        "guest": guest,
        "thanks": thanks,
        "attending": guest.rsvp == WeddingGuest.Rsvp.ATTENDING,
        "declined": guest.rsvp == WeddingGuest.Rsvp.DECLINED,
    })


def privacy(request):
    return render(request, "core/privacy.html")


def favicon_ico(request):
    """Some clients probe /favicon.ico directly even when a <link rel=icon> is
    declared — answer with the resolved icon instead of a 404 on every visit."""
    from .context_processors import _favicon

    url = _favicon(WeddingConfig.get())
    if url:
        return redirect(url)
    return HttpResponse(status=204)


def _ics_escape(text):
    """Escape TEXT values per RFC 5545 §3.3.11."""
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _ics_fold(line):
    """Fold a content line to ≤75 octets (RFC 5545 §3.1) without splitting a
    UTF-8 sequence — Arabic text triples in octets, so folding is required."""
    out = []
    raw = line.encode("utf-8")
    while len(raw) > 74:
        cut = 74
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # inside a UTF-8 char
            cut -= 1
        out.append(raw[:cut])
        raw = b" " + raw[cut:]
    out.append(raw)
    return b"\r\n".join(out)


def calendar_ics(request):
    """«أضف إلى التقويم» — a downloadable calendar event built live from
    WeddingConfig (no dependency, hand-rolled RFC 5545). Times are emitted in
    UTC so every calendar app lands on the same Cairo instant; a display alarm
    reminds the guest a day ahead. Served as an attachment so WhatsApp's
    in-app browser hands it to the calendar app."""
    config = WeddingConfig.get()
    site_url = settings.SITE_URL.rstrip("/")
    domain = site_url.split("//")[-1].split("/")[0] or "elzant.com"
    fmt = "%Y%m%dT%H%M%SZ"
    start = config.wedding_datetime.astimezone(datetime_timezone.utc)
    end = start + timedelta(hours=4)  # typical celebration span; only a hint
    summary = f"حفل زفاف {config.groom_name} و{config.bride_name}"
    location = " — ".join(x for x in (config.venue_name, config.venue_address) if x)
    desc_parts = [f"يسعدنا حضوركم حفل زفاف {config.groom_name} و{config.bride_name} 🤍"]
    if config.map_url:
        desc_parts.append(f"الموقع على الخريطة: {config.map_url}")
    desc_parts.append(f"الدعوة: {site_url}")
    description = _ics_escape("\n".join(desc_parts))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//elzant//wedding//AR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:wedding-1@{domain}",
        f"DTSTAMP:{timezone.now().astimezone(datetime_timezone.utc).strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{description}",
    ]
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    if config.map_url:
        lines.append(f"URL:{config.map_url}")
    lines += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape(summary)}",
        "TRIGGER:-P1D",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    body = b"\r\n".join(_ics_fold(line) for line in lines) + b"\r\n"
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="elzant-wedding.ics"'
    return response


def _guest_from_session(request):
    token = request.session.get("invitation_token")
    if not token:
        return None
    return WeddingGuest.objects.filter(invitation_token=token).first()
