"""
Serializers for TFTW Marketplace.
"""

from rest_framework import serializers
from django.db import transaction
from .models import Restaurant, FoodListing, Booking, Notification


class RestaurantSerializer(serializers.ModelSerializer):
    owner_email = serializers.ReadOnlyField(source='owner.email')
    owner_name = serializers.ReadOnlyField(source='owner.get_full_name')

    class Meta:
        model = Restaurant
        fields = (
            'id',
            'owner',
            'owner_email',
            'owner_name',
            'business_name',
            'description',
            'category',
            'address',
            'city',
            'phone',
            'banner_image',
            'latitude',
            'longitude',
            'status',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')


class FoodListingSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.ReadOnlyField(source='restaurant.business_name')
    restaurant_city = serializers.ReadOnlyField(source='restaurant.city')
    restaurant_address = serializers.ReadOnlyField(source='restaurant.address')
    restaurant_phone = serializers.ReadOnlyField(source='restaurant.phone')
    discount_percent = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()

    class Meta:
        model = FoodListing
        fields = (
            'id',
            'restaurant',
            'restaurant_name',
            'restaurant_city',
            'restaurant_address',
            'restaurant_phone',
            'name',
            'description',
            'category',
            'image',
            'original_price',
            'discounted_price',
            'discount_percent',
            'quantity',
            'quantity_available',
            'pickup_start',
            'pickup_end',
            'pickup_instructions',
            'status',
            'is_available',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'restaurant', 'created_at', 'updated_at')

    def validate(self, attrs):
        orig = attrs.get('original_price', getattr(self.instance, 'original_price', None))
        disc = attrs.get('discounted_price', getattr(self.instance, 'discounted_price', None))
        if orig is not None and disc is not None:
            if disc > orig:
                raise serializers.ValidationError({
                    'discounted_price': 'Discounted price cannot be greater than original price.'
                })

        qty = attrs.get('quantity', getattr(self.instance, 'quantity', None))
        if qty is not None and qty < 1:
            raise serializers.ValidationError({
                'quantity': 'Quantity must be at least 1.'
            })

        return attrs


class BookingSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.get_full_name')
    customer_email = serializers.ReadOnlyField(source='customer.email')
    customer_phone = serializers.ReadOnlyField(source='customer.phone')
    restaurant_name = serializers.ReadOnlyField(source='restaurant.business_name')
    restaurant_address = serializers.ReadOnlyField(source='restaurant.address')
    listing_name = serializers.ReadOnlyField(source='listing.name')
    listing_image = serializers.ReadOnlyField(source='listing.image')

    class Meta:
        model = Booking
        fields = (
            'id',
            'booking_number',
            'customer',
            'customer_name',
            'customer_email',
            'customer_phone',
            'restaurant',
            'restaurant_name',
            'restaurant_address',
            'listing',
            'listing_name',
            'listing_image',
            'quantity',
            'unit_price',
            'total_amount',
            'status',
            'payment_status',
            'payment_method',
            'razorpay_order_id',
            'razorpay_payment_id',
            'payment_timestamp',
            'refund_id',
            'refund_status',
            'refund_amount',
            'refunded_at',
            'pickup_start',
            'pickup_end',
            'pickup_code',
            'notes',
            'cancellation_reason',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'booking_number',
            'customer',
            'restaurant',
            'listing',
            'unit_price',
            'total_amount',
            'razorpay_order_id',
            'razorpay_payment_id',
            'payment_timestamp',
            'refund_id',
            'refund_status',
            'refund_amount',
            'refunded_at',
            'pickup_start',
            'pickup_end',
            'pickup_code',
            'created_at',
            'updated_at',
        )



class CreateBookingSerializer(serializers.Serializer):
    """
    Validates and executes an atomic booking creation.
    Locks the FoodListing row using select_for_update() to prevent race conditions.
    """
    listing_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    payment_method = serializers.ChoiceField(
        choices=['UPI', 'CARD', 'CASH_ON_PICKUP'],
        default='UPI',
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_listing_id(self, value):
        try:
            listing = FoodListing.objects.get(pk=value)
        except FoodListing.DoesNotExist:
            raise serializers.ValidationError("Listing does not exist.")
        if listing.status != 'active':
            raise serializers.ValidationError("This food listing is no longer active.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        listing_id = validated_data['listing_id']
        requested_qty = validated_data['quantity']
        payment_method = validated_data.get('payment_method', 'UPI')
        notes = validated_data.get('notes', '')

        with transaction.atomic():
            # Lock the listing row to prevent simultaneous overselling
            listing = FoodListing.objects.select_for_update().get(pk=listing_id)

            if listing.status != 'active':
                raise serializers.ValidationError({"error": "Listing is no longer active."})

            if listing.quantity_available < requested_qty:
                raise serializers.ValidationError({
                    "error": f"Only {listing.quantity_available} item(s) remaining. Cannot book {requested_qty}."
                })

            # Calculate server-side total
            unit_price = listing.discounted_price
            total_amount = unit_price * requested_qty

            # Decrement inventory atomically
            listing.quantity_available -= requested_qty
            if listing.quantity_available == 0:
                listing.status = 'sold_out'
            listing.save(update_fields=['quantity_available', 'status', 'updated_at'])

            # 4-digit verification code
            import random
            pickup_code = f"{random.randint(1000, 9999)}"

            booking = Booking.objects.create(
                customer=user,
                restaurant=listing.restaurant,
                listing=listing,
                quantity=requested_qty,
                unit_price=unit_price,
                total_amount=total_amount,
                status='CONFIRMED',
                payment_status='PAYMENT_SUCCESS',
                payment_method=payment_method,
                pickup_start=listing.pickup_start,
                pickup_end=listing.pickup_end,
                pickup_code=pickup_code,
                notes=notes,
            )

            # Create notification for restaurant owner
            Notification.objects.create(
                user=listing.restaurant.owner,
                title="New Booking Received!",
                message=f"Order #{booking.booking_number}: {requested_qty}x {listing.name} booked by {user.get_full_name()}.",
                type='new_booking',
                related_booking=booking,
            )

            # Create confirmation notification for customer
            Notification.objects.create(
                user=user,
                title="Booking Confirmed!",
                message=f"Your order #{booking.booking_number} for {listing.name} is confirmed! Pickup: {listing.pickup_start} - {listing.pickup_end}.",
                type='status_update',
                related_booking=booking,
            )

            return booking


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'title', 'message', 'type', 'is_read', 'related_booking', 'created_at')
        read_only_fields = ('id', 'title', 'message', 'type', 'related_booking', 'created_at')
