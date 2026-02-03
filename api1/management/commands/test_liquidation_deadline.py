from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime, time as dt_time
from api1.models import TravelOrder


class Command(BaseCommand):
    help = 'Adjust date_travel_to to test liquidation deadline notification'

    def add_arguments(self, parser):
        parser.add_argument(
            '--travel-order-number',
            type=str,
            required=True,
            help='Travel order number to adjust'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days from today for the deadline (default: 30)'
        )
        parser.add_argument(
            '--show-only',
            action='store_true',
            help='Only show what date_travel_to should be, without updating'
        )

    def handle(self, *args, **options):
        travel_order_number = options.get('travel_order_number')
        days = options['days']
        show_only = options.get('show_only', False)
        today = timezone.now().date()
        
        try:
            travel_order = TravelOrder.objects.get(travel_order_number=travel_order_number)
            
            # Calculate what date_travel_to should be
            # Deadline = date_travel_to + 90 days
            # So: date_travel_to = (today + days) - 90 days
            target_deadline = today + timedelta(days=days)
            required_date_travel_to = target_deadline - timedelta(days=90)
            
            self.stdout.write(f"Travel Order: {travel_order_number}")
            self.stdout.write(f"Today's date: {today.strftime('%Y-%m-%d')}")
            self.stdout.write(f"Target deadline: {target_deadline.strftime('%Y-%m-%d')} ({days} days from today)")
            self.stdout.write(f"Current date_travel_to: {travel_order.date_travel_to.strftime('%Y-%m-%d') if travel_order.date_travel_to else 'Not set'}")
            self.stdout.write(f"Required date_travel_to: {required_date_travel_to.strftime('%Y-%m-%d')} (to trigger notification in {days} days)")
            
            if travel_order.date_travel_to:
                current_deadline = travel_order.date_travel_to + timedelta(days=90)
                days_until_current_deadline = (current_deadline - today).days
                self.stdout.write(f"Current expected deadline: {current_deadline.strftime('%Y-%m-%d')} ({days_until_current_deadline} days away)")
                self.stdout.write(f"Notification window: {'✓ Will trigger' if 28 <= days_until_current_deadline <= 32 else '✗ Too far/close'}")
            
            if show_only:
                self.stdout.write(self.style.WARNING("\n⚠ Show-only mode. No changes made."))
                self.stdout.write(f"\nTo update date_travel_to, run without --show-only flag:")
                self.stdout.write(f"  python manage.py test_liquidation_deadline --travel-order-number {travel_order_number} --days {days}")
            else:
                # Update date_travel_to
                old_date = travel_order.date_travel_to
                travel_order.date_travel_to = required_date_travel_to
                travel_order.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✓ Updated date_travel_to from {old_date.strftime('%Y-%m-%d') if old_date else 'None'} "
                        f"to {required_date_travel_to.strftime('%Y-%m-%d')}"
                    )
                )
                self.stdout.write(f"\nNow run: python manage.py check_liquidation_deadlines")
                self.stdout.write(f"Expected deadline will be: {target_deadline.strftime('%Y-%m-%d')} ({days} days from today)")
                
        except TravelOrder.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"✗ Travel order {travel_order_number} not found")
            )

