"""
Payment models for Too Fresh To Waste (TFTW).

Tracks:
  - Payment: Transaction lifecycle records tied to customer bookings and Razorpay orders.
  - PaymentWebhookEvent: Idempotent ledger of processed Razorpay webhook notifications.
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator


class Payment(models.Model):
    """
    Records an individual payment transaction attempt for a Booking.
    Maintains complete audit history and transitions through:
      ORDER_CREATED -> PAYMENT_PENDING -> PAID / PAYMENT_FAILED / CANCELLED -> REFUND_PENDING -> REFUNDED
    """

    STATUS_CHOICES = [
        ('ORDER_CREATED', 'Order Created'),
        ('PAYMENT_PENDING', 'Payment Pending'),
        ('PAID', 'Paid'),
        ('PAYMENT_SUCCESS', 'Payment Success'),  # Alias for PAID
        ('PAYMENT_FAILED', 'Payment Failed'),
        ('CANCELLED', 'Cancelled'),
        ('REFUND_PENDING', 'Refund Pending'),
        ('REFUNDED', 'Refunded'),
    ]

    booking = models.ForeignKey(
        'marketplace.Booking',
        on_delete=models.CASCADE,
        related_name='payments',
        db_index=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
        db_index=True,
    )

    # Razorpay Identifiers
    razorpay_order_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Razorpay order identifier returned by Orders API',
    )
    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text='Razorpay payment ID returned after successful authorization',
    )
    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='HMAC SHA-256 signature returned by Razorpay Checkout',
    )

    # Financial Attributes
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text='Amount in INR (Server-calculated)',
    )
    currency = models.CharField(max_length=10, default='INR')

    # Lifecycle State
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='ORDER_CREATED',
        db_index=True,
    )

    # Method & Channel Details (from Razorpay response)
    payment_method = models.CharField(max_length=50, blank=True, default='')  # upi, card, netbanking, wallet
    bank = models.CharField(max_length=50, blank=True, default='')
    wallet = models.CharField(max_length=50, blank=True, default='')
    vpa = models.CharField(max_length=100, blank=True, default='')

    # Failure Audit
    error_code = models.CharField(max_length=100, blank=True, default='')
    error_description = models.TextField(blank=True, default='')

    # Refund Audit
    refund_status = models.CharField(max_length=30, blank=True, default='')
    refund_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.id} | Order {self.razorpay_order_id} | ₹{self.amount} ({self.status})"

    @property
    def is_successful(self):
        return self.status in ('PAID', 'PAYMENT_SUCCESS')


class PaymentWebhookEvent(models.Model):
    """
    Idempotent ledger of all webhook events delivered by Razorpay.
    Prevents duplicate execution of order confirmation or refunds.
    """

    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'payment_webhook_events'
        ordering = ['-created_at']

    def __str__(self):
        return f"WebhookEvent {self.event_id} ({self.event_type}) - Processed={self.processed}"
