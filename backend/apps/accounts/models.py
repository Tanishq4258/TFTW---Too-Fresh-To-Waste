"""
Custom User model for Too Fresh To Waste.

Extends AbstractBaseUser to support:
  - Email as the login identifier (not username)
  - Account types: customer / business
  - First & Last name (matching the signup form)

Expandable later for: profile photo, phone, address, business details, etc.
"""

from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)


class UserManager(BaseUserManager):
    """Custom manager — email is the unique identifier instead of username."""

    def create_user(self, email, password, first_name, last_name, account_type='customer', **extra_fields):
        if not email:
            raise ValueError('Email address is required.')
        if not password:
            raise ValueError('Password is required.')
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            account_type=account_type,
            **extra_fields,
        )
        user.set_password(password)  # Hashes via Django's PBKDF2
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, first_name='Admin', last_name='User', **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

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
      - account_type (customer | business)
    """

    ACCOUNT_TYPE_CHOICES = [
        ('customer', 'Customer'),
        ('business', 'Business'),
    ]

    # ── Core identity ──────────────────────────────────────────────────────────
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='customer',
    )

    # ── Django internals ───────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # ── Future-ready fields (nullable for now) ─────────────────────────────────
    # phone         = models.CharField(max_length=20, blank=True)
    # profile_photo = models.ImageField(upload_to='avatars/', null=True, blank=True)

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
