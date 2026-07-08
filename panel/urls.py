from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(
        template_name="panel/login.html", redirect_authenticated_user=True,
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="panel:login"), name="logout"),

    path("", views.dashboard, name="dashboard"),
    path("guests/", views.guests_list, name="guests"),
    path("guests/add/", views.guest_add, name="guest_add"),
    path("guests/<int:guest_id>/", views.guest_detail, name="guest_detail"),
    path("guests/<int:guest_id>/resend/", views.guest_resend, name="guest_resend"),
    path("templates/", views.templates_list, name="templates"),
]
