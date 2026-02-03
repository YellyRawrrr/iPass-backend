from django.core.management.base import BaseCommand
from api1.email_service import cleanup_expired_temporary_passwords


class Command(BaseCommand):
    help = 'Clean up expired temporary passwords'

    def handle(self, *args, **options):
        count = cleanup_expired_temporary_passwords()
        self.stdout.write(
            self.style.SUCCESS(f'Successfully cleaned up {count} expired temporary passwords')
        )
