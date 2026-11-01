from django.urls import path

from apps.accounts.views import LoginView, LogoutView, MeView, csrf

urlpatterns = [
    path("csrf/", csrf, name="accounts-csrf"),
    path("login/", LoginView.as_view(), name="accounts-login"),
    path("logout/", LogoutView.as_view(), name="accounts-logout"),
    path("me/", MeView.as_view(), name="accounts-me"),
]
