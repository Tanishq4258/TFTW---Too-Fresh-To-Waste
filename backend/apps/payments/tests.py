"""
Comprehensive Automated Test Suite for TFTW Razorpay Payment Implementation.
Covers:
  1. Successful payment flow
  2. Failed payment handling
  3. User cancellation reporting
  4. Payment retry
  5. Duplicate payment attempt prevention
  6. Already-paid order protection
  7. Invalid Razorpay signature rejection
  8. Invalid Razorpay order ID
  9. Invalid payment ID
  10. Manipulated payment amount (backend controls final price)
  11. Manipulated item price / availability validation
  12. Manipulated quantity (zero, negative, overselling)
  13. IDOR / Cross-user order security check
  14. Unauthorized payment endpoint protection (401)
  15. Customer attempting admin refund endpoint (403)
  16. Customer attempting to force status to PAID directly (forbidden)
  17. Customer attempting admin payment list (403)
  18. Missing Razorpay credentials safe error handling
  19. Secret key exposure check (no secrets in responses or serializers)
  20. Webhook signature verification (valid vs tampered)
  21. Webhook idempotency (duplicate delivery protection)
  22. Payment replay protection (reusing payment ID across bookings)
  23. Webhook arriving before frontend callback
  24. Webhook arriving after frontend callback
  25. Admin refund execution and atomic inventory restoration
"""

import json
import hmac
import hashlib
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from razorpay.errors import SignatureVerificationError

from apps.accounts.models import User
from apps.marketplace.models import Restaurant, FoodListing, Booking
from apps.payments.models import Payment, PaymentWebhookEvent
from apps.payments.services import (
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
    create_razorpay_order,
    create_razorpay_refund,
    RazorpayConfigError,
)
from apps.payments.pricing import calculate_and_validate_order_price, PricingValidationError


TEST_KEY_ID = "rzp_test_TFTW123456789"
TEST_KEY_SECRET = "test_secret_super_key_987654321"
TEST_WEBHOOK_SECRET = "test_webhook_secret_key_12345"


@override_settings(
    RAZORPAY_KEY_ID=TEST_KEY_ID,
    RAZORPAY_KEY_SECRET=TEST_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET,
    RAZORPAY_CURRENCY="INR",
)
class RazorpayPaymentsTestSuite(TestCase):
    """
    Full automated test suite for Razorpay payment integration, security, and edge cases.
    """

    def setUp(self):
        # 1. Create Users
        self.customer = User.objects.create_user(
            email="test_customer@tftw.dev",
            password="CustomerPass123!",
            first_name="Rohan",
            last_name="Sharma",
            account_type="customer",
            phone="+919876543210",
        )
        self.other_customer = User.objects.create_user(
            email="other_customer@tftw.dev",
            password="OtherPass123!",
            first_name="Pooja",
            last_name="Verma",
            account_type="customer",
        )
        self.partner_user = User.objects.create_user(
            email="bakery_owner@tftw.dev",
            password="PartnerPass123!",
            first_name="Chef",
            last_name="Baker",
            account_type="restaurant",
        )
        self.admin_user = User.objects.create_superuser(
            email="admin_super@tftw.dev",
            password="AdminPass123!",
            first_name="Admin",
            last_name="Super",
        )

        # 2. Create Restaurant Profile
        self.restaurant = Restaurant.objects.create(
            owner=self.partner_user,
            business_name="The Artisan Bakehouse",
            description="Fresh artisan breads and pastries.",
            category="Bakery",
            address="SCO 45, Sector 35-C",
            city="Chandigarh",
            phone="+919876512345",
            status="active",
        )

        # 3. Create Food Listing (Price ₹300 -> ₹99, Qty: 10)
        self.listing = FoodListing.objects.create(
            restaurant=self.restaurant,
            name="Sourdough & Croissant Box",
            description="Freshly baked morning surplus pastries.",
            category="bakery",
            original_price=Decimal("300.00"),
            discounted_price=Decimal("99.00"),
            quantity=10,
            quantity_available=10,
            pickup_start="7:00 PM",
            pickup_end="9:00 PM",
            status="active",
        )

        # 4. API Clients
        self.client_anon = APIClient()

        self.client_customer = APIClient()
        self.client_customer.force_authenticate(user=self.customer)

        self.client_other = APIClient()
        self.client_other.force_authenticate(user=self.other_customer)

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin_user)

    # ─── 1. PUBLIC CONFIGURATION & SECRETS ────────────────────────────────────

    def test_payment_config_endpoint_never_exposes_secrets(self):
        """Verify public config returns key_id and currency but NEVER secret keys."""
        resp = self.client_anon.get("/api/payments/config/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data.get("key_id"), TEST_KEY_ID)
        self.assertEqual(data.get("currency"), "INR")
        self.assertTrue(data.get("is_configured"))

        # Strict Secret Leak Prevention
        content_str = resp.content.decode("utf-8")
        self.assertNotIn(TEST_KEY_SECRET, content_str)
        self.assertNotIn(TEST_WEBHOOK_SECRET, content_str)
        self.assertNotIn("secret", data)

    # ─── 2. BACKEND PRICE CONTROL & PRICING ENGINE ────────────────────────────

    def test_backend_controls_price_and_ignores_client_tampering(self):
        """Backend must calculate amount from DB; client-supplied price or amount is disregarded."""
        with patch("apps.payments.views.create_razorpay_order") as mock_rzp_order:
            mock_rzp_order.return_value = {"id": "order_test_99", "amount": 9900, "status": "created"}

            # Malicious client sends amount = 1
            payload = {
                "listing_id": self.listing.id,
                "quantity": 1,
                "amount": 1,         # Tampered!
                "total_amount": 1.0, # Tampered!
                "price": 0.50,       # Tampered!
            }
            resp = self.client_customer.post("/api/payments/create-order/", payload, format="json")
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
            data = resp.json()

            # Backend enforced trusted DB price: ₹99.00 = 9900 paise
            self.assertEqual(data["amount"], "99.00")
            self.assertEqual(data["amount_paise"], 9900)
            mock_rzp_order.assert_called_once()
            _, kwargs = mock_rzp_order.call_args
            if not kwargs:
                args = mock_rzp_order.call_args[0]
                self.assertEqual(args[0], 9900)
            else:
                self.assertEqual(kwargs.get("amount_paise"), 9900)

    def test_quantity_validation_zero_negative_and_oversell(self):
        """Validates that non-positive quantities and quantities exceeding stock are rejected."""
        # Zero quantity
        resp = self.client_customer.post("/api/payments/create-order/", {"listing_id": self.listing.id, "quantity": 0})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Negative quantity
        resp = self.client_customer.post("/api/payments/create-order/", {"listing_id": self.listing.id, "quantity": -3})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Oversell quantity (> available stock of 10)
        resp = self.client_customer.post("/api/payments/create-order/", {"listing_id": self.listing.id, "quantity": 15})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only 10 item(s) available", resp.json().get("error", ""))

    # ─── 3. ORDER INITIATION & INVENTORY ATOMICITY ────────────────────────────

    def test_successful_order_creation_holds_inventory_atomically(self):
        """Creating a payment order decrements available quantity atomically."""
        initial_stock = self.listing.quantity_available  # 10
        with patch("apps.payments.views.create_razorpay_order") as mock_rzp_order:
            mock_rzp_order.return_value = {"id": "order_test_stock1", "amount": 19800, "status": "created"}

            resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 2,
            })
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

            # Check stock decremented
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.quantity_available, initial_stock - 2)

            # Check Booking created in PENDING state
            booking = Booking.objects.get(pk=resp.json()["booking_id"])
            self.assertEqual(booking.status, "PENDING")
            self.assertEqual(booking.payment_status, "PAYMENT_PENDING")
            self.assertEqual(booking.razorpay_order_id, "order_test_stock1")
            self.assertEqual(booking.total_amount, Decimal("198.00"))

            # Check Payment record created
            payment = Payment.objects.get(booking=booking)
            self.assertEqual(payment.status, "PAYMENT_PENDING")
            self.assertEqual(payment.razorpay_order_id, "order_test_stock1")

    # ─── 4. PAYMENT SIGNATURE VERIFICATION ────────────────────────────────────

    def test_successful_payment_verification_confirms_order(self):
        """Valid Razorpay signature confirms order and transitions payment status to PAID."""
        with patch("apps.payments.views.create_razorpay_order") as mock_order:
            mock_order.return_value = {"id": "order_verify_ok_123", "amount": 9900, "status": "created"}
            create_resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 1,
            })
            booking_id = create_resp.json()["booking_id"]
            order_id = create_resp.json()["razorpay_order_id"]

        payment_id = "pay_test_succ_123456"
        # Generate valid HMAC-SHA256 signature
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        valid_signature = hmac.new(TEST_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        with patch("apps.payments.views.fetch_razorpay_payment") as mock_fetch:
            mock_fetch.return_value = {"method": "upi", "vpa": "rohan@okhdfcbank"}

            verify_resp = self.client_customer.post("/api/payments/verify/", {
                "booking_id": booking_id,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_signature,
            })
            self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)
            self.assertTrue(verify_resp.json().get("success"))

            booking = Booking.objects.get(pk=booking_id)
            self.assertEqual(booking.status, "CONFIRMED")
            self.assertEqual(booking.payment_status, "PAID")
            self.assertEqual(booking.razorpay_payment_id, payment_id)
            self.assertIsNotNone(booking.payment_timestamp)

            payment = Payment.objects.get(booking=booking)
            self.assertEqual(payment.status, "PAID")
            self.assertEqual(payment.razorpay_payment_id, payment_id)
            self.assertEqual(payment.payment_method, "upi")

    def test_invalid_signature_is_rejected_and_not_marked_paid(self):
        """Forged or altered signature must be rejected and order remains unpaid."""
        with patch("apps.payments.views.create_razorpay_order") as mock_order:
            mock_order.return_value = {"id": "order_fake_sig_123", "amount": 9900, "status": "created"}
            create_resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 1,
            })
            booking_id = create_resp.json()["booking_id"]
            order_id = create_resp.json()["razorpay_order_id"]

        fake_signature = "0000000000000000000000000000000000000000000000000000000000000000"

        verify_resp = self.client_customer.post("/api/payments/verify/", {
            "booking_id": booking_id,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_fake_9999",
            "razorpay_signature": fake_signature,
        })
        self.assertEqual(verify_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid signature", verify_resp.json().get("error", ""))

        booking = Booking.objects.get(pk=booking_id)
        self.assertNotEqual(booking.status, "CONFIRMED")
        self.assertNotEqual(booking.payment_status, "PAID")

    # ─── 5. DUPLICATE PAYMENT & REPLAY PROTECTION ────────────────────────────

    def test_already_paid_order_protection(self):
        """Once an order is PAID, subsequent verification calls return idempotent success without altering state."""
        with patch("apps.payments.views.create_razorpay_order") as mock_order:
            mock_order.return_value = {"id": "order_dup_test_1", "amount": 9900, "status": "created"}
            create_resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 1,
            })
            booking_id = create_resp.json()["booking_id"]
            order_id = create_resp.json()["razorpay_order_id"]

        payment_id = "pay_dup_test_999"
        sig = hmac.new(TEST_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

        # First verification
        self.client_customer.post("/api/payments/verify/", {
            "booking_id": booking_id,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
        })

        # Second verification (Replay attempt)
        second_resp = self.client_customer.post("/api/payments/verify/", {
            "booking_id": booking_id,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
        })
        self.assertEqual(second_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(second_resp.json().get("status"), "already_paid")

    def test_payment_id_replay_across_different_orders_is_blocked(self):
        """A payment ID cannot be reused across two different bookings."""
        # Booking 1
        b1 = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="CONFIRMED",
            payment_status="PAID",
            razorpay_order_id="order_111",
            razorpay_payment_id="pay_stolen_id_999",
        )
        Payment.objects.create(
            booking=b1,
            customer=self.customer,
            razorpay_order_id="order_111",
            razorpay_payment_id="pay_stolen_id_999",
            amount=Decimal("99.00"),
            status="PAID",
        )

        # Booking 2 (unpaid)
        b2 = Booking.objects.create(
            customer=self.other_customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_222",
        )

        sig = hmac.new(TEST_KEY_SECRET.encode(), f"order_222|pay_stolen_id_999".encode(), hashlib.sha256).hexdigest()

        # Attacker tries to use b1's payment ID on b2
        resp = self.client_other.post("/api/payments/verify/", {
            "booking_id": b2.id,
            "razorpay_order_id": "order_222",
            "razorpay_payment_id": "pay_stolen_id_999",
            "razorpay_signature": sig,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Duplicate payment ID detected", resp.json().get("error", ""))

    # ─── 6. IDOR & AUTHORIZATION TESTS ────────────────────────────────────────

    def test_cross_tenant_idor_prevention(self):
        """User A cannot verify or fail User B's order."""
        b = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_user_a",
        )

        # other_customer attempts to verify customer's booking
        resp = self.client_other.post("/api/payments/verify/", {
            "booking_id": b.id,
            "razorpay_order_id": "order_user_a",
            "razorpay_payment_id": "pay_hack_123",
            "razorpay_signature": "somesig",
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # other_customer attempts to report failure on customer's booking
        resp_fail = self.client_other.post("/api/payments/failure/", {
            "booking_id": b.id,
            "razorpay_order_id": "order_user_a",
        })
        self.assertEqual(resp_fail.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_rejected(self):
        """Anonymous requests to payment endpoints return 401 Unauthorized."""
        resp = self.client_anon.post("/api/payments/create-order/", {"listing_id": self.listing.id, "quantity": 1})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        resp2 = self.client_anon.post("/api/payments/verify/", {})
        self.assertEqual(resp2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_cannot_call_admin_refund(self):
        """Normal customer attempting admin refund endpoint is rejected with 403."""
        resp = self.client_customer.post("/api/payments/refund/", {"booking_id": 1, "reason": "steal"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_view_admin_payment_logs(self):
        """Normal customer attempting to view admin payments list is rejected with 403."""
        resp = self.client_customer.get("/api/payments/admin/all/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ─── 7. PAYMENT FAILURE & RETRY FLOW ──────────────────────────────────────

    def test_payment_failure_reporting_and_retry(self):
        """Customer reporting payment dismissal can retry payment cleanly."""
        with patch("apps.payments.views.create_razorpay_order") as mock_order:
            mock_order.return_value = {"id": "order_retry_101", "amount": 9900, "status": "created"}
            create_resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 1,
            })
            booking_id = create_resp.json()["booking_id"]
            order_id = create_resp.json()["razorpay_order_id"]

        # Report failure / dismissal
        fail_resp = self.client_customer.post("/api/payments/failure/", {
            "booking_id": booking_id,
            "razorpay_order_id": order_id,
            "error_code": "BAD_REQUEST_ERROR",
            "error_description": "User dismissed checkout",
        })
        self.assertEqual(fail_resp.status_code, status.HTTP_200_OK)

        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.payment_status, "PAYMENT_FAILED")

        # Retry payment
        retry_resp = self.client_customer.post("/api/payments/retry/", {"booking_id": booking_id})
        self.assertEqual(retry_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(retry_resp.json()["razorpay_order_id"], order_id)

    # ─── 8. WEBHOOK IMPLEMENTATION & IDEMPOTENCY ──────────────────────────────

    def test_webhook_signature_verification_and_event_reconciliation(self):
        """Authentic payment.captured webhook reconciles order to PAID."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_webhook_rec_1",
        )
        Payment.objects.create(
            booking=booking,
            customer=self.customer,
            razorpay_order_id="order_webhook_rec_1",
            amount=Decimal("99.00"),
            status="PAYMENT_PENDING",
        )

        webhook_payload = {
            "entity": "event",
            "account_id": "acc_12345",
            "event": "payment.captured",
            "id": "evt_capture_12345",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_captured_999",
                        "order_id": "order_webhook_rec_1",
                        "amount": 9900,
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                    }
                }
            }
        }
        body_bytes = json.dumps(webhook_payload).encode("utf-8")
        valid_webhook_sig = hmac.new(TEST_WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()

        # Send webhook
        resp = self.client_anon.post(
            "/api/payments/webhook/",
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_webhook_sig,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "CONFIRMED")
        self.assertEqual(booking.payment_status, "PAID")
        self.assertEqual(booking.razorpay_payment_id, "pay_captured_999")

        # Verify idempotency ledger
        evt = PaymentWebhookEvent.objects.get(event_id="evt_capture_12345")
        self.assertTrue(evt.processed)

        # ─── IDEMPOTENCY TEST: Redeliver identical webhook ───────────────────
        resp_dup = self.client_anon.post(
            "/api/payments/webhook/",
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_webhook_sig,
        )
        self.assertEqual(resp_dup.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_dup.json().get("status"), "already_processed")

    def test_webhook_with_invalid_signature_is_rejected(self):
        """Webhook with invalid signature returns 400 and is not processed."""
        payload = {"event": "payment.captured", "id": "evt_fake_999"}
        body_bytes = json.dumps(payload).encode("utf-8")

        resp = self.client_anon.post(
            "/api/payments/webhook/",
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="tampered_signature_123",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PaymentWebhookEvent.objects.filter(event_id="evt_fake_999").exists())

    # ─── 9. ADMIN REFUND ARCHITECTURE ─────────────────────────────────────────

    def test_admin_refund_restores_inventory_atomically(self):
        """Admin initiating refund calls Razorpay API, marks order refunded/cancelled, and restores food stock."""
        # Initial stock was 10. Let's make it 8 by booking 2.
        self.listing.quantity_available = 8
        self.listing.save()

        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=2,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("198.00"),
            status="CONFIRMED",
            payment_status="PAID",
            razorpay_order_id="order_refund_test",
            razorpay_payment_id="pay_to_refund_123",
        )
        Payment.objects.create(
            booking=booking,
            customer=self.customer,
            razorpay_order_id="order_refund_test",
            razorpay_payment_id="pay_to_refund_123",
            amount=Decimal("198.00"),
            status="PAID",
        )

        with patch("apps.payments.views.create_razorpay_refund") as mock_refund:
            mock_refund.return_value = {"id": "rfnd_test_official_888", "amount": 19800, "status": "processed"}

            resp = self.client_admin.post("/api/payments/refund/", {
                "booking_id": booking.id,
                "reason": "Customer fell ill and could not pick up",
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            data = resp.json()
            self.assertEqual(data["refund_id"], "rfnd_test_official_888")

            # Check Booking updated
            booking.refresh_from_db()
            self.assertEqual(booking.status, "CANCELLED")
            self.assertEqual(booking.payment_status, "REFUNDED")
            self.assertEqual(booking.refund_id, "rfnd_test_official_888")

            # Check inventory restored atomically: 8 + 2 = 10
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.quantity_available, 10)

    def test_refund_cannot_be_duplicated(self):
        """Already refunded order cannot be refunded again."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="CANCELLED",
            payment_status="REFUNDED",
            refund_status="REFUNDED",
            razorpay_order_id="order_ref_dup",
            razorpay_payment_id="pay_ref_dup",
        )

        resp = self.client_admin.post("/api/payments/refund/", {"booking_id": booking.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been refunded", resp.json().get("error", ""))

    # ─── 10. MISSING CREDENTIALS ERROR HANDLING ───────────────────────────────

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_missing_credentials_safe_error(self):
        """When credentials are not configured, server returns safe error without exposing internals or crashing."""
        resp = self.client_customer.post("/api/payments/create-order/", {
            "listing_id": self.listing.id,
            "quantity": 1,
        })
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("configuration error", resp.json().get("error", "").lower())

    # ─── 11. RELIABILITY & EDGE-CASE SCENARIOS ─────────────────────────────────

    def test_invalid_razorpay_order_id_mismatch(self):
        """Mismatched Razorpay order ID during verification is rejected."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_actual_123",
        )

        resp = self.client_customer.post("/api/payments/verify/", {
            "booking_id": booking.id,
            "razorpay_order_id": "order_wrong_999",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "somesig",
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mismatch", resp.json().get("error", "").lower())

    def test_customer_cannot_force_payment_status_paid_via_status_endpoint(self):
        """Customer cannot directly call booking status update endpoint to mark order PAID or COMPLETED."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
        )

        # Customer attempts to patch status to COMPLETED
        resp = self.client_customer.patch(f"/api/bookings/{booking.id}/status/", {
            "status": "COMPLETED",
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Customer attempts to send payment_status = PAID
        resp2 = self.client_customer.patch(f"/api/bookings/{booking.id}/status/", {
            "status": "CONFIRMED",
            "payment_status": "PAID",
        })
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "PENDING")
        self.assertEqual(booking.payment_status, "PAYMENT_PENDING")

    def test_webhook_arriving_before_frontend_callback(self):
        """When webhook arrives before frontend callback, frontend verify gracefully returns already_paid."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_race_before",
        )
        Payment.objects.create(
            booking=booking,
            customer=self.customer,
            razorpay_order_id="order_race_before",
            amount=Decimal("99.00"),
            status="PAYMENT_PENDING",
        )

        payment_id = "pay_race_before_999"

        # 1. Webhook arrives first
        webhook_payload = {
            "entity": "event",
            "event": "payment.captured",
            "id": "evt_race_1",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": "order_race_before",
                        "amount": 9900,
                        "currency": "INR",
                        "status": "captured",
                        "method": "card",
                    }
                }
            }
        }
        raw_body = json.dumps(webhook_payload).encode("utf-8")
        sig = hmac.new(TEST_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

        wh_resp = self.client_anon.post(
            "/api/payments/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        self.assertEqual(wh_resp.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "CONFIRMED")
        self.assertEqual(booking.payment_status, "PAID")

        # 2. Frontend callback arrives second
        client_sig = hmac.new(TEST_KEY_SECRET.encode(), f"order_race_before|{payment_id}".encode(), hashlib.sha256).hexdigest()
        fe_resp = self.client_customer.post("/api/payments/verify/", {
            "booking_id": booking.id,
            "razorpay_order_id": "order_race_before",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": client_sig,
        })
        self.assertEqual(fe_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(fe_resp.json().get("status"), "already_paid")

    def test_webhook_arriving_after_frontend_callback(self):
        """When frontend verify arrives first and confirms order, webhook arrives later and is acknowledged idempotently."""
        booking = Booking.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            listing=self.listing,
            quantity=1,
            unit_price=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            status="PENDING",
            payment_status="PAYMENT_PENDING",
            razorpay_order_id="order_race_after",
        )
        Payment.objects.create(
            booking=booking,
            customer=self.customer,
            razorpay_order_id="order_race_after",
            amount=Decimal("99.00"),
            status="PAYMENT_PENDING",
        )

        payment_id = "pay_race_after_999"

        # 1. Frontend verify arrives first
        client_sig = hmac.new(TEST_KEY_SECRET.encode(), f"order_race_after|{payment_id}".encode(), hashlib.sha256).hexdigest()
        with patch("apps.payments.views.fetch_razorpay_payment") as mock_fetch:
            mock_fetch.return_value = {"method": "upi"}
            fe_resp = self.client_customer.post("/api/payments/verify/", {
                "booking_id": booking.id,
                "razorpay_order_id": "order_race_after",
                "razorpay_payment_id": payment_id,
                "razorpay_signature": client_sig,
            })
            self.assertEqual(fe_resp.status_code, status.HTTP_200_OK)
            self.assertTrue(fe_resp.json().get("success"))

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, "PAID")

        # 2. Webhook arrives after
        webhook_payload = {
            "entity": "event",
            "event": "order.paid",
            "id": "evt_race_2",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": "order_race_after",
                        "amount": 9900,
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                    }
                }
            }
        }
        raw_body = json.dumps(webhook_payload).encode("utf-8")
        wh_sig = hmac.new(TEST_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

        wh_resp = self.client_anon.post(
            "/api/payments/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wh_sig,
        )
        self.assertEqual(wh_resp.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, "PAID")
        self.assertEqual(booking.status, "CONFIRMED")

    def test_razorpay_api_failure_rolls_back_cleanly(self):
        """If Razorpay API fails during order creation, database transactions roll back without dangling state."""
        initial_stock = self.listing.quantity_available
        with patch("apps.payments.views.create_razorpay_order", side_effect=Exception("Razorpay Gateway Down")):
            resp = self.client_customer.post("/api/payments/create-order/", {
                "listing_id": self.listing.id,
                "quantity": 1,
            })
            self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Check stock was NOT decremented
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.quantity_available, initial_stock)

            # Check no dangling payment was left
            self.assertFalse(Payment.objects.filter(customer=self.customer, status='PAYMENT_PENDING').exists())

