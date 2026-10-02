"""
Pricing and Cart validation engine for Too Fresh To Waste (TFTW).
CRITICAL SECURITY:
Backend is the sole source of truth for all prices, discounts, taxes, and fees.
Client amounts are NEVER trusted.
"""

from decimal import Decimal, ROUND_HALF_UP
from apps.marketplace.models import FoodListing


class PricingValidationError(Exception):
    """Raised when cart/pricing validation fails."""
    pass


def calculate_and_validate_order_price(listing_id, quantity):
    """
    Validates item availability, status, and stock from database.
    Calculates subtotal, applies server-controlled fees/taxes, and derives paise amount.

    Returns:
      dict with:
        listing: FoodListing instance (locked via select_for_update caller)
        unit_price: Decimal
        subtotal: Decimal
        platform_fee: Decimal
        taxes: Decimal
        total_amount: Decimal
        amount_paise: int (smallest currency unit for Razorpay)
    """
    # 1. Validate quantity
    if not isinstance(quantity, int) or quantity < 1:
        raise PricingValidationError("Quantity must be a positive integer greater than or equal to 1.")

    if quantity > 50:
        raise PricingValidationError("Maximum allowable quantity per booking is 50.")

    # 2. Retrieve listing from database
    try:
        listing = FoodListing.objects.select_related('restaurant').get(pk=listing_id)
    except FoodListing.DoesNotExist:
        raise PricingValidationError("Selected surplus food listing does not exist.")

    # 3. Validate status & stock
    if listing.status != 'active':
        raise PricingValidationError("This food listing is no longer active.")

    if listing.restaurant.status != 'active':
        raise PricingValidationError("The restaurant partner is currently not accepting orders.")

    if listing.quantity_available < quantity:
        raise PricingValidationError(
            f"Only {listing.quantity_available} item(s) available. Cannot book {quantity}."
        )

    # 4. Read trusted price from database
    unit_price = Decimal(str(listing.discounted_price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if unit_price <= Decimal('0.00'):
        raise PricingValidationError("Invalid item pricing configured.")

    # 5. Calculate Subtotal
    subtotal = (unit_price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 6. Server-controlled Platform fees & taxes (transparent zero or configured)
    platform_fee = Decimal('0.00')
    taxes = Decimal('0.00')

    # 7. Final amount
    total_amount = (subtotal + platform_fee + taxes).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 8. Bounds check (Razorpay min: ₹1.00 = 100 paise)
    amount_paise = int(total_amount * 100)
    if amount_paise < 100:
        raise PricingValidationError("Order total must be at least ₹1.00 for online payment.")

    return {
        'listing': listing,
        'unit_price': unit_price,
        'subtotal': subtotal,
        'platform_fee': platform_fee,
        'taxes': taxes,
        'total_amount': total_amount,
        'amount_paise': amount_paise,
    }
