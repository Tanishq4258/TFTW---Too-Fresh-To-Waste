"""
Marketplace URL patterns for Too Fresh To Waste.
"""

from django.urls import path
from . import views

urlpatterns = [
    # ─── Restaurants ───────────────────────────────────────────────────────────
    path('restaurants/', views.RestaurantListCreateView.as_asgi() if hasattr(views.RestaurantListCreateView, 'as_asgi') else views.RestaurantListCreateView.as_view(), name='restaurant-list-create'),
    path('restaurants/me/', views.MyRestaurantProfileView.as_view(), name='my-restaurant-profile'),
    path('restaurants/<int:pk>/', views.RestaurantDetailView.as_view(), name='restaurant-detail'),

    # ─── Food Listings ────────────────────────────────────────────────────────
    path('listings/', views.FoodListingListCreateView.as_view(), name='listing-list-create'),
    path('listings/my/', views.MyRestaurantListingsView.as_view(), name='my-listings'),
    path('listings/<int:pk>/', views.FoodListingDetailView.as_view(), name='listing-detail'),

    # ─── Bookings / Orders ────────────────────────────────────────────────────
    path('bookings/', views.BookingListCreateView.as_view(), name='booking-list-create'),
    path('bookings/<int:pk>/', views.BookingDetailView.as_view(), name='booking-detail'),
    path('bookings/<int:pk>/status/', views.BookingStatusUpdateView.as_view(), name='booking-status-update'),

    # ─── In-App Notifications ─────────────────────────────────────────────────
    path('notifications/', views.NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/read/', views.NotificationMarkReadView.as_view(), name='notification-read'),
    path('notifications/read-all/', views.NotificationMarkAllReadView.as_view(), name='notification-read-all'),

    # ─── Admin Endpoints (Protected by IsAdminRole) ───────────────────────────
    path('admin/dashboard/', views.AdminDashboardStatsView.as_view(), name='admin-dashboard'),
    path('admin/users/', views.AdminUsersListView.as_view(), name='admin-users'),
    path('admin/users/<int:pk>/status/', views.AdminUserStatusToggleView.as_view(), name='admin-user-status'),
    path('admin/restaurants/<int:pk>/status/', views.AdminRestaurantStatusToggleView.as_view(), name='admin-restaurant-status'),
    path('admin/analytics/', views.AdminAnalyticsView.as_view(), name='admin-analytics'),
]
