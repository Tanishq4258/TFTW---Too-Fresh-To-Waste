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
    Maps exactly to the signup form fields:
      firstName, lastName, email, password, confirmPassword, account_type
    """
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    account_type = serializers.ChoiceField(
        choices=['customer', 'business'],
        default='customer',
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password', 'confirm_password', 'account_type')

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
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            account_type=validated_data.get('account_type', 'customer'),
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

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'account_type',
            'date_joined',
            'last_login',
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()
