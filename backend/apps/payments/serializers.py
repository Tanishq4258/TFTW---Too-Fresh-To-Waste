"""
Serializers for TFTW Payments.
Validates input, shields secrets, and formats payment responses.
"""

from rest_framework import serializers
from .models import Payment, PaymentWebhookEvent
from apps.marketplace.models import Booking


class CreatePaymentOrderInputSerializer(serializers.Serializer):
    """
    Validates customer's request to begin payment and reserve surplus food.
    CRITICAL: Does NOT accept client amount or price. Backend derives price.
    """
    listing_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class VerifyPaymentInputSerializer(serializers.Serializer):
    """
    Validates Razorpay checkout response for server-side signature verification.
    """
    booking_id = serializers.IntegerField(min_value=1)
    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=255)


class PaymentFailureInputSerializer(serializers.Serializer):
    """
    Validates payment failure / cancellation reporting from frontend checkout.
    """
    booking_id = serializers.IntegerField(min_value=1)
    razorpay_order_id = serializers.CharField(max_length=100)
    error_code = serializers.CharField(required=False, allow_blank=True, default='')
    error_description = serializers.CharField(required=False, allow_blank=True, default='')


class AdminRefundInputSerializer(serializers.Serializer):
    """
    Validates admin refund requests.
    """
    booking_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, default='Admin initiated refund')


class PaymentDetailSerializer(serializers.ModelSerializer):
    """
    Serializes Payment model for customer and admin audits.
    Never exposes internal secrets.
    """
    customer_name = serializers.ReadOnlyField(source='customer.get_full_name')
    customer_email = serializers.ReadOnlyField(source='customer.email')
    booking_number = serializers.ReadOnlyField(source='booking.booking_number')

    class Meta:
        model = Payment
        fields = (
            'id',
            'booking',
            'booking_number',
            'customer',
            'customer_name',
            'customer_email',
            'razorpay_order_id',
            'razorpay_payment_id',
            'amount',
            'currency',
            'status',
            'payment_method',
            'bank',
            'wallet',
            'vpa',
            'error_code',
            'error_description',
            'refund_status',
            'refund_id',
            'refund_amount',
            'refunded_at',
            'paid_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields
