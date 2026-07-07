from django.urls import path

from . import views, webhooks

urlpatterns = [
    path("", views.home, name="home"),
    path("tahnia/shukran/", views.thank_you, name="thank_you"),
    path("i/<str:token>/", views.invitation, name="invitation"),
    path("privacy/", views.privacy, name="privacy"),
    # Twilio WhatsApp status callback (signature-verified).
    path("webhooks/twilio/", webhooks.twilio_status_webhook, name="twilio_status"),
]
