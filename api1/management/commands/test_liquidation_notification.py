from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime, time as dt_time
from api1.models import Liquidation, TravelOrder


class Command(BaseCommand):
    help = 'Set liquidation deadline to 30 days from today for testing notification'

    def add_arguments(self, parser):
        parser.add_argument(
            '--travel-order-number',
            type=str,
            help='Travel order number to update (optional, if not provided will update all liquidations)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days from today to set the deadline (default: 30)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if liquidation already has a deadline'
        )

    def handle(self, *args, **options):
        days = options['days']
        travel_order_number = options.get('travel_order_number')
        today = timezone.now().date()
        target_deadline = timezone.make_aware(
            datetime.combine(today + timedelta(days=days), datetime.min.time())
        )
        
        self.stdout.write(f"Setting liquidation deadlines to {days} days from today ({target_deadline.strftime('%Y-%m-%d')})")
        
        if travel_order_number:
            force = options.get('force', False)
            try:
                travel_order = TravelOrder.objects.get(travel_order_number=travel_order_number)
                try:
                    liquidation = Liquidation.objects.get(travel_order=travel_order)
                    old_deadline = liquidation.liquidation_deadline
                    
                    if old_deadline and not force:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⚠ Liquidation already has a deadline ({old_deadline.strftime('%Y-%m-%d')}). "
                                f"Use --force to override it."
                            )
                        )
                        return
                    
                    liquidation.liquidation_deadline = target_deadline
                    liquidation.save()
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Updated liquidation for travel order {travel_order_number}\n"
                            f"  Old deadline: {old_deadline.strftime('%Y-%m-%d %H:%M:%S') if old_deadline else 'None'}\n"
                            f"  New deadline: {liquidation.liquidation_deadline.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    )
                except Liquidation.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠ No liquidation found for travel order {travel_order_number}\n"
                            f"  Note: The check_liquidation_deadlines command will still check this travel order\n"
                            f"  and calculate the expected deadline from date_travel_to (date_travel_to + 90 days).\n"
                            f"  You can run the check command directly without needing to create a liquidation.\n\n"
                            f"  To test with this travel order, run:\n"
                            f"  python manage.py check_liquidation_deadlines"
                        )
                    )
                    self.stdout.write(f"\n  Travel order details:")
                    self.stdout.write(f"    Date Travel To: {travel_order.date_travel_to}")
                    if travel_order.date_travel_to:
                        from datetime import datetime, time as dt_time
                        travel_end_datetime = timezone.make_aware(
                            datetime.combine(travel_order.date_travel_to, dt_time.max)
                        )
                        expected_deadline = travel_end_datetime + timedelta(days=90)
                        days_until_deadline = (expected_deadline.date() - today).days
                        self.stdout.write(f"    Expected Deadline: {expected_deadline.date().strftime('%Y-%m-%d')}")
                        self.stdout.write(f"    Days until deadline: {days_until_deadline}")
                        self.stdout.write(f"    Notification window (28-32 days): {'✓ Will trigger' if 28 <= days_until_deadline <= 32 else '✗ Too far/close'}")
            except TravelOrder.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"✗ Travel order {travel_order_number} not found")
                )
        else:
            # Update liquidations
            force = options.get('force', False)
            if force:
                liquidations = Liquidation.objects.all()
                self.stdout.write("Updating ALL liquidations (--force flag used)...")
            else:
                liquidations = Liquidation.objects.filter(liquidation_deadline__isnull=True)
                self.stdout.write("Updating liquidations without deadlines...")
            
            count = liquidations.count()
            
            if count == 0:
                self.stdout.write("No liquidations found. Use --travel-order-number to update a specific one.")
                return
            
            self.stdout.write(f"Found {count} liquidation(s). Updating...")
            
            updated = 0
            for liquidation in liquidations:
                old_deadline = liquidation.liquidation_deadline
                liquidation.liquidation_deadline = target_deadline
                liquidation.save()
                updated += 1
                old_str = old_deadline.strftime('%Y-%m-%d') if old_deadline else 'None'
                self.stdout.write(
                    f"  ✓ Updated liquidation for travel order {liquidation.travel_order.travel_order_number} "
                    f"(old: {old_str}, new: {target_deadline.strftime('%Y-%m-%d')})"
                )
            
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Successfully updated {updated} liquidation(s)")
            )
        
        self.stdout.write(f"\nNow run: python manage.py check_liquidation_deadlines to trigger the notification")

