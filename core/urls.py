from django.urls import path

from . import views, webhooks

urlpatterns = [
    path("", views.home, name="home"),
    path("tahnia/shukran/", views.thank_you, name="thank_you"),
    path("i/<str:token>/", views.invitation, name="invitation"),
    path("i/<str:token>/rsvp/", views.rsvp, name="rsvp"),
    path("privacy/", views.privacy, name="privacy"),
    # Twilio WhatsApp status callback (signature-verified).
    path("webhooks/twilio/", webhooks.twilio_status_webhook, name="twilio_status"),
    # Twilio inbound WhatsApp (quick-reply RSVP buttons), signature-verified.
    path("webhooks/twilio/inbound/", webhooks.twilio_inbound_webhook, name="twilio_inbound"),
]
