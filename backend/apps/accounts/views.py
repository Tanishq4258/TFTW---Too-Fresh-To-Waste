"""
Authentication views for Too Fresh To Waste.

Endpoints:
  POST /api/auth/register/               — Create a new user account + send verification email
  POST /api/auth/login/                  — Obtain JWT tokens (warns if email unverified)
  POST /api/auth/logout/                 — Blacklist the refresh token (server-side logout)
  POST /api/auth/token/refresh/          — Refresh the access token
  GET  /api/auth/me/                     — Return the currently authenticated user's profile

  POST /api/auth/verify-email/           — Verify email using token from link
  POST /api/auth/resend-verification/    — Resend verification email (rate-limited)
  POST /api/auth/forgot-password/        — Request a password reset link (rate-limited)
  POST /api/auth/reset-password/         — Reset password using token from link

  GET  /api/auth/google/init/            — Start Google OAuth flow (returns redirect URL)
  GET  /api/auth/google/callback/        — Google OAuth callback handler
"""

import os
import logging
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import EmailVerificationToken, PasswordResetToken
from .serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
    ResendVerificationSerializer,
)
from .email_service import send_verification_email, send_password_reset_email
from .google_oauth import (
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_info,
    find_or_create_google_user,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# ─── Rate limiting helper ──────────────────────────────────────────────────────

def _rate_limit(cache_key: str, limit: int, window_seconds: int) -> bool:
    """
    Simple in-memory rate limiter using Django's cache.
    Returns True if the request is allowed, False if rate-limited.
    """
    count = cache.get(cache_key, 0)
    if count >= limit:
        return False
    cache.set(cache_key, count + 1, window_seconds)
    return True


def _get_client_ip(request) -> str:
    """Extract the real client IP, accounting for reverse proxy headers."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


# ─── Register ──────────────────────────────────────────────────────────────────

class RegisterView(APIView):
    """
    POST /api/auth/register/

    Creates a new user, sends a verification email, and returns JWT tokens.
    The account is created immediately but email_verified=False until confirmed.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ip = _get_client_ip(request)
        if not _rate_limit(f'register:{ip}', limit=10, window_seconds=3600):
            return Response(
                {'error': 'Too many registration attempts. Please try again later.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()

        # Send verification email (async in production; sync here for simplicity)
        try:
            token_obj = EmailVerificationToken.create_for_user(user)
            send_verification_email(user, token_obj.token)
        except Exception as e:
            logger.error(f"Failed to send verification email on register for {user.email}: {e}")
            # Don't fail registration if email sending fails — user can resend

        # Issue tokens immediately (user can browse but gated features require verified email)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Account created. Please check your email to verify your address.',
                'email_verification_required': True,
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ─── Login ─────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    """
    POST /api/auth/login/

    Body: { "email": "user@example.com", "password": "secret" }

    Returns access + refresh tokens along with user profile.
    Returns warning if email is not verified.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ip = _get_client_ip(request)
        email = request.data.get('email', '').lower().strip()

        # Per-IP rate limiting
        if not _rate_limit(f'login_ip:{ip}', limit=20, window_seconds=900):
            return Response(
                {'error': 'Too many login attempts. Please try again in 15 minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Per-email rate limiting (prevent account enumeration via timing)
        if email and not _rate_limit(f'login_email:{email}', limit=10, window_seconds=900):
            return Response(
                {'error': 'Too many login attempts for this email. Please try again in 15 minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = CustomTokenObtainPairSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            error_detail = str(e)
            if 'No active account' in error_detail or 'invalid_credentials' in error_detail.lower():
                return Response(
                    {'errors': {'non_field_errors': ['Invalid email or password.']}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.user
        response_data = {
            'message': 'Login successful.',
            'user': serializer.validated_data['user'],
            'tokens': {
                'access': serializer.validated_data['access'],
                'refresh': serializer.validated_data['refresh'],
            },
        }

        # Block if email not verified
        if not user.email_verified:
            return Response(
                {
                    'error': 'unverified_email',
                    'message': 'Please verify your email address to log in.',
                    'email_verification_required': True
                },
                status=status.HTTP_403_FORBIDDEN
            )

        return Response(response_data, status=status.HTTP_200_OK)


# ─── Logout ────────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Body:   { "refresh": "<refresh_token>" }
    Header: Authorization: Bearer <access_token>

    Blacklists the refresh token so it cannot be reused.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except (TokenError, InvalidToken):
            # Still return success — the token is already invalid/expired
            pass

        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


# ─── Me ────────────────────────────────────────────────────────────────────────

class MeView(APIView):
    """
    GET /api/auth/me/

    Header: Authorization: Bearer <access_token>

    Returns the authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ─── Token Refresh ──────────────────────────────────────────────────────────────

class TokenRefreshCustomView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/

    Standard Simple JWT token refresh — included for frontend use.
    """
    pass


# ─── Email Verification ────────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    """
    POST /api/auth/verify-email/

    Body: { "token": "<token from email link>" }

    Validates the token, marks email as verified, invalidates the token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        token_value = serializer.validated_data['token']

        try:
            token_obj = EmailVerificationToken.objects.select_related('user').get(token=token_value)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {'error': 'invalid_token', 'message': 'This verification link is invalid or has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token_obj.used:
            if token_obj.user.email_verified:
                return Response(
                    {'error': 'already_verified', 'message': 'Your email has already been verified. You can log in.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'error': 'token_used', 'message': 'This verification link has already been used. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token_obj.is_expired:
            return Response(
                {'error': 'token_expired', 'message': 'This verification link has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        user.email_verified = True
        user.save(update_fields=['email_verified'])

        token_obj.used = True
        token_obj.save(update_fields=['used'])

        logger.info(f"Email verified for {user.email}")

        # Issue fresh tokens so the user can be auto-logged-in after verification
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Email verified successfully! Welcome to Too Fresh To Waste.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            },
            status=status.HTTP_200_OK,
        )


# ─── Resend Verification ────────────────────────────────────────────────────────

class ResendVerificationView(APIView):
    """
    POST /api/auth/resend-verification/

    Body: { "email": "user@example.com" }

    Rate-limited: 3 requests per email per hour.
    Returns a generic message to avoid email enumeration.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()
        ip = _get_client_ip(request)

        # Rate limit per email and per IP
        if not _rate_limit(f'resend_verify:{email}', limit=3, window_seconds=3600):
            # Generic response to avoid revealing existence
            return Response(
                {'message': 'If this email belongs to an unverified account, a verification email has been sent.'},
                status=status.HTTP_200_OK,
            )
        if not _rate_limit(f'resend_verify_ip:{ip}', limit=10, window_seconds=3600):
            return Response(
                {'message': 'If this email belongs to an unverified account, a verification email has been sent.'},
                status=status.HTTP_200_OK,
            )

        # Generic response regardless of whether email exists (anti-enumeration)
        generic_response = Response(
            {'message': 'If this email belongs to an unverified account, a verification email has been sent.'},
            status=status.HTTP_200_OK,
        )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return generic_response

        if user.email_verified:
            return Response(
                {'error': 'already_verified', 'message': 'This email address has already been verified.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_obj = EmailVerificationToken.create_for_user(user)
            send_verification_email(user, token_obj.token)
        except Exception as e:
            logger.error(f"Failed to resend verification for {email}: {e}")

        return generic_response


# ─── Forgot Password ────────────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
    """
    POST /api/auth/forgot-password/

    Body: { "email": "user@example.com" }

    Rate-limited. Always returns a generic response (anti-enumeration).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()
        ip = _get_client_ip(request)

        if not _rate_limit(f'forgot_pw:{email}', limit=3, window_seconds=3600):
            return Response(
                {'message': 'If an account exists with this email, a password reset link has been sent.'},
                status=status.HTTP_200_OK,
            )
        if not _rate_limit(f'forgot_pw_ip:{ip}', limit=10, window_seconds=3600):
            return Response(
                {'message': 'If an account exists with this email, a password reset link has been sent.'},
                status=status.HTTP_200_OK,
            )

        generic_response = Response(
            {'message': 'If an account exists with this email, a password reset link has been sent.'},
            status=status.HTTP_200_OK,
        )

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return generic_response

        # Don't send reset to Google-only accounts that have no password
        if not user.has_usable_password() and user.google_id and not user.password:
            logger.info(f"Password reset attempted for Google-only account: {email}")
            return generic_response

        try:
            token_obj = PasswordResetToken.create_for_user(user)
            send_password_reset_email(user, token_obj.token)
        except Exception as e:
            logger.error(f"Failed to send password reset email for {email}: {e}")

        return generic_response


# ─── Reset Password ────────────────────────────────────────────────────────────

class ResetPasswordView(APIView):
    """
    POST /api/auth/reset-password/

    Body: { "token": "...", "password": "newpass", "confirm_password": "newpass" }

    Validates the token, resets the password, invalidates the token.
    Existing JWT tokens remain valid — user must log in again with new password.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        token_value = serializer.validated_data['token']
        new_password = serializer.validated_data['password']

        try:
            token_obj = PasswordResetToken.objects.select_related('user').get(token=token_value)
        except PasswordResetToken.DoesNotExist:
            return Response(
                {'error': 'invalid_token', 'message': 'This password reset link is invalid or has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token_obj.used:
            return Response(
                {'error': 'token_used', 'message': 'This password reset link has already been used. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token_obj.is_expired:
            return Response(
                {'error': 'token_expired', 'message': 'This password reset link has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        user.set_password(new_password)
        user.save(update_fields=['password'])

        token_obj.used = True
        token_obj.save(update_fields=['used'])

        logger.info(f"Password reset successfully for {user.email}")

        # Blacklist all existing refresh tokens for this user for security
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            outstanding = OutstandingToken.objects.filter(user=user)
            for t in outstanding:
                BlacklistedToken.objects.get_or_create(token=t)
        except Exception as e:
            logger.warning(f"Could not blacklist old tokens after reset for {user.email}: {e}")

        return Response(
            {'message': 'Password reset successfully. Please log in with your new password.'},
            status=status.HTTP_200_OK,
        )


# ─── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleAuthInitView(APIView):
    """
    GET /api/auth/google/init/

    Returns the Google OAuth authorization URL.
    Frontend should redirect the user to this URL.
    The state parameter is stored in the session to prevent CSRF.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if not GOOGLE_CLIENT_ID:
            return Response(
                {'error': 'Google OAuth is not configured on this server.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        auth_url, state = get_google_auth_url()
        # Store state in session for CSRF validation
        request.session['google_oauth_state'] = state
        request.session.save()

        return Response({'auth_url': auth_url, 'state': state}, status=status.HTTP_200_OK)


class GoogleAuthCallbackView(APIView):
    """
    GET /api/auth/google/callback/

    Handles the OAuth callback from Google.
    Exchanges the code for tokens, gets user info, finds/creates user,
    then redirects the browser to the frontend with JWT tokens in the URL fragment.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.http import HttpResponseRedirect

        error = request.GET.get('error')
        if error:
            redirect_url = f"{FRONTEND_URL}/login.html?google_error={error}"
            return HttpResponseRedirect(redirect_url)

        code = request.GET.get('code')
        state = request.GET.get('state')

        if not code:
            return HttpResponseRedirect(f"{FRONTEND_URL}/login.html?google_error=no_code")

        # Validate state (CSRF protection)
        session_state = request.session.get('google_oauth_state')
        if session_state and state and session_state != state:
            logger.warning("Google OAuth state mismatch — possible CSRF attack")
            return HttpResponseRedirect(f"{FRONTEND_URL}/login.html?google_error=state_mismatch")

        # Exchange code for tokens (client_secret stays server-side)
        token_data = exchange_code_for_tokens(code)
        if not token_data or 'access_token' not in token_data:
            return HttpResponseRedirect(f"{FRONTEND_URL}/login.html?google_error=token_exchange_failed")

        # Get user info from Google (verified by Google's servers)
        google_info = get_google_user_info(token_data['access_token'])
        if not google_info:
            return HttpResponseRedirect(f"{FRONTEND_URL}/login.html?google_error=userinfo_failed")

        # Find or create TFTW user
        user, created, error_msg = find_or_create_google_user(google_info)
        if error_msg or not user:
            return HttpResponseRedirect(f"{FRONTEND_URL}/login.html?google_error=account_error")

        # Issue TFTW JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Clear the state from session
        if 'google_oauth_state' in request.session:
            del request.session['google_oauth_state']

        # Redirect to frontend with tokens in URL fragment (not query params for security)
        # Frontend's auth.js handles this and stores in localStorage
        user_data = UserSerializer(user).data
        import json, urllib.parse
        user_json = urllib.parse.quote(json.dumps(user_data))

        if user.account_type == 'admin' or user.is_staff or user.is_superuser:
            redirect_page = 'admin-dashboard.html'
        elif user.account_type in ('restaurant', 'business'):
            redirect_page = 'restaurant-dashboard.html'
        else:
            redirect_page = 'index.html'

        redirect_url = (
            f"{FRONTEND_URL}/google-callback.html"
            f"?access={urllib.parse.quote(access_token)}"
            f"&refresh={urllib.parse.quote(refresh_token)}"
            f"&user={user_json}"
            f"&redirect={redirect_page}"
        )
        return HttpResponseRedirect(redirect_url)
