"""
Custom User model for Too Fresh To Waste.

Extends AbstractBaseUser to support:
  - Email as the login identifier (not username)
  - Account types: customer / business / restaurant / admin
  - First & Last name (matching the signup form)
  - Email verification
  - Google OAuth identity
"""

import secrets
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager — email is the unique identifier instead of username."""

    def create_user(self, email, password=None, first_name='', last_name='', account_type='customer', **extra_fields):
        if not email:
            raise ValueError('Email address is required.')
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            account_type=account_type,
            **extra_fields,
        )
        if password:
            user.set_password(password)  # Hashes via Django's PBKDF2
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, first_name='Admin', last_name='User', **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('email_verified', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, first_name, last_name, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    TFTW custom user.

    Fields from signup form:
      - first_name
      - last_name
      - email       (login identifier)
      - password    (hashed by Django)
      - account_type (customer | business | restaurant | admin)

    Additional auth fields:
      - email_verified  (must verify before full access)
      - google_id       (for Google OAuth linking)
    """

    ACCOUNT_TYPE_CHOICES = [
        ('customer', 'Customer'),
        ('restaurant', 'Restaurant'),
        ('business', 'Business'),  # alias for restaurant
        ('admin', 'Admin'),
    ]

    # ── Core identity ──────────────────────────────────────────────────────────
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20, blank=True, default='')
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='customer',
    )

    # ── Email verification ─────────────────────────────────────────────────────
    email_verified = models.BooleanField(default=False, db_index=True)

    # ── Google OAuth ───────────────────────────────────────────────────────────
    google_id = models.CharField(max_length=128, blank=True, default='', db_index=True)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    updated_at = models.DateTimeField(auto_now=True)

    # ── Django internals ───────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)


    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}>'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_customer(self):
        return self.account_type == 'customer'

    @property
    def is_restaurant(self):
        return self.account_type in ('restaurant', 'business')

    @property
    def is_admin_user(self):
        return self.account_type == 'admin' or self.is_staff or self.is_superuser


# ─── Email Verification Token ─────────────────────────────────────────────────

def _default_verification_expiry():
    return timezone.now() + timedelta(hours=24)


class EmailVerificationToken(models.Model):
    """
    Cryptographically secure, single-use, expiring email verification token.
    One active token per user (old tokens are invalidated on new generation).
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verification_tokens',
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_verification_expiry)
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'email_verification_tokens'
        verbose_name = 'Email Verification Token'

    def __str__(self):
        return f'VerifToken({self.user.email}, used={self.used})'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.used and not self.is_expired

    @classmethod
    def create_for_user(cls, user):
        """Invalidate all previous tokens and create a fresh one."""
        cls.objects.filter(user=user, used=False).update(used=True)
        token_value = secrets.token_urlsafe(48)
        return cls.objects.create(user=user, token=token_value)


# ─── Password Reset Token ──────────────────────────────────────────────────────

def _default_reset_expiry():
    return timezone.now() + timedelta(hours=2)


class PasswordResetToken(models.Model):
    """
    Cryptographically secure, single-use, expiring password reset token.
    Expires in 2 hours. Single-use enforced via 'used' flag.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_reset_expiry)
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_tokens'
        verbose_name = 'Password Reset Token'

    def __str__(self):
        return f'ResetToken({self.user.email}, used={self.used})'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.used and not self.is_expired

    @classmethod
    def create_for_user(cls, user):
        """Invalidate all previous reset tokens and create a fresh one."""
        cls.objects.filter(user=user, used=False).update(used=True)
        token_value = secrets.token_urlsafe(48)
        return cls.objects.create(user=user, token=token_value)
