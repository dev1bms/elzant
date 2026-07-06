from django.urls import path

from . import views, webhooks

urlpatterns = [
    path("", views.home, name="home"),
    path("tahnia/shukran/", views.thank_you, name="thank_you"),
    path("i/<str:token>/", views.invitation, name="invitation"),
    path("privacy/", views.privacy, name="privacy"),
    # WhatsApp Cloud API status webhook (Meta calls this; signature-verified).
    path("webhooks/whatsapp/", webhooks.whatsapp_webhook, name="whatsapp_webhook"),
]
