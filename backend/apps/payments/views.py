"""
Payment API Views for Too Fresh To Waste (TFTW).
Implements secure Razorpay order initiation, official signature verification,
idempotent webhook processing, customer retry, and admin refunds.
"""

import json
import logging
import random
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Payment, PaymentWebhookEvent
from .serializers import (
    CreatePaymentOrderInputSerializer,
    VerifyPaymentInputSerializer,
    PaymentFailureInputSerializer,
    AdminRefundInputSerializer,
    PaymentDetailSerializer,
)
from .services import (
    get_razorpay_client,
    create_razorpay_order,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
    fetch_razorpay_payment,
    create_razorpay_refund,
    RazorpayConfigError,
    RazorpayServiceError,
)
from .pricing import calculate_and_validate_order_price, PricingValidationError
from apps.marketplace.models import FoodListing, Booking, Notification
from apps.marketplace.serializers import BookingSerializer
from apps.marketplace.permissions import IsAdminRole
from apps.marketplace.realtime import broadcast_marketplace_event

logger = logging.getLogger('payments')


class PaymentConfigView(APIView):
    """
    GET /api/payments/config/
    Returns public, client-safe configuration for Razorpay Checkout.
    CRITICAL: Never exposes RAZORPAY_KEY_SECRET or RAZORPAY_WEBHOOK_SECRET.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        return Response({
            "key_id": key_id,
            "currency": getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
            "is_configured": bool(key_id and getattr(settings, 'RAZORPAY_KEY_SECRET', '')),
        }, status=status.HTTP_200_OK)


class CreatePaymentOrderView(APIView):
    """
    POST /api/payments/create-order/
    Initiates the payment flow for surplus food booking.
    - Validates customer authentication.
    - Retrieves trusted price directly from DB (never trusts client amount).
    - Locks FoodListing row via select_for_update() to prevent overselling.
    - Creates Booking in PENDING state and decrements available inventory.
    - Creates Razorpay order server-side.
    - Returns Razorpay order details to frontend.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreatePaymentOrderInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        listing_id = serializer.validated_data['listing_id']
        quantity = serializer.validated_data['quantity']
        notes = serializer.validated_data.get('notes', '')

        try:
            with transaction.atomic():
                # 1. Lock the listing row to prevent simultaneous overselling
                try:
                    listing = FoodListing.objects.select_for_update().select_related('restaurant').get(pk=listing_id)
                except FoodListing.DoesNotExist:
                    return Response({"error": "Listing does not exist."}, status=status.HTTP_404_NOT_FOUND)

                # 2. Strict backend price calculation & inventory check
                pricing = calculate_and_validate_order_price(listing_id, quantity)
                unit_price = pricing['unit_price']
                total_amount = pricing['total_amount']
                amount_paise = pricing['amount_paise']

                # 3. Decrement available inventory atomically (held for payment)
                listing.quantity_available -= quantity
                if listing.quantity_available == 0:
                    listing.status = 'sold_out'
                listing.save(update_fields=['quantity_available', 'status', 'updated_at'])

                # 4. Generate 4-digit verification PIN for counter pickup
                pickup_code = f"{random.randint(1000, 9999)}"

                # 5. Create Booking in PENDING status
                booking = Booking.objects.create(
                    customer=user,
                    restaurant=listing.restaurant,
                    listing=listing,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_amount=total_amount,
                    status='PENDING',
                    payment_status='PAYMENT_PENDING',
                    payment_method='Razorpay',
                    pickup_start=listing.pickup_start,
                    pickup_end=listing.pickup_end,
                    pickup_code=pickup_code,
                    notes=notes,
                )

                # 6. Create Razorpay Order server-side
                try:
                    razorpay_order = create_razorpay_order(
                        amount_paise=amount_paise,
                        receipt=booking.booking_number,
                        notes={
                            "booking_id": booking.id,
                            "booking_number": booking.booking_number,
                            "customer_id": user.id,
                            "customer_email": user.email,
                            "listing_id": listing.id,
                            "listing_name": listing.name,
                        }
                    )
                except RazorpayConfigError as cfg_err:
                    # Rollback transaction automatically
                    raise cfg_err
                except Exception as rzp_err:
                    logger.error(f"Razorpay order creation failed: {str(rzp_err)}")
                    raise rzp_err

                razorpay_order_id = razorpay_order['id']

                # 7. Update booking with razorpay_order_id
                booking.razorpay_order_id = razorpay_order_id
                booking.save(update_fields=['razorpay_order_id', 'updated_at'])

                # 8. Create Payment record for transaction tracking
                payment = Payment.objects.create(
                    booking=booking,
                    customer=user,
                    razorpay_order_id=razorpay_order_id,
                    amount=total_amount,
                    currency=pricing.get('currency', 'INR') if isinstance(pricing, dict) and 'currency' in pricing else 'INR',
                    status='PAYMENT_PENDING',
                )

            # Return response for frontend Razorpay checkout
            return Response({
                "booking_id": booking.id,
                "booking_number": booking.booking_number,
                "razorpay_order_id": razorpay_order_id,
                "amount": str(total_amount),
                "amount_paise": amount_paise,
                "currency": getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
                "key_id": getattr(settings, 'RAZORPAY_KEY_ID', ''),
                "customer": {
                    "name": user.get_full_name() or user.email.split('@')[0],
                    "email": user.email,
                    "phone": user.phone or "",
                },
                "listing": {
                    "name": listing.name,
                    "restaurant_name": listing.restaurant.business_name,
                    "pickup_window": f"{listing.pickup_start} – {listing.pickup_end}",
                },
            }, status=status.HTTP_201_CREATED)

        except PricingValidationError as p_err:
            return Response({"error": str(p_err)}, status=status.HTTP_400_BAD_REQUEST)
        except RazorpayConfigError:
            return Response(
                {"error": "Payment gateway configuration error. Please contact the administrator."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("Unexpected error during payment order creation")
            return Response({"error": "Unable to initiate payment. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyPaymentView(APIView):
    """
    POST /api/payments/verify/
    Verifies Razorpay payment signature server-side.
    CRITICAL:
    - Never marks an order PAID based merely on frontend report.
    - Official Razorpay HMAC-SHA256 signature verification.
    - Protected against duplicate requests, replays, and race conditions.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        booking_id = serializer.validated_data['booking_id']
        razorpay_order_id = serializer.validated_data['razorpay_order_id']
        razorpay_payment_id = serializer.validated_data['razorpay_payment_id']
        razorpay_signature = serializer.validated_data['razorpay_signature']

        try:
            booking = Booking.objects.select_related('customer', 'restaurant', 'listing').get(pk=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        # IDOR Authorization check: Must be the order's customer or admin
        is_admin = user.account_type == 'admin' or user.is_staff or user.is_superuser
        if booking.customer != user and not is_admin:
            logger.warning(f"Unauthorized verification attempt on booking #{booking_id} by user {user.id}")
            return Response({"error": "You do not have permission to verify this order."}, status=status.HTTP_403_FORBIDDEN)

        # Check if booking is already PAID (Idempotent success)
        if booking.payment_status in ('PAID', 'PAYMENT_SUCCESS'):
            return Response({
                "status": "already_paid",
                "message": "Order is already paid and confirmed.",
                "booking": BookingSerializer(booking).data,
            }, status=status.HTTP_200_OK)

        # Validate that razorpay_order_id matches the booking
        if booking.razorpay_order_id and booking.razorpay_order_id != razorpay_order_id:
            logger.error(f"Mismatched razorpay_order_id for booking #{booking.id}: {booking.razorpay_order_id} vs {razorpay_order_id}")
            return Response({"error": "Order verification mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if payment_id has already been used on a different booking
        existing_payment = Payment.objects.filter(razorpay_payment_id=razorpay_payment_id).exclude(booking=booking).first()
        if existing_payment:
            logger.error(f"Duplicate payment replay detected! Payment ID {razorpay_payment_id} already attached to booking #{existing_payment.booking_id}")
            return Response({"error": "Invalid payment. Duplicate payment ID detected."}, status=status.HTTP_400_BAD_REQUEST)

        # ─── OFFICIAL SERVER-SIDE SIGNATURE VERIFICATION ───────────────────────
        is_valid = verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)
        if not is_valid:
            # Mark attempt as failed
            Payment.objects.filter(booking=booking, razorpay_order_id=razorpay_order_id).update(
                status='PAYMENT_FAILED',
                error_description='Invalid signature supplied during verification',
            )
            return Response({"error": "Payment verification failed. Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        # ─── UPDATE STATE ATOMICALLY ──────────────────────────────────────────
        with transaction.atomic():
            payment_record, _ = Payment.objects.get_or_create(
                booking=booking,
                razorpay_order_id=razorpay_order_id,
                defaults={
                    'customer': booking.customer,
                    'amount': booking.total_amount,
                    'currency': getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
                }
            )

            # Fetch payment details from Razorpay to capture payment method (UPI, card, etc.)
            rzp_details = fetch_razorpay_payment(razorpay_payment_id)
            method = rzp_details.get('method', '')
            bank = rzp_details.get('bank', '') or ''
            wallet = rzp_details.get('wallet', '') or ''
            vpa = rzp_details.get('vpa', '') or ''

            now = timezone.now()
            payment_record.status = 'PAID'
            payment_record.razorpay_payment_id = razorpay_payment_id
            payment_record.razorpay_signature = razorpay_signature
            payment_record.payment_method = method or 'Razorpay'
            payment_record.bank = bank
            payment_record.wallet = wallet
            payment_record.vpa = vpa
            payment_record.paid_at = now
            payment_record.save()

            # Confirm TFTW Order
            booking.status = 'CONFIRMED'
            booking.payment_status = 'PAID'
            booking.razorpay_payment_id = razorpay_payment_id
            booking.razorpay_signature = razorpay_signature
            booking.payment_timestamp = now
            booking.payment_method = f"Razorpay ({method.upper() if method else 'Online'})"
            booking.save()

            # Create in-app notification for restaurant partner
            Notification.objects.create(
                user=booking.restaurant.owner,
                title="New Paid Booking Received!",
                message=f"Order #{booking.booking_number}: {booking.quantity}x {booking.listing.name} paid online via {booking.payment_method}.",
                type='new_booking',
                related_booking=booking,
            )

            # Create confirmation notification for customer
            Notification.objects.create(
                user=booking.customer,
                title="Payment Confirmed!",
                message=f"Order #{booking.booking_number} for {booking.listing.name} is confirmed! Pickup PIN: {booking.pickup_code}.",
                type='status_update',
                related_booking=booking,
            )

        booking_data = BookingSerializer(booking).data

        # Broadcast real-time event to Customer, Restaurant, and Admin dashboards
        broadcast_marketplace_event("booking_created", {
            "booking": booking_data,
            "listing_id": booking.listing.id,
            "quantity_available": booking.listing.quantity_available,
            "listing_status": booking.listing.status,
            "restaurant_id": booking.restaurant.id,
            "customer_name": booking.customer.get_full_name(),
            "total_amount": str(booking.total_amount),
            "payment_status": "PAID",
        })

        return Response({
            "success": True,
            "message": "Payment verified and booking confirmed successfully.",
            "booking": booking_data,
        }, status=status.HTTP_200_OK)


class PaymentFailureReportView(APIView):
    """
    POST /api/payments/failure/
    Records payment failure or dismissal from checkout frontend.
    Allows customer to retry payment without losing their reservation immediately.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PaymentFailureInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        booking_id = serializer.validated_data['booking_id']
        razorpay_order_id = serializer.validated_data['razorpay_order_id']
        error_code = serializer.validated_data.get('error_code', '')
        error_description = serializer.validated_data.get('error_description', '')

        try:
            booking = Booking.objects.get(pk=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if booking.customer != user:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        # Do not overwrite if already paid
        if booking.payment_status in ('PAID', 'PAYMENT_SUCCESS'):
            return Response({"message": "Order is already paid."}, status=status.HTTP_200_OK)

        Payment.objects.filter(booking=booking, razorpay_order_id=razorpay_order_id).update(
            status='PAYMENT_FAILED',
            error_code=error_code,
            error_description=error_description,
        )
        booking.payment_status = 'PAYMENT_FAILED'
        booking.save(update_fields=['payment_status', 'updated_at'])

        logger.info(f"Payment failed recorded for booking #{booking.id}: {error_code} - {error_description}")
        return Response({"message": "Payment failure recorded. You may retry payment."}, status=status.HTTP_200_OK)


class RetryPaymentView(APIView):
    """
    POST /api/payments/retry/
    Allows customer to retry payment for an existing unpaid booking.
    Reuses existing Razorpay order or creates a fresh one cleanly.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking_id')
        if not booking_id:
            return Response({"error": "booking_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        try:
            booking = Booking.objects.select_related('listing', 'restaurant').get(pk=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if booking.customer != user:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        if booking.payment_status in ('PAID', 'PAYMENT_SUCCESS'):
            return Response({"error": "This booking is already paid."}, status=status.HTTP_400_BAD_REQUEST)

        if booking.status == 'CANCELLED':
            return Response({"error": "This booking has been cancelled and cannot be paid."}, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = int(booking.total_amount * 100)

        # If a Razorpay order already exists, reuse it; otherwise create a new one
        razorpay_order_id = booking.razorpay_order_id
        if not razorpay_order_id:
            try:
                razorpay_order = create_razorpay_order(
                    amount_paise=amount_paise,
                    receipt=booking.booking_number,
                    notes={"booking_id": booking.id, "booking_number": booking.booking_number}
                )
                razorpay_order_id = razorpay_order['id']
                booking.razorpay_order_id = razorpay_order_id
                booking.payment_status = 'PAYMENT_PENDING'
                booking.save(update_fields=['razorpay_order_id', 'payment_status', 'updated_at'])

                Payment.objects.create(
                    booking=booking,
                    customer=user,
                    razorpay_order_id=razorpay_order_id,
                    amount=booking.total_amount,
                    currency=getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
                    status='PAYMENT_PENDING',
                )
            except Exception as exc:
                return Response({"error": "Could not create payment order."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "booking_id": booking.id,
            "booking_number": booking.booking_number,
            "razorpay_order_id": razorpay_order_id,
            "amount": str(booking.total_amount),
            "amount_paise": amount_paise,
            "currency": getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
            "key_id": getattr(settings, 'RAZORPAY_KEY_ID', ''),
            "customer": {
                "name": user.get_full_name() or user.email,
                "email": user.email,
                "phone": user.phone or "",
            },
            "listing": {
                "name": booking.listing.name,
                "restaurant_name": booking.restaurant.business_name,
                "pickup_window": f"{booking.pickup_start} – {booking.pickup_end}",
            },
        }, status=status.HTTP_200_OK)


class RazorpayWebhookView(APIView):
    """
    POST /api/payments/webhook/
    Asynchronous Webhook listener for Razorpay payment events.
    Handles:
      - payment.captured / order.paid: Auto-confirms orders if customer closed browser
      - payment.failed: Records failed payment attempt
      - refund.processed: Reconciles refund state
    Guarantees:
      - HMAC-SHA256 signature verification against RAZORPAY_WEBHOOK_SECRET
      - Idempotent event processing via PaymentWebhookEvent ledger
    """
    permission_classes = [AllowAny]

    def post(self, request):
        signature = request.headers.get('X-Razorpay-Signature', '')
        raw_body = request.body

        # 1. Signature Verification
        if not verify_razorpay_webhook_signature(raw_body, signature):
            logger.warning("Rejected webhook: Invalid or missing X-Razorpay-Signature.")
            return Response({"error": "Invalid webhook signature"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Parse payload
        try:
            event_data = json.loads(raw_body.decode('utf-8'))
        except Exception:
            return Response({"error": "Invalid JSON body"}, status=status.HTTP_400_BAD_REQUEST)

        event_id = event_data.get('id')
        event_type = event_data.get('event')

        if not event_id or not event_type:
            return Response({"error": "Missing event ID or event type"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Idempotency Check: Don't process the same event twice
        existing_event = PaymentWebhookEvent.objects.filter(event_id=event_id).first()
        if existing_event and existing_event.processed:
            logger.info(f"Webhook event {event_id} already processed. Returning 200 OK.")
            return Response({"status": "already_processed"}, status=status.HTTP_200_OK)

        webhook_log, _ = PaymentWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={'event_type': event_type, 'payload': event_data}
        )

        logger.info(f"Processing Razorpay webhook: {event_type} [Event ID: {event_id}]")

        try:
            payload = event_data.get('payload', {})

            if event_type in ('payment.captured', 'order.paid'):
                # Extract payment entity
                payment_entity = payload.get('payment', {}).get('entity', {})
                razorpay_order_id = payment_entity.get('order_id')
                razorpay_payment_id = payment_entity.get('id')
                method = payment_entity.get('method', '')

                if razorpay_order_id:
                    with transaction.atomic():
                        booking = Booking.objects.select_related('customer', 'restaurant', 'listing').filter(
                            razorpay_order_id=razorpay_order_id
                        ).first()

                        if booking and booking.payment_status not in ('PAID', 'PAYMENT_SUCCESS'):
                            now = timezone.now()
                            booking.status = 'CONFIRMED'
                            booking.payment_status = 'PAID'
                            booking.razorpay_payment_id = razorpay_payment_id
                            booking.payment_timestamp = now
                            booking.payment_method = f"Razorpay ({method.upper() if method else 'Online'})"
                            booking.save()

                            Payment.objects.filter(
                                booking=booking,
                                razorpay_order_id=razorpay_order_id
                            ).update(
                                status='PAID',
                                razorpay_payment_id=razorpay_payment_id,
                                payment_method=method or 'Razorpay',
                                paid_at=now,
                            )

                            # Notify
                            Notification.objects.create(
                                user=booking.restaurant.owner,
                                title="New Paid Booking (Webhook)",
                                message=f"Order #{booking.booking_number} payment captured via Razorpay.",
                                type='new_booking',
                                related_booking=booking,
                            )

                            broadcast_marketplace_event("booking_status_changed", {
                                "booking": BookingSerializer(booking).data,
                                "listing_id": booking.listing.id,
                                "quantity_available": booking.listing.quantity_available,
                                "new_status": "CONFIRMED",
                            })

            elif event_type == 'payment.failed':
                payment_entity = payload.get('payment', {}).get('entity', {})
                razorpay_order_id = payment_entity.get('order_id')
                error_desc = payment_entity.get('error_description', '')
                error_code = payment_entity.get('error_code', '')

                if razorpay_order_id:
                    Payment.objects.filter(
                        razorpay_order_id=razorpay_order_id
                    ).exclude(status__in=['PAID', 'PAYMENT_SUCCESS']).update(
                        status='PAYMENT_FAILED',
                        error_code=error_code,
                        error_description=error_desc,
                    )
                    Booking.objects.filter(
                        razorpay_order_id=razorpay_order_id
                    ).exclude(payment_status__in=['PAID', 'PAYMENT_SUCCESS']).update(
                        payment_status='PAYMENT_FAILED'
                    )

            elif event_type == 'refund.processed':
                refund_entity = payload.get('refund', {}).get('entity', {})
                razorpay_payment_id = refund_entity.get('payment_id')
                refund_id = refund_entity.get('id')
                amount = Decimal(str(refund_entity.get('amount', 0) / 100))

                if razorpay_payment_id:
                    Payment.objects.filter(
                        razorpay_payment_id=razorpay_payment_id
                    ).update(
                        status='REFUNDED',
                        refund_status='REFUNDED',
                        refund_id=refund_id,
                        refund_amount=amount,
                        refunded_at=timezone.now(),
                    )
                    Booking.objects.filter(
                        razorpay_payment_id=razorpay_payment_id
                    ).update(
                        status='CANCELLED',
                        payment_status='REFUNDED',
                        refund_id=refund_id,
                        refund_status='REFUNDED',
                    )

            # Mark processed
            webhook_log.processed = True
            webhook_log.processed_at = timezone.now()
            webhook_log.save(update_fields=['processed', 'processed_at'])

            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Error processing webhook")
            webhook_log.error_message = str(exc)
            webhook_log.save(update_fields=['error_message'])
            return Response({"error": "Internal processing error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminRefundView(APIView):
    """
    POST /api/payments/refund/
    Strictly protected for ADMIN role.
    Processes refunds through official Razorpay Refund API and restores food listing inventory.
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = AdminRefundInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        booking_id = serializer.validated_data['booking_id']
        reason = serializer.validated_data.get('reason', 'Admin initiated refund')

        try:
            booking = Booking.objects.select_related('customer', 'restaurant', 'listing').get(pk=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if booking.refund_status == 'REFUNDED' or booking.payment_status == 'REFUNDED':
            return Response({"error": "Order has already been refunded."}, status=status.HTTP_400_BAD_REQUEST)

        if booking.payment_status not in ('PAID', 'PAYMENT_SUCCESS'):
            return Response({"error": f"Cannot refund booking with payment status: {booking.payment_status}."}, status=status.HTTP_400_BAD_REQUEST)


        if not booking.razorpay_payment_id:
            return Response({"error": "No verified Razorpay payment ID found for this order."}, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = int(booking.total_amount * 100)

        with transaction.atomic():
            # 1. Call Razorpay Refund API
            try:
                refund_resp = create_razorpay_refund(
                    razorpay_payment_id=booking.razorpay_payment_id,
                    amount_paise=amount_paise,
                    notes={"booking_id": booking.id, "reason": reason}
                )
                refund_id = refund_resp.get('id', f"rfnd_{booking.booking_number}")
            except Exception as exc:
                logger.error(f"Razorpay refund call failed for booking #{booking.id}: {str(exc)}")
                return Response({"error": f"Payment gateway refund failed: {str(exc)}"}, status=status.HTTP_502_BAD_GATEWAY)

            now = timezone.now()

            # 2. Update Booking status & restore inventory atomically
            booking.status = 'CANCELLED'
            booking.payment_status = 'REFUNDED'
            booking.refund_id = refund_id
            booking.refund_status = 'REFUNDED'
            booking.refund_amount = booking.total_amount
            booking.refunded_at = now
            booking.cancellation_reason = f"Refunded by Admin: {reason}"
            booking.save()

            # Restore inventory to FoodListing
            listing = FoodListing.objects.select_for_update().get(pk=booking.listing.id)
            listing.quantity_available += booking.quantity
            if listing.status == 'sold_out':
                listing.status = 'active'
            listing.save(update_fields=['quantity_available', 'status', 'updated_at'])

            # 3. Update Payment record
            Payment.objects.filter(booking=booking).update(
                status='REFUNDED',
                refund_status='REFUNDED',
                refund_id=refund_id,
                refund_amount=booking.total_amount,
                refunded_at=now,
            )

            # 4. In-App Notifications
            Notification.objects.create(
                user=booking.customer,
                title="Refund Processed",
                message=f"Your refund of ₹{booking.total_amount} for Order #{booking.booking_number} has been processed via Razorpay.",
                type='status_update',
                related_booking=booking,
            )

        # Broadcast update
        broadcast_marketplace_event("booking_status_changed", {
            "booking": BookingSerializer(booking).data,
            "listing_id": booking.listing.id,
            "quantity_available": booking.listing.quantity_available,
            "new_status": "CANCELLED",
        })

        return Response({
            "success": True,
            "message": "Refund processed successfully.",
            "refund_id": refund_id,
            "booking": BookingSerializer(booking).data,
        }, status=status.HTTP_200_OK)


class AdminPaymentsListView(APIView):
    """
    GET /api/payments/admin/all/
    Strictly protected for ADMIN role.
    Returns list of all payment transactions with filters.
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = Payment.objects.select_related('customer', 'booking').all().order_by('-created_at')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                models.Q(razorpay_order_id__icontains=search) |
                models.Q(razorpay_payment_id__icontains=search) |
                models.Q(booking__booking_number__icontains=search) |
                models.Q(customer__email__icontains=search)
            )

        serializer = PaymentDetailSerializer(qs[:100], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
