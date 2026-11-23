"""Authentication views (JWT obtain/refresh/logout+blacklist, register, profile)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import ChangePasswordSerializer, RegisterSerializer, UserProfileSerializer
from apps.audit_logs.services import log_audit_event

User = get_user_model()


class AuditedTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        if resp.status_code == 200:
            email = request.data.get("email", "")
            user = User.objects.filter(email=email).first()
            log_audit_event(action="auth.login", actor=user, request=request, metadata={"email": email})
        return resp


class AuditedTokenRefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_audit_event(action="auth.register", actor=user, request=self.request, metadata={"email": user.email})


class LogoutView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        log_audit_event(action="auth.logout", actor=request.user, request=request)
        return Response({"status": "logged_out"}, status=status.HTTP_200_OK)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        log_audit_event(action="auth.password_changed", actor=user, request=request)
        return Response({"status": "password_updated"}, status=status.HTTP_200_OK)
