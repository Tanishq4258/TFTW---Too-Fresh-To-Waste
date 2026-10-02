"""
Marketplace models for Too Fresh To Waste (TFTW).

Defines:
  - Restaurant: Business profile connected to a User owner
  - FoodListing: Surplus food offerings with inventory & pickup windows
  - Booking: Orders placed by customers with atomic inventory deduction
  - Notification: Real-time user notification events
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator


def generate_booking_number():
    """Generates a human-friendly unique booking number like TFTW-849201."""
    return f"TFTW-{uuid.uuid4().hex[:6].upper()}"


class Restaurant(models.Model):
    """
    Restaurant / Food Partner profile.
    Linked to a User whose role is 'restaurant' or 'business'.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='restaurant_profile',
    )
    business_name = models.CharField(max_length=150, db_index=True)
    description = models.TextField(blank=True, default='')
    category = models.CharField(
        max_length=60,
        default='Bakery & Cafe',
        help_text='e.g., Bakery, Cafe, Restaurant, Sweet Shop',
    )
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, default='Chandigarh')
    phone = models.CharField(max_length=30, blank=True, default='')
    banner_image = models.CharField(
        max_length=500,
        blank=True,
        default='assets/images/hero_food.jpg',
        help_text='URL to restaurant header image or storefront photo',
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'restaurants'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} ({self.city})"


class FoodListing(models.Model):
    """
    Surplus food item listed by a restaurant for sale.
    """

    CATEGORY_CHOICES = [
        ('bakery', 'Bakery & Pastries'),
        ('meals', 'Prepared Meals & Combos'),
        ('desserts', 'Desserts & Sweets'),
        ('beverages', 'Beverages & Juices'),
        ('snacks', 'Snacks & Quick Bites'),
        ('grocery', 'Dairy & Fresh Produce'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('sold_out', 'Sold Out'),
        ('expired', 'Expired'),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='listings',
        db_index=True,
    )
    name = models.CharField(max_length=150, db_index=True)
    description = models.TextField()
    category = models.CharField(
        max_length=40,
        choices=CATEGORY_CHOICES,
        default='bakery',
        db_index=True,
    )
    image = models.CharField(
        max_length=500,
        blank=True,
        default='assets/images/bakery_box.jpg',
        help_text='Food image URL or relative asset path',
    )

    original_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    discounted_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Total quantity initially made available',
    )
    quantity_available = models.PositiveIntegerField(
        help_text='Remaining available quantity for booking',
    )
    pickup_start = models.CharField(
        max_length=50,
        default='7:00 PM',
        help_text='e.g., 7:00 PM or 19:00',
    )
    pickup_end = models.CharField(
        max_length=50,
        default='9:00 PM',
        help_text='e.g., 9:00 PM or 21:00',
    )
    pickup_instructions = models.TextField(
        blank=True,
        default='Show your booking ID at the counter during the pickup window.',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'food_listings'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.restaurant.business_name} (₹{self.discounted_price})"

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > 0:
            diff = self.original_price - self.discounted_price
            if diff > 0:
                return round((diff / self.original_price) * 100)
        return 0

    @property
    def is_available(self):
        return self.status == 'active' and self.quantity_available > 0


class Booking(models.Model):
    """
    Booking / Order placed by a customer.
    Deducts available inventory atomically.
    """

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('READY_FOR_PICKUP', 'Ready for Pickup'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('ORDER_CREATED', 'Order Created'),
        ('PAYMENT_PENDING', 'Payment Pending'),
        ('PAID', 'Paid'),
        ('PAYMENT_SUCCESS', 'Payment Success'),
        ('PAYMENT_FAILED', 'Payment Failed'),
        ('CANCELLED', 'Cancelled'),
        ('REFUND_PENDING', 'Refund Pending'),
        ('REFUNDED', 'Refunded'),
    ]

    booking_number = models.CharField(
        max_length=30,
        unique=True,
        default=generate_booking_number,
        db_index=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        db_index=True,
    )
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='bookings',
        db_index=True,
    )
    listing = models.ForeignKey(
        FoodListing,
        on_delete=models.PROTECT,
        related_name='bookings',
        db_index=True,
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
    )
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=25,
        choices=PAYMENT_STATUS_CHOICES,
        default='PAYMENT_PENDING',
        db_index=True,
    )
    payment_method = models.CharField(max_length=30, default='Razorpay')
    
    # Razorpay Transaction & Verification Fields
    razorpay_order_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, default='')
    payment_timestamp = models.DateTimeField(null=True, blank=True)
    
    # Refund Tracking
    refund_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    refund_status = models.CharField(max_length=30, blank=True, default='')
    refund_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    pickup_start = models.CharField(max_length=50, blank=True)
    pickup_end = models.CharField(max_length=50, blank=True)
    pickup_code = models.CharField(max_length=10, blank=True)
    notes = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_paid(self):
        return self.payment_status in ('PAID', 'PAYMENT_SUCCESS')


    class Meta:
        db_table = 'bookings'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.booking_number} ({self.status}) - {self.customer.get_full_name()}"


class Notification(models.Model):
    """
    In-app user notification for real-time alerts.
    """

    TYPE_CHOICES = [
        ('new_booking', 'New Booking Received'),
        ('status_update', 'Booking Status Updated'),
        ('cancellation', 'Booking Cancelled'),
        ('listing_update', 'Listing Update'),
        ('system', 'System Alert'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True,
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='system')
    is_read = models.BooleanField(default=False, db_index=True)
    related_booking = models.ForeignKey(
        Booking,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] to {self.user.email}: {self.title}"
