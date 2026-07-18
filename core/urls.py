from django.urls import path

from . import views, webhooks

urlpatterns = [
    path("", views.home, name="home"),
    path("tahnia/shukran/", views.thank_you, name="thank_you"),
    path("i/<str:token>/", views.invitation, name="invitation"),
    path("i/<str:token>/rsvp/", views.rsvp, name="rsvp"),
    # One-tap RSVP from WhatsApp URL buttons (GET). The token is the LAST path
    # segment on purpose: WhatsApp requires a URL-button variable to sit at the
    # end of the URL, so it can't be placed mid-path (e.g. /i/<token>/confirm).
    path("i/confirm/<str:token>/", views.rsvp_link, {"choice": "attending"}, name="rsvp_attend"),
    path("i/decline/<str:token>/", views.rsvp_link, {"choice": "declined"}, name="rsvp_decline"),
    path("privacy/", views.privacy, name="privacy"),
    # «أضف إلى التقويم» — downloadable calendar event built from WeddingConfig.
    path("wedding.ics", views.calendar_ics, name="calendar_ics"),
    # نبضات حساب مدة التصفح من صفحات الدعوة (sendBeacon)
    path("i/<str:token>/ping/", views.presence_ping, name="presence_ping"),
    # Direct /favicon.ico probes (old in-app browsers) → the resolved icon.
    path("favicon.ico", views.favicon_ico, name="favicon_ico"),
    # Twilio WhatsApp status callback (signature-verified).
    path("webhooks/twilio/", webhooks.twilio_status_webhook, name="twilio_status"),
    # Twilio inbound WhatsApp (quick-reply RSVP buttons), signature-verified.
    path("webhooks/twilio/inbound/", webhooks.twilio_inbound_webhook, name="twilio_inbound"),
]
