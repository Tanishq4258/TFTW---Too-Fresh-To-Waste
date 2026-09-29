"""
Authentication views for Too Fresh To Waste.

Endpoints:
  POST /api/auth/register/   — Create a new user account
  POST /api/auth/login/      — Obtain JWT access + refresh tokens
  POST /api/auth/logout/     — Blacklist the refresh token (server-side logout)
  POST /api/auth/token/refresh/ — Get a new access token using refresh token
  GET  /api/auth/me/         — Return the currently authenticated user's profile
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(APIView):
    """
    POST /api/auth/register/

    Body:
      {
        "first_name": "Aarav",
        "last_name": "Sharma",
        "email": "aarav@example.com",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
        "account_type": "customer"   // or "business"
      }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()

        # Issue tokens immediately on registration (auto-login)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Account created successfully.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login/

    Body:
      { "email": "user@example.com", "password": "secret" }

    Returns access + refresh tokens along with user profile.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomTokenObtainPairSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            # Provide a user-friendly error instead of DRF's generic message
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

        return Response(
            {
                'message': 'Login successful.',
                'user': serializer.validated_data['user'],
                'tokens': {
                    'access': serializer.validated_data['access'],
                    'refresh': serializer.validated_data['refresh'],
                },
            },
            status=status.HTTP_200_OK,
        )


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
            return Response(
                {'error': 'Invalid or expired refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


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


class TokenRefreshCustomView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/

    Standard Simple JWT token refresh — included for frontend use.
    """
    pass
