"""
Management command to seed realistic TFTW data:
  - Admin account
  - Restaurant partners & profiles
  - Surplus food listings
  - Test customer account
  - Sample bookings
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.marketplace.models import Restaurant, FoodListing, Booking, Notification

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds initial TFTW database records for dev and testing."

    def handle(self, *args, **options):
        self.stdout.write("Seeding TFTW database...")

        # 1. Admin account
        admin_user, created = User.objects.get_or_create(
            email='admin@tftw.dev',
            defaults={
                'first_name': 'TFTW',
                'last_name': 'Administrator',
                'account_type': 'admin',
                'phone': '+91 99999 00001',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('AdminPass123!')
        admin_user.account_type = 'admin'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()
        self.stdout.write(f"Admin: admin@tftw.dev / AdminPass123! (created={created})")

        # 2. Test Customer
        customer_user, _ = User.objects.get_or_create(
            email='customer@tftw.dev',
            defaults={
                'first_name': 'Aarav',
                'last_name': 'Sharma',
                'account_type': 'customer',
                'phone': '+91 98888 12345',
            }
        )
        customer_user.set_password('Customer123!')
        customer_user.save()
        self.stdout.write("Customer: customer@tftw.dev / Customer123!")

        # 3. Restaurant Partners
        partners_data = [
            {
                'email': 'morningoven@tftw.dev',
                'first_name': 'Priya',
                'last_name': 'Sharma',
                'business_name': 'The Morning Oven',
                'description': 'Artisan European bakery known for sourdough, butter croissants, and fresh Danish pastries.',
                'category': 'Bakery & Patisserie',
                'address': 'SCO 45, Sector 17',
                'city': 'Chandigarh',
                'phone': '+91 98140 11223',
                'banner_image': 'assets/images/bakery_box.jpg',
            },
            {
                'email': 'brewandbite@tftw.dev',
                'first_name': 'Rohan',
                'last_name': 'Verma',
                'business_name': 'Brew & Bite Café',
                'description': 'Specialty coffee bar and wholesome bistro serving gourmet sandwiches, wraps, and seasonal salads.',
                'category': 'Cafe & Bistro',
                'address': 'SCO 112, Sector 35-C',
                'city': 'Chandigarh',
                'phone': '+91 98720 33445',
                'banner_image': 'assets/images/cafe_box.jpg',
            },
            {
                'email': 'sweetspot@tftw.dev',
                'first_name': 'Ananya',
                'last_name': 'Mehta',
                'business_name': 'Sweet Spot Patisserie',
                'description': 'Boutique French dessert shop crafting delicate macarons, chocolate tarts, and velvet brownies.',
                'category': 'Desserts & Sweets',
                'address': 'Booth 89, Sector 22',
                'city': 'Chandigarh',
                'phone': '+91 98880 55667',
                'banner_image': 'assets/images/dessert_box.jpg',
            },
        ]

        restaurants = {}
        for p in partners_data:
            user, _ = User.objects.get_or_create(
                email=p['email'],
                defaults={
                    'first_name': p['first_name'],
                    'last_name': p['last_name'],
                    'account_type': 'restaurant',
                    'phone': p['phone'],
                }
            )
            user.set_password('Partner123!')
            user.account_type = 'restaurant'
            user.save()

            rest, _ = Restaurant.objects.get_or_create(
                owner=user,
                defaults={
                    'business_name': p['business_name'],
                    'description': p['description'],
                    'category': p['category'],
                    'address': p['address'],
                    'city': p['city'],
                    'phone': p['phone'],
                    'banner_image': p['banner_image'],
                    'status': 'active',
                }
            )
            restaurants[p['business_name']] = rest
            self.stdout.write(f"Restaurant partner: {p['email']} / Partner123! ({p['business_name']})")

        # 4. Food Listings
        listings_data = [
            {
                'restaurant': restaurants['The Morning Oven'],
                'name': 'Bakery Surprise Box',
                'description': 'Assortment of freshly baked croissants, pain au chocolat, Danish swirls and breakfast muffins baked today.',
                'category': 'bakery',
                'image': 'assets/images/bakery_box.jpg',
                'original_price': Decimal('399.00'),
                'discounted_price': Decimal('149.00'),
                'quantity': 5,
                'quantity_available': 4,
                'pickup_start': '7:30 PM',
                'pickup_end': '9:00 PM',
                'pickup_instructions': 'Visit the main bakery counter. Mention your Too Fresh To Waste reservation ID.',
                'status': 'active',
            },
            {
                'restaurant': restaurants['Brew & Bite Café'],
                'name': 'Evening Café Box',
                'description': 'Delicious grilled sourdough sandwiches, fresh pesto focaccia slices, and house dips from today’s lunch run.',
                'category': 'meals',
                'image': 'assets/images/cafe_box.jpg',
                'original_price': Decimal('450.00'),
                'discounted_price': Decimal('199.00'),
                'quantity': 4,
                'quantity_available': 3,
                'pickup_start': '6:00 PM',
                'pickup_end': '8:00 PM',
                'pickup_instructions': 'Pick up directly at the barista counter. Freshly packed kraft box.',
                'status': 'active',
            },
            {
                'restaurant': restaurants['Sweet Spot Patisserie'],
                'name': 'Fresh Dessert Box',
                'description': 'Parisian macarons (4 pcs), dark chocolate fudge brownie slice, and lemon curd fruit tartlet.',
                'category': 'desserts',
                'image': 'assets/images/dessert_box.jpg',
                'original_price': Decimal('300.00'),
                'discounted_price': Decimal('129.00'),
                'quantity': 3,
                'quantity_available': 2,
                'pickup_start': '8:00 PM',
                'pickup_end': '9:30 PM',
                'pickup_instructions': 'Show booking code at the dessert display counter.',
                'status': 'active',
            },
            {
                'restaurant': restaurants['The Morning Oven'],
                'name': 'Artisan Sourdough & Croissant Loaf',
                'description': 'Whole rustic wild sourdough boule and a 2-pack of golden butter croissants.',
                'category': 'bakery',
                'image': 'assets/images/hero_food.jpg',
                'original_price': Decimal('280.00'),
                'discounted_price': Decimal('99.00'),
                'quantity': 6,
                'quantity_available': 6,
                'pickup_start': '7:00 PM',
                'pickup_end': '8:30 PM',
                'pickup_instructions': 'Collection at side pickup window.',
                'status': 'active',
            },
        ]

        created_listings = []
        for l_data in listings_data:
            listing, _ = FoodListing.objects.get_or_create(
                restaurant=l_data['restaurant'],
                name=l_data['name'],
                defaults=l_data,
            )
            created_listings.append(listing)

        # 5. Create 1 sample booking for customer
        if created_listings:
            first_listing = created_listings[0]
            booking, _ = Booking.objects.get_or_create(
                booking_number='TFTW-782104',
                defaults={
                    'customer': customer_user,
                    'restaurant': first_listing.restaurant,
                    'listing': first_listing,
                    'quantity': 1,
                    'unit_price': first_listing.discounted_price,
                    'total_amount': first_listing.discounted_price,
                    'status': 'CONFIRMED',
                    'payment_status': 'PAYMENT_SUCCESS',
                    'payment_method': 'UPI',
                    'pickup_start': first_listing.pickup_start,
                    'pickup_end': first_listing.pickup_end,
                    'pickup_code': '5812',
                }
            )
            Notification.objects.get_or_create(
                user=first_listing.restaurant.owner,
                related_booking=booking,
                defaults={
                    'title': 'New Booking Received!',
                    'message': f"Order #{booking.booking_number}: 1x {first_listing.name} reserved by {customer_user.get_full_name()}.",
                    'type': 'new_booking',
                }
            )

        self.stdout.write(self.style.SUCCESS("TFTW database successfully seeded with live realistic data!"))
