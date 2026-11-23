from django.urls import path

from apps.accounts.views import (
    AuditedTokenObtainPairView,
    AuditedTokenRefreshView,
    ChangePasswordView,
    LogoutView,
    ProfileView,
    RegisterView,
)

urlpatterns = [
    path("login/", AuditedTokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", AuditedTokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("me/", ProfileView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]
