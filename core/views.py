from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from .forms import GreetingForm
from .models import Greeting
from .utils import get_client_ip


# Rate-limit greeting submissions per IP. Active only when RATELIMIT_ENABLE is
# True (off in local dev); honeypot + moderation + length limits are the always-
# on defenses. GET requests are never limited (method="POST").
@ratelimit(key="ip", rate="5/h", method="POST", block=True)
def home(request):
    if request.method == "POST":
        form = GreetingForm(request.POST)
        if form.is_valid():
            greeting = form.save(commit=False)
            greeting.ip_address = get_client_ip(request)
            greeting.save()
            # Pass name/message to the thank-you page via the session (not the
            # pk) so pending records can't be enumerated or read by URL.
            request.session["card"] = {
                "name": greeting.name,
                "message": greeting.message,
            }
            return redirect("thank_you")
    else:
        form = GreetingForm()
    return render(
        request,
        "core/home.html",
        {"form": form, "greetings": Greeting.approved()},
    )


def thank_you(request):
    card = request.session.pop("card", None)  # consumed once
    if not card:
        return redirect("home")
    return render(request, "core/thank_you.html", {"card": card})
