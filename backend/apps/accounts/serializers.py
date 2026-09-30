"""
Serializers for user authentication and profile data.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


# ─── Registration ──────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    """
    Maps to the signup form fields:
      first_name, last_name, email, password, confirm_password, account_type, phone
    """
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    account_type = serializers.ChoiceField(
        choices=['customer', 'business', 'restaurant', 'admin'],
        default='customer',
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password', 'confirm_password', 'account_type', 'phone')

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                'An account with this email already exists.'
            )
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        account_type = validated_data.get('account_type', 'customer')
        # Normalize 'business' to 'restaurant'
        if account_type == 'business':
            account_type = 'restaurant'

        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data.get('phone', ''),
            account_type=account_type,
        )

        # If restaurant, auto-create their initial Restaurant profile
        if account_type == 'restaurant':
            from apps.marketplace.models import Restaurant
            Restaurant.objects.get_or_create(
                owner=user,
                defaults={
                    'business_name': f"{user.first_name}'s Food Partner",
                    'description': 'Local food partner fighting food waste.',
                    'category': 'Bakery & Cafe',
                    'address': 'Main Market',
                    'city': 'Chandigarh',
                    'phone': user.phone or '+91 98765 43210',
                    'banner_image': 'assets/images/hero_food.jpg',
                    'status': 'active',
                }
            )

        return user


# ─── JWT customisation ────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds user info to the token response payload."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Extra claims embedded in the JWT
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        token['email'] = user.email
        token['account_type'] = user.account_type
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Add user profile data alongside tokens
        data['user'] = UserSerializer(self.user).data
        return data


# ─── User profile ─────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    """Safe, read-only representation of the logged-in user."""

    full_name = serializers.SerializerMethodField()
    restaurant_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'phone',
            'account_type',
            'is_staff',
            'is_superuser',
            'restaurant_id',
            'date_joined',
            'last_login',
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_restaurant_id(self, obj):
        if hasattr(obj, 'restaurant_profile'):
            return obj.restaurant_profile.id
        return None

