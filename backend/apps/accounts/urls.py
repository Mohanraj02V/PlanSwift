from django.urls import path

from apps.accounts.views import (
    AdminUserDetailView,
    AdminUserListCreateView,
    AuditedTokenObtainPairView,
    AuditedTokenRefreshView,
    ChangePasswordView,
    CsrfTokenView,
    DisabledRegisterView,
    LogoutView,
    ProfileView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("login/", AuditedTokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", AuditedTokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("register/", DisabledRegisterView.as_view(), name="auth-register-disabled"),
    path("me/", ProfileView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("users/", AdminUserListCreateView.as_view(), name="admin-users"),
    path("users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
]
