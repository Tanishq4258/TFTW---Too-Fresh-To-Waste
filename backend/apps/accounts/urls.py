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
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/',    LoginView.as_view(),    name='auth-login'),
    path('logout/',   LogoutView.as_view(),   name='auth-logout'),
    path('me/',       MeView.as_view(),       name='auth-me'),
    path('token/refresh/', TokenRefreshCustomView.as_view(), name='auth-token-refresh'),
]
