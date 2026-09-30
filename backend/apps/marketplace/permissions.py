"""
Role-based permissions for TFTW Marketplace.
"""

from rest_framework import permissions


class IsAdminRole(permissions.BasePermission):
    """
    Allows access only to users with ADMIN role or is_staff / is_superuser.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (
                getattr(user, 'account_type', '') == 'admin' or
                user.is_staff or
                user.is_superuser
            )
        )


class IsRestaurantRole(permissions.BasePermission):
    """
    Allows access only to users with RESTAURANT role (or legacy 'business').
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (
                getattr(user, 'account_type', '') in ('restaurant', 'business') or
                user.is_staff or
                user.is_superuser
            )
        )


class IsCustomerRole(permissions.BasePermission):
    """
    Allows access only to authenticated customer accounts.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)
