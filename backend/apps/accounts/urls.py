"""
URL patterns for the accounts app.

All routes are prefixed with /api/auth/ from the root urlconf.
"""

from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    MeView,
    TokenRefreshCustomView,
    VerifyEmailView,
    ResendVerificationView,
    ForgotPasswordView,
    ResetPasswordView,
    GoogleAuthInitView,
    GoogleAuthCallbackView,
)

urlpatterns = [
    # ── Core auth ──────────────────────────────────────────────────────────────
    path('register/',       RegisterView.as_view(),       name='auth-register'),
    path('login/',          LoginView.as_view(),           name='auth-login'),
    path('logout/',         LogoutView.as_view(),          name='auth-logout'),
    path('me/',             MeView.as_view(),              name='auth-me'),
    path('token/refresh/',  TokenRefreshCustomView.as_view(), name='auth-token-refresh'),

    # ── Email verification ─────────────────────────────────────────────────────
    path('verify-email/',           VerifyEmailView.as_view(),       name='auth-verify-email'),
    path('resend-verification/',    ResendVerificationView.as_view(), name='auth-resend-verification'),

    # ── Password reset ─────────────────────────────────────────────────────────
    path('forgot-password/',    ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('reset-password/',     ResetPasswordView.as_view(),  name='auth-reset-password'),

    # ── Google OAuth ───────────────────────────────────────────────────────────
    path('google/init/',        GoogleAuthInitView.as_view(),     name='auth-google-init'),
    path('google/callback/',    GoogleAuthCallbackView.as_view(), name='auth-google-callback'),
]
