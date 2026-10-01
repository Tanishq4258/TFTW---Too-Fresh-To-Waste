"""
Management command: promote_to_admin

Usage:
  python manage.py promote_to_admin <email>
  python manage.py promote_to_admin <email> --demote

Securely promotes (or demotes) a user to admin role.
This is the ONLY way to create admin accounts - not via the signup form.

Examples:
  python manage.py promote_to_admin tanishq@example.com
  python manage.py promote_to_admin tanishq@example.com --demote
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Promote or demote a user to/from admin role.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email address of the user to promote/demote')
        parser.add_argument(
            '--demote',
            action='store_true',
            help='Demote the user from admin role back to customer',
        )

    def handle(self, *args, **options):
        email = options['email'].lower().strip()
        demote = options['demote']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'No user found with email: {email}')

        if demote:
            user.account_type = 'customer'
            user.is_staff = False
            user.save(update_fields=['account_type', 'is_staff'])
            self.stdout.write(self.style.SUCCESS(
                f'[OK] User {email} has been demoted to customer role.'
            ))
        else:
            user.account_type = 'admin'
            user.is_staff = True
            user.email_verified = True  # Admins are always verified
            user.save(update_fields=['account_type', 'is_staff', 'email_verified'])
            self.stdout.write(self.style.SUCCESS(
                f'[OK] User {email} has been promoted to ADMIN role with staff access.'
            ))
            self.stdout.write(self.style.WARNING(
                '  They can now access /admin/ and the admin dashboard.'
            ))
