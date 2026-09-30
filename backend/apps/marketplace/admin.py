from django.contrib import admin
from .models import Restaurant, FoodListing, Booking, Notification


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'city', 'category', 'owner', 'status', 'created_at')
    list_filter = ('status', 'city', 'category')
    search_fields = ('business_name', 'owner__email', 'address')


@admin.register(FoodListing)
class FoodListingAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'category', 'original_price', 'discounted_price', 'quantity_available', 'status')
    list_filter = ('status', 'category', 'restaurant')
    search_fields = ('name', 'description', 'restaurant__business_name')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_number', 'customer', 'restaurant', 'listing', 'quantity', 'total_amount', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status')
    search_fields = ('booking_number', 'customer__email', 'restaurant__business_name')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'type', 'is_read', 'created_at')
    list_filter = ('is_read', 'type')
