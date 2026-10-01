"""
Google OAuth 2.0 / OpenID Connect service for Too Fresh To Waste.

Uses the Authorization Code Flow (server-side) which is the most secure pattern
for web applications:
  1. Frontend redirects user to Google
  2. Google redirects back to backend callback with an authorization code
  3. Backend exchanges the code for tokens (client secret stays server-side)
  4. Backend verifies identity and finds/creates user
  5. Backend issues TFTW JWT tokens to frontend

Environment variables required:
  GOOGLE_CLIENT_ID     — from Google Cloud Console
  GOOGLE_CLIENT_SECRET — from Google Cloud Console
  GOOGLE_REDIRECT_URI  — must match exactly what's registered in Google Cloud Console
                         e.g. http://localhost:8000/api/auth/google/callback/ (dev)
                              https://api.toofreshtowaste.in/api/auth/google/callback/ (prod)
  FRONTEND_URL         — where to redirect after auth (e.g. https://toofreshtowaste.in)
"""

import os
import secrets
import logging
import urllib.parse

import requests as http_requests
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.getenv(
    'GOOGLE_REDIRECT_URI',
    'http://127.0.0.1:8000/api/auth/google/callback/'
)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://127.0.0.1:5500')

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'


def get_google_auth_url(state: str | None = None) -> tuple[str, str]:
    """
    Generate the Google OAuth2 authorization URL.
    Returns (auth_url, state) where state is a CSRF token.
    """
    if not state:
        state = secrets.token_urlsafe(32)

    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account',
    }
    auth_url = GOOGLE_AUTH_URL + '?' + urllib.parse.urlencode(params)
    return auth_url, state


def exchange_code_for_tokens(code: str) -> dict | None:
    """
    Exchange the authorization code for access/id tokens.
    Returns token dict or None on failure.
    Client secret is kept server-side — never sent to frontend.
    """
    try:
        resp = http_requests.post(GOOGLE_TOKEN_URL, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code',
        }, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Google token exchange failed: {e}")
        return None


def get_google_user_info(access_token: str) -> dict | None:
    """
    Fetch user profile from Google's userinfo endpoint.
    We verify using the access_token (not blindly trusting client-provided data).
    """
    try:
        resp = http_requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Google userinfo fetch failed: {e}")
        return None


def find_or_create_google_user(google_info: dict) -> tuple[User | None, bool, str]:
    """
    Find or create a TFTW user from Google profile info.

    Account linking logic (prevents duplicates):
      1. If google_id already linked → return that user.
      2. Elif email exists AND email is verified on Google → link Google to existing account.
      3. Else → create a new user with email_verified=True (Google confirmed it).

    Returns (user, created, error_message).
    If error, user=None and error_message is set.
    """
    google_id = google_info.get('sub')
    email = google_info.get('email', '').lower().strip()
    email_verified = google_info.get('email_verified', False)
    given_name = google_info.get('given_name', '')
    family_name = google_info.get('family_name', '')

    if not google_id or not email:
        return None, False, 'Google did not return required identity information.'

    if not email_verified:
        return None, False, 'Your Google account email is not verified with Google.'

    # 1. Existing user with this google_id
    try:
        user = User.objects.get(google_id=google_id)
        # Ensure email_verified is set
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        return user, False, ''
    except User.DoesNotExist:
        pass

    # 2. Existing account with same email (email-verified by Google = safe to link)
    try:
        user = User.objects.get(email=email)
        # Link this Google account
        user.google_id = google_id
        if not user.email_verified:
            user.email_verified = True
        user.save(update_fields=['google_id', 'email_verified'])
        return user, False, ''
    except User.DoesNotExist:
        pass

    # 3. Create new user
    user = User.objects.create_user(
        email=email,
        password=None,  # No password — Google-only account (set_unusable_password)
        first_name=given_name or email.split('@')[0],
        last_name=family_name or '',
        account_type='customer',
        email_verified=True,
        google_id=google_id,
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user, True, ''
