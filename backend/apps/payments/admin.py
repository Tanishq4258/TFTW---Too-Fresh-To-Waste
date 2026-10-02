"""
Django Admin registration for Payments.
"""

from django.contrib import admin
from .models import Payment, PaymentWebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'booking',
        'customer',
        'razorpay_order_id',
        'razorpay_payment_id',
        'amount',
        'status',
        'payment_method',
        'paid_at',
        'created_at',
    )
    list_filter = ('status', 'currency', 'created_at', 'paid_at')
    search_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'booking__booking_number',
        'customer__email',
    )
    readonly_fields = (
        'id',
        'booking',
        'customer',
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'amount',
        'currency',
        'created_at',
        'updated_at',
        'paid_at',
    )


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'processed', 'processed_at', 'created_at')
    list_filter = ('event_type', 'processed', 'created_at')
    search_fields = ('event_id', 'event_type')
    readonly_fields = ('event_id', 'event_type', 'payload', 'processed', 'processed_at', 'created_at')
