from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, EmailVerificationToken, PasswordResetToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin config for the custom User model."""

    ordering = ('-date_joined',)
    list_display = ('email', 'first_name', 'last_name', 'account_type', 'email_verified', 'is_staff', 'date_joined')
    list_filter = ('account_type', 'email_verified', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone', 'account_type')}),
        (_('Verification'), {'fields': ('email_verified', 'google_id')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'updated_at')}),
    )
    readonly_fields = ('date_joined', 'last_login', 'updated_at', 'google_id')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'account_type', 'password1', 'password2'),
        }),
    )

    # email is the username field
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used', 'is_expired')
    list_filter = ('used',)
    search_fields = ('user__email',)
    readonly_fields = ('token', 'created_at', 'expires_at')

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expired?'


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used', 'is_expired')
    list_filter = ('used',)
    search_fields = ('user__email',)
    readonly_fields = ('token', 'created_at', 'expires_at')

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expired?'
