"""
Marketplace views for Too Fresh To Waste.
Provides endpoints for Customer, Restaurant, and Admin panels.
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Restaurant, FoodListing, Booking, Notification
from .serializers import (
    RestaurantSerializer,
    FoodListingSerializer,
    BookingSerializer,
    CreateBookingSerializer,
    NotificationSerializer,
)
from .permissions import IsAdminRole, IsRestaurantRole
from .realtime import broadcast_marketplace_event
from django.contrib.auth import get_user_model

User = get_user_model()
import re

def _expire_stale_listings():
    """
    Finds active listings that were created on a previous day OR whose 
    pickup time has finished today, and marks them as 'expired'.
    """
    now = timezone.localtime(timezone.now())
    today_date = now.date()
    current_hour = now.hour
    current_min = now.minute

    active_listings = FoodListing.objects.filter(status='active')
    to_update = []
    
    for listing in active_listings:
        listing_date = timezone.localtime(listing.created_at).date()
        expired = False
        
        if listing_date < today_date:
            expired = True
        else:
            match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?', str(listing.pickup_end))
            if match:
                h = int(match.group(1))
                m = int(match.group(2))
                meridiem = match.group(3)
                if meridiem:
                    meridiem = meridiem.lower()
                    if meridiem == 'pm' and h < 12:
                        h += 12
                    elif meridiem == 'am' and h == 12:
                        h = 0
                if current_hour > h or (current_hour == h and current_min > m):
                    expired = True
                    
        if expired:
            listing.status = 'expired'
            to_update.append(listing)
    
    if to_update:
        FoodListing.objects.bulk_update(to_update, ['status'])


# ─── RESTAURANT PROFILE VIEWS ──────────────────────────────────────────────────

class RestaurantListCreateView(APIView):
    """
    GET: Public list of active restaurants
    POST: Create a restaurant profile for current business/restaurant user
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        city = request.query_params.get('city')
        search = request.query_params.get('search')
        qs = Restaurant.objects.filter(status='active')
        if city:
            qs = qs.filter(city__iexact=city)
        if search:
            qs = qs.filter(Q(business_name__icontains=search) | Q(description__icontains=search))
        serializer = RestaurantSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        # Check if restaurant profile already exists
        if hasattr(user, 'restaurant_profile'):
            return Response(
                {"error": "Restaurant profile already exists for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy()
        serializer = RestaurantSerializer(data=data)
        if serializer.is_valid():
            restaurant = serializer.save(owner=user)
            # Ensure user account_type is set to restaurant
            if user.account_type != 'restaurant':
                user.account_type = 'restaurant'
                user.save(update_fields=['account_type'])
            return Response(RestaurantSerializer(restaurant).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RestaurantDetailView(APIView):
    """
    GET: Details of a single restaurant + their active listings
    PATCH: Update restaurant profile (Owner or Admin)
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=status.HTTP_404_NOT_FOUND)

        _expire_stale_listings()
        serializer = RestaurantSerializer(restaurant)
        data = serializer.data
        # Include active listings
        listings = restaurant.listings.filter(status='active')
        data['listings'] = FoodListingSerializer(listings, many=True).data
        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions: owner or admin
        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        if restaurant.owner != user and not is_admin:
            return Response({"error": "You do not have permission to modify this restaurant."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RestaurantSerializer(restaurant, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MyRestaurantProfileView(APIView):
    """
    GET /api/restaurants/me/
    Returns the restaurant profile of the currently logged-in business user,
    or auto-creates a starter profile if they registered as 'business' or 'restaurant'.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (user.account_type in ('restaurant', 'business') or user.is_staff or user.is_superuser):
            return Response({"error": "Account is not a restaurant partner."}, status=status.HTTP_403_FORBIDDEN)

        restaurant, created = Restaurant.objects.get_or_create(
            owner=user,
            defaults={
                'business_name': f"{user.first_name}'s Kitchen",
                'description': 'Delicious freshly prepared surplus food.',
                'category': 'Cafe & Bakery',
                'address': 'Main Market, Sector 17',
                'city': 'Chandigarh',
                'phone': user.phone or '+91 98765 43210',
                'banner_image': 'assets/images/hero_food.jpg',
                'status': 'active',
            }
        )
        serializer = RestaurantSerializer(restaurant)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ─── FOOD LISTING VIEWS ────────────────────────────────────────────────────────

class FoodListingListCreateView(APIView):
    """
    GET: Public browsing of surplus food listings with filters (search, category, city, max_price).
    POST: Restaurant creates a surplus food listing. Broadcasts listing_created.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        _expire_stale_listings()
        qs = FoodListing.objects.filter(status='active', restaurant__status='active')

        # Filters
        category = request.query_params.get('category')
        search = request.query_params.get('search')
        city = request.query_params.get('city')
        max_price = request.query_params.get('max_price')
        sort = request.query_params.get('sort', 'newest')

        if category and category != 'all':
            qs = qs.filter(category=category)
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(restaurant__business_name__icontains=search)
            )
        if city:
            qs = qs.filter(restaurant__city__iexact=city)
        if max_price:
            try:
                qs = qs.filter(discounted_price__lte=Decimal(max_price))
            except Exception:
                pass

        if sort == 'price_low':
            qs = qs.order_by('discounted_price')
        elif sort == 'price_high':
            qs = qs.order_by('-discounted_price')
        elif sort == 'discount':
            qs = qs.order_by(F('original_price') - F('discounted_price')).reverse()
        else:
            qs = qs.order_by('-created_at')

        serializer = FoodListingSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        if not (user.account_type in ('restaurant', 'business') or user.is_staff or user.is_superuser):
            return Response({"error": "Only restaurant accounts can create listings."}, status=status.HTTP_403_FORBIDDEN)

        # Get or create restaurant profile
        restaurant, _ = Restaurant.objects.get_or_create(
            owner=user,
            defaults={
                'business_name': f"{user.first_name}'s Kitchen",
                'description': 'Surplus food partner.',
                'category': 'Bakery & Cafe',
                'address': 'Sector 17',
                'city': 'Chandigarh',
            }
        )

        data = request.data.copy()
        # Default quantity_available to quantity if not supplied
        if 'quantity' in data and 'quantity_available' not in data:
            data['quantity_available'] = data['quantity']

        serializer = FoodListingSerializer(data=data)
        if serializer.is_valid():
            listing = serializer.save(restaurant=restaurant)
            listing_data = FoodListingSerializer(listing).data

            # Broadcast real-time event to all connected clients!
            broadcast_marketplace_event("listing_created", listing_data)

            return Response(listing_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FoodListingDetailView(APIView):
    """
    GET: Details of a food listing
    PATCH: Update listing (Owner restaurant or Admin). Broadcasts listing_updated.
    DELETE: Soft-delete/deactivate listing. Broadcasts listing_deleted.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        try:
            listing = FoodListing.objects.get(pk=pk)
        except FoodListing.DoesNotExist:
            return Response({"error": "Listing not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(FoodListingSerializer(listing).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        try:
            listing = FoodListing.objects.get(pk=pk)
        except FoodListing.DoesNotExist:
            return Response({"error": "Listing not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        if listing.restaurant.owner != user and not is_admin:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = FoodListingSerializer(listing, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save()
            # If quantity_available becomes 0, mark sold_out automatically
            if updated.quantity_available == 0 and updated.status == 'active':
                updated.status = 'sold_out'
                updated.save(update_fields=['status'])
            elif updated.quantity_available > 0 and updated.status == 'sold_out':
                updated.status = 'active'
                updated.save(update_fields=['status'])

            updated_data = FoodListingSerializer(updated).data
            broadcast_marketplace_event("listing_updated", updated_data)
            return Response(updated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            listing = FoodListing.objects.get(pk=pk)
        except FoodListing.DoesNotExist:
            return Response({"error": "Listing not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        if listing.restaurant.owner != user and not is_admin:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        listing.status = 'inactive'
        listing.save(update_fields=['status'])
        broadcast_marketplace_event("listing_deleted", {"id": listing.id})
        return Response({"message": "Listing deactivated successfully."}, status=status.HTTP_200_OK)


class MyRestaurantListingsView(APIView):
    """
    GET: Listings belonging to the logged-in restaurant owner.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'restaurant_profile'):
            return Response([], status=status.HTTP_200_OK)

        _expire_stale_listings()
        listings = user.restaurant_profile.listings.all().order_by('-created_at')
        serializer = FoodListingSerializer(listings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ─── BOOKINGS / ORDERS VIEWS ──────────────────────────────────────────────────

class BookingListCreateView(APIView):
    """
    GET:
      - Customers get their bookings
      - Restaurants get bookings for their restaurant
      - Admins get all bookings
    POST:
      - Authenticated customer creates a booking (atomic transaction).
        Broadcasts booking_created immediately.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser

        if is_admin:
            qs = Booking.objects.all().select_related('customer', 'restaurant', 'listing')
        elif user.account_type in ('restaurant', 'business'):
            if hasattr(user, 'restaurant_profile'):
                qs = Booking.objects.filter(restaurant=user.restaurant_profile).select_related('customer', 'restaurant', 'listing')
            else:
                qs = Booking.objects.none()
        else:
            qs = Booking.objects.filter(customer=user).select_related('customer', 'restaurant', 'listing')

        # Status filter
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        serializer = BookingSerializer(qs.order_by('-created_at'), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = serializer.save()
            booking_data = BookingSerializer(booking).data

            # Broadcast real-time event to Customer, Restaurant, and Admin panels!
            broadcast_marketplace_event("booking_created", {
                "booking": booking_data,
                "listing_id": booking.listing.id,
                "quantity_available": booking.listing.quantity_available,
                "listing_status": booking.listing.status,
                "restaurant_id": booking.restaurant.id,
                "customer_name": booking.customer.get_full_name(),
                "total_amount": str(booking.total_amount),
            })

            return Response(booking_data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BookingDetailView(APIView):
    """
    GET: Details of a single booking
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            booking = Booking.objects.select_related('customer', 'restaurant', 'listing').get(pk=pk)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        is_restaurant_owner = (booking.restaurant.owner == user)
        is_customer = (booking.customer == user)

        if not (is_admin or is_restaurant_owner or is_customer):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        return Response(BookingSerializer(booking).data, status=status.HTTP_200_OK)


class BookingStatusUpdateView(APIView):
    """
    PATCH /api/bookings/<id>/status/
    Updates booking status:
      PENDING -> CONFIRMED -> READY_FOR_PICKUP -> COMPLETED
      or CANCELLED (restores inventory atomically!)
    """
    permission_classes = [IsAuthenticated]

    VALID_TRANSITIONS = {
        'PENDING': ['CONFIRMED', 'CANCELLED'],
        'CONFIRMED': ['READY_FOR_PICKUP', 'CANCELLED'],
        'READY_FOR_PICKUP': ['COMPLETED', 'CANCELLED'],
        'COMPLETED': [],
        'CANCELLED': [],
    }

    def patch(self, request, pk):
        try:
            booking = Booking.objects.select_related('customer', 'restaurant', 'listing').get(pk=pk)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        reason = request.data.get('cancellation_reason', '')

        if not new_status or new_status not in dict(Booking.STATUS_CHOICES):
            return Response({"error": f"Invalid status: {new_status}."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        is_restaurant_owner = (booking.restaurant.owner == user)
        is_customer = (booking.customer == user)

        # Permission check
        if not (is_admin or is_restaurant_owner or (is_customer and new_status == 'CANCELLED')):
            return Response({"error": "You do not have permission to perform this status update."}, status=status.HTTP_403_FORBIDDEN)

        current_status = booking.status
        allowed_next = self.VALID_TRANSITIONS.get(current_status, [])

        if new_status not in allowed_next and not is_admin:
            return Response(
                {"error": f"Cannot transition from {current_status} to {new_status}. Allowed: {allowed_next}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            booking.status = new_status
            if reason:
                booking.cancellation_reason = reason

            # If cancelled, atomically restore inventory back to listing
            if new_status == 'CANCELLED':
                listing = FoodListing.objects.select_for_update().get(pk=booking.listing.id)
                listing.quantity_available += booking.quantity
                if listing.status == 'sold_out':
                    listing.status = 'active'
                listing.save(update_fields=['quantity_available', 'status', 'updated_at'])
                booking.payment_status = 'REFUNDED'

            booking.save()

            # Create notification for affected party
            if is_restaurant_owner or is_admin:
                # Notify customer
                Notification.objects.create(
                    user=booking.customer,
                    title=f"Order Update: {new_status}",
                    message=f"Order #{booking.booking_number} is now {new_status}.",
                    type='status_update',
                    related_booking=booking,
                )
            if is_customer and new_status == 'CANCELLED':
                # Notify restaurant owner
                Notification.objects.create(
                    user=booking.restaurant.owner,
                    title="Order Cancelled by Customer",
                    message=f"Order #{booking.booking_number} for {booking.listing.name} was cancelled by {user.get_full_name()}.",
                    type='cancellation',
                    related_booking=booking,
                )

        updated_booking_data = BookingSerializer(booking).data

        # Broadcast real-time status update!
        broadcast_marketplace_event("booking_status_changed", {
            "booking": updated_booking_data,
            "listing_id": booking.listing.id,
            "quantity_available": booking.listing.quantity_available,
            "listing_status": booking.listing.status,
            "new_status": new_status,
        })

        return Response(updated_booking_data, status=status.HTTP_200_OK)


# ─── IN-APP NOTIFICATIONS VIEWS ───────────────────────────────────────────────

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:30]
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
            notif.is_read = True
            notif.save(update_fields=['is_read'])
            return Response({"message": "Marked as read."}, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({"error": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All marked as read."}, status=status.HTTP_200_OK)


# ─── ADMIN DASHBOARD & ANALYTICS VIEWS ────────────────────────────────────────

class AdminDashboardStatsView(APIView):
    """
    GET /api/admin/dashboard/
    Strictly protected for ADMIN role.
    Aggregates full platform operational stats.
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Users breakdown
        total_customers = User.objects.filter(account_type='customer').count()
        total_restaurants = Restaurant.objects.count()
        active_restaurants = Restaurant.objects.filter(status='active').count()

        # Listings breakdown
        total_listings = FoodListing.objects.count()
        active_listings = FoodListing.objects.filter(status='active').count()
        sold_out_listings = FoodListing.objects.filter(status='sold_out').count()

        # Bookings breakdown
        bookings_qs = Booking.objects.all()
        total_bookings = bookings_qs.count()
        today_bookings = bookings_qs.filter(created_at__gte=today_start).count()
        pending_bookings = bookings_qs.filter(status='PENDING').count()
        confirmed_bookings = bookings_qs.filter(status='CONFIRMED').count()
        ready_bookings = bookings_qs.filter(status='READY_FOR_PICKUP').count()
        completed_bookings = bookings_qs.filter(status='COMPLETED').count()
        cancelled_bookings = bookings_qs.filter(status='CANCELLED').count()

        # Revenue calculation (non-cancelled orders)
        revenue_agg = bookings_qs.exclude(status='CANCELLED').aggregate(
            total_rev=Sum('total_amount'),
            items_sold=Sum('quantity'),
        )
        total_revenue = float(revenue_agg['total_rev'] or 0)
        food_items_sold = int(revenue_agg['items_sold'] or 0)

        # Active inventory remaining
        active_inventory = FoodListing.objects.filter(status='active').aggregate(
            rem=Sum('quantity_available')
        )['rem'] or 0

        # Estimated waste saved (approx 0.65 kg per meal / food box rescued)
        estimated_kg_saved = round(food_items_sold * 0.65, 1)

        # Recent activities
        recent_bookings = BookingSerializer(
            Booking.objects.all().select_related('customer', 'restaurant', 'listing').order_by('-created_at')[:8],
            many=True
        ).data

        recent_customers = [
            {
                "id": u.id,
                "name": u.get_full_name(),
                "email": u.email,
                "date_joined": u.date_joined,
                "is_active": u.is_active,
            }
            for u in User.objects.filter(account_type='customer').order_by('-date_joined')[:6]
        ]

        recent_restaurants = RestaurantSerializer(
            Restaurant.objects.all().order_by('-created_at')[:6],
            many=True
        ).data

        return Response({
            "metrics": {
                "total_customers": total_customers,
                "total_restaurants": total_restaurants,
                "active_restaurants": active_restaurants,
                "total_listings": total_listings,
                "active_listings": active_listings,
                "sold_out_listings": sold_out_listings,
                "total_bookings": total_bookings,
                "today_bookings": today_bookings,
                "pending_bookings": pending_bookings,
                "confirmed_bookings": confirmed_bookings,
                "ready_bookings": ready_bookings,
                "completed_bookings": completed_bookings,
                "cancelled_bookings": cancelled_bookings,
                "total_revenue": total_revenue,
                "food_items_sold": food_items_sold,
                "active_inventory_remaining": active_inventory,
                "estimated_kg_saved": estimated_kg_saved,
            },
            "recent_bookings": recent_bookings,
            "recent_customers": recent_customers,
            "recent_restaurants": recent_restaurants,
        }, status=status.HTTP_200_OK)


class AdminUsersListView(APIView):
    """
    GET /api/admin/users/
    Admin can search & list all users, filter by role.
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        search = request.query_params.get('search')
        role = request.query_params.get('role')
        qs = User.objects.all().order_by('-date_joined')

        if role:
            qs = qs.filter(account_type=role)
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        data = [
            {
                "id": u.id,
                "full_name": u.get_full_name(),
                "email": u.email,
                "phone": u.phone,
                "account_type": u.account_type,
                "is_active": u.is_active,
                "date_joined": u.date_joined,
                "last_login": u.last_login,
            }
            for u in qs
        ]
        return Response(data, status=status.HTTP_200_OK)


class AdminUserStatusToggleView(APIView):
    """
    PATCH /api/admin/users/<id>/status/
    Admin can enable/disable user accounts.
    """
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if user.is_superuser:
            return Response({"error": "Cannot modify superuser account."}, status=status.HTTP_400_BAD_REQUEST)

        is_active = request.data.get('is_active')
        if is_active is not None:
            user.is_active = bool(is_active)
            user.save(update_fields=['is_active'])

        return Response({
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "message": f"User is now {'active' if user.is_active else 'disabled'}.",
        }, status=status.HTTP_200_OK)


class AdminRestaurantStatusToggleView(APIView):
    """
    PATCH /api/admin/restaurants/<id>/status/
    Admin can approve or suspend a restaurant partner.
    """
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if new_status in ('active', 'suspended', 'pending'):
            restaurant.status = new_status
            restaurant.save(update_fields=['status'])
            return Response(RestaurantSerializer(restaurant).data, status=status.HTTP_200_OK)
        return Response({"error": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)


class AdminAnalyticsView(APIView):
    """
    GET /api/admin/analytics/
    Returns daily booking trends, top selling restaurants, top food items.
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        # Daily bookings for the last 7 days
        daily_trends = []
        for i in range(7):
            day = (seven_days_ago + timedelta(days=i)).date()
            count = Booking.objects.filter(
                created_at__date=day
            ).count()
            rev = Booking.objects.filter(
                created_at__date=day
            ).exclude(status='CANCELLED').aggregate(s=Sum('total_amount'))['s'] or 0
            daily_trends.append({
                "date": day.strftime("%b %d"),
                "bookings": count,
                "revenue": float(rev),
            })

        # Top restaurants by completed/confirmed sales
        top_restaurants = (
            Booking.objects.exclude(status='CANCELLED')
            .values('restaurant__id', 'restaurant__business_name')
            .annotate(
                total_orders=Count('id'),
                total_revenue=Sum('total_amount'),
                items_sold=Sum('quantity'),
            )
            .order_by('-total_revenue')[:5]
        )

        # Top items sold
        top_items = (
            Booking.objects.exclude(status='CANCELLED')
            .values('listing__id', 'listing__name')
            .annotate(
                orders_count=Count('id'),
                units_sold=Sum('quantity'),
                revenue=Sum('total_amount'),
            )
            .order_by('-units_sold')[:5]
        )

        return Response({
            "daily_trends": daily_trends,
            "top_restaurants": list(top_restaurants),
            "top_items": list(top_items),
        }, status=status.HTTP_200_OK)
