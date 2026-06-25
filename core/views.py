from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import GreetingForm
from .imaging import ImageError, process_image
from .models import Greeting, GreetingSuggestion, WeddingGuest
from .utils import country_from_request, flag_from_code, get_client_ip


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
                # Post-moderation: publish immediately; the admin can hide later.
                greeting.status = Greeting.Status.APPROVED
                greeting.approved_at = timezone.now()
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
            "greetings": Greeting.visible(),
            "suggestions": GreetingSuggestion.active_suggestions(),
            "guest": guest,
            "visitor_flag": flag_from_code(vcode),
            "visitor_country": vname,
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
        {"guest": guest, "suggestions": GreetingSuggestion.active_suggestions()},
    )


def privacy(request):
    return render(request, "core/privacy.html")


def _guest_from_session(request):
    token = request.session.get("invitation_token")
    if not token:
        return None
    return WeddingGuest.objects.filter(invitation_token=token).first()
