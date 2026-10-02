"""
Razorpay Service layer for Too Fresh To Waste (TFTW).
Wraps official Razorpay Python SDK with error handling, signature verification,
webhook validation, order creation, and refunds.
"""

import hmac
import hashlib
import logging
from django.conf import settings
import razorpay
from razorpay.errors import SignatureVerificationError, BadRequestError, GatewayError

logger = logging.getLogger('payments')


class RazorpayConfigError(Exception):
    """Raised when Razorpay credentials are missing or invalid."""
    pass


class RazorpayServiceError(Exception):
    """Raised when Razorpay API call fails."""
    pass


def get_razorpay_client():
    """
    Initializes and returns the official Razorpay client using configured settings.
    Never exposes or logs secret credentials.
    """
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')

    if not key_id or not key_secret:
        logger.error("Razorpay credentials missing from server environment configuration.")
        raise RazorpayConfigError("Payment gateway configuration error. Please contact support.")

    client = razorpay.Client(auth=(key_id, key_secret))
    client.set_app_details({"title": "Too Fresh To Waste", "version": "1.0.0"})
    return client


def create_razorpay_order(amount_paise, receipt, notes=None):
    """
    Creates an official Razorpay Order server-side.
    Amount must be an integer in the smallest currency unit (paise for INR).
    """
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise ValueError("Order amount must be a positive integer in paise.")

    client = get_razorpay_client()
    order_payload = {
        "amount": amount_paise,
        "currency": getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
        "receipt": str(receipt),
        "notes": notes or {},
        "payment_capture": 1,  # Auto-capture payment on authorization
    }

    try:
        logger.info(f"Creating Razorpay order for receipt={receipt}, amount_paise={amount_paise}")
        order = client.order.create(data=order_payload)
        logger.info(f"Razorpay order created successfully: {order.get('id')}")
        return order
    except Exception as exc:
        logger.error(f"Failed to create Razorpay order for receipt={receipt}: {str(exc)}")
        raise RazorpayServiceError("Failed to initiate payment order with payment gateway.") from exc


def verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verifies Razorpay payment signature server-side using the backend-only Secret Key.
    Returns True if valid, False otherwise. Never throws unhandled exceptions.
    """
    if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
        logger.warning("Payment signature verification failed: Missing required signature parameters.")
        return False

    client = get_razorpay_client()
    params = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params)
        logger.info(f"Signature verified successfully for payment_id={razorpay_payment_id}, order_id={razorpay_order_id}")
        return True
    except SignatureVerificationError:
        logger.warning(f"Signature verification rejected for payment_id={razorpay_payment_id}, order_id={razorpay_order_id}")
        return False
    except Exception as exc:
        logger.error(f"Unexpected error verifying signature: {str(exc)}")
        return False


def verify_razorpay_webhook_signature(body_bytes, signature, webhook_secret=None):
    """
    Verifies incoming webhook payload signature using HMAC-SHA256 against RAZORPAY_WEBHOOK_SECRET.
    Returns True if authentic, False otherwise.
    """
    secret = webhook_secret or getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured on server.")
        return False

    if not signature:
        logger.warning("Webhook request missing X-Razorpay-Signature header.")
        return False

    try:
        # Convert bytes to string if needed
        body_str = body_bytes.decode('utf-8') if isinstance(body_bytes, bytes) else str(body_bytes)
        client = get_razorpay_client()
        client.utility.verify_webhook_signature(body_str, signature, secret)
        return True
    except SignatureVerificationError:
        logger.warning("Webhook signature verification failed.")
        return False
    except Exception as exc:
        logger.error(f"Webhook signature check error: {str(exc)}")
        return False


def fetch_razorpay_payment(razorpay_payment_id):
    """
    Fetches verified payment details from Razorpay to retrieve method, bank, wallet, VPA.
    Safe failure fallback if network error occurs.
    """
    try:
        client = get_razorpay_client()
        return client.payment.fetch(razorpay_payment_id)
    except Exception as exc:
        logger.warning(f"Could not fetch details for payment_id={razorpay_payment_id}: {str(exc)}")
        return {}


def create_razorpay_refund(razorpay_payment_id, amount_paise=None, notes=None):
    """
    Initiates a secure server-side refund for a verified payment.
    Requires Razorpay Payment ID.
    If amount_paise is None, full refund is initiated.
    """
    if not razorpay_payment_id:
        raise ValueError("Valid razorpay_payment_id is required for refund.")

    client = get_razorpay_client()
    refund_data = {}
    if amount_paise is not None:
        if not isinstance(amount_paise, int) or amount_paise <= 0:
            raise ValueError("Refund amount must be a positive integer in paise.")
        refund_data["amount"] = amount_paise

    if notes:
        refund_data["notes"] = notes

    try:
        logger.info(f"Initiating Razorpay refund for payment_id={razorpay_payment_id}, amount_paise={amount_paise}")
        refund = client.payment.refund(razorpay_payment_id, refund_data)
        logger.info(f"Razorpay refund created: {refund.get('id')} for payment_id={razorpay_payment_id}")
        return refund
    except Exception as exc:
        logger.error(f"Failed to issue refund for payment_id={razorpay_payment_id}: {str(exc)}")
        raise RazorpayServiceError(f"Refund request failed: {str(exc)}") from exc
