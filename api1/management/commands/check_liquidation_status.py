from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api1.models import Liquidation, TravelOrder


class Command(BaseCommand):
    help = 'Check liquidation status and deadlines for debugging'

    def add_arguments(self, parser):
        parser.add_argument(
            '--travel-order-number',
            type=str,
            help='Travel order number to check (optional)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all liquidations'
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        travel_order_number = options.get('travel_order_number')
        show_all = options.get('all', False)
        
        self.stdout.write(f"Today's date: {today.strftime('%Y-%m-%d')}\n")
        
        if travel_order_number:
            try:
                travel_order = TravelOrder.objects.get(travel_order_number=travel_order_number)
                self.stdout.write(f"Travel Order: {travel_order_number}")
                self.stdout.write(f"  Date Travel To: {travel_order.date_travel_to}")
                
                # Calculate expected deadline
                if travel_order.date_travel_to:
                    from datetime import datetime, time as dt_time
                    travel_end_datetime = timezone.make_aware(
                        datetime.combine(travel_order.date_travel_to, dt_time.max)
                    )
                    expected_deadline = travel_end_datetime + timedelta(days=90)
                    days_until_deadline = (expected_deadline.date() - today).days
                    
                    self.stdout.write(f"  Expected Deadline: {expected_deadline.date().strftime('%Y-%m-%d')}")
                    self.stdout.write(f"  Days until deadline: {days_until_deadline}")
                    self.stdout.write(f"  Notification window (28-32 days): {'✓' if 28 <= days_until_deadline <= 32 else '✗'}")
                
                try:
                    liquidation = Liquidation.objects.get(travel_order=travel_order)
                    self.stdout.write(f"\nLiquidation found:")
                    self.stdout.write(f"  ID: {liquidation.id}")
                    self.stdout.write(f"  Status: {liquidation.status}")
                    self.stdout.write(f"  Uploaded By: {liquidation.uploaded_by.email if liquidation.uploaded_by else 'None'}")
                    self.stdout.write(f"  Deadline Set: {'Yes' if liquidation.liquidation_deadline else 'No'}")
                    
                    if liquidation.liquidation_deadline:
                        deadline_date = liquidation.liquidation_deadline.date()
                        days_remaining = (deadline_date - today).days
                        
                        self.stdout.write(f"  Deadline Date: {deadline_date.strftime('%Y-%m-%d')}")
                        self.stdout.write(f"  Days Remaining: {days_remaining}")
                        self.stdout.write(f"  Within notification window (28-32 days): {'✓' if 28 <= days_remaining <= 32 else '✗'}")
                        self.stdout.write(f"  Status matches filter: {'✓' if liquidation.status in ['Pending', 'Under Pre-Audit', 'Under Final Audit'] else '✗'}")
                        
                        if liquidation.status in ['Pending', 'Under Pre-Audit', 'Under Final Audit']:
                            if 28 <= days_remaining <= 32:
                                self.stdout.write(self.style.SUCCESS("\n✓ This liquidation SHOULD trigger a notification!"))
                            else:
                                self.stdout.write(self.style.WARNING(f"\n⚠ Notification won't trigger yet. Days remaining: {days_remaining} (needs 28-32)"))
                        else:
                            self.stdout.write(self.style.ERROR(f"\n✗ Status '{liquidation.status}' is not in the allowed statuses for notification"))
                    else:
                        self.stdout.write(self.style.ERROR("\n✗ No deadline set! Deadline is only set when submitting liquidation components."))
                        self.stdout.write("  Components needed: After Travel Report, Certificate of Travel, or Certificate of Appearance")
                        
                        if travel_order.date_travel_to:
                            self.stdout.write(f"\n  To set deadline manually, run:")
                            self.stdout.write(f"  python manage.py test_liquidation_notification --travel-order-number {travel_order_number} --force")
                except Liquidation.DoesNotExist:
                    self.stdout.write(self.style.ERROR("\n✗ No liquidation found for this travel order"))
                    self.stdout.write("  Liquidation is created when you submit liquidation components (After Travel Report, Certificate of Travel, or Certificate of Appearance)")
                    
            except TravelOrder.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"✗ Travel order {travel_order_number} not found"))
        elif show_all:
            liquidations = Liquidation.objects.all().select_related('travel_order', 'uploaded_by')
            self.stdout.write(f"Found {liquidations.count()} liquidations:\n")
            
            for liq in liquidations:
                self.stdout.write(f"Travel Order: {liq.travel_order.travel_order_number}")
                self.stdout.write(f"  Date Travel To: {liq.travel_order.date_travel_to}")
                self.stdout.write(f"  Status: {liq.status}")
                self.stdout.write(f"  Deadline: {liq.liquidation_deadline.date().strftime('%Y-%m-%d') if liq.liquidation_deadline else 'Not set'}")
                
                if liq.liquidation_deadline:
                    days_remaining = (liq.liquidation_deadline.date() - today).days
                    self.stdout.write(f"  Days Remaining: {days_remaining}")
                    in_window = 28 <= days_remaining <= 32
                    in_status = liq.status in ['Pending', 'Under Pre-Audit', 'Under Final Audit']
                    
                    if in_window and in_status:
                        self.stdout.write(self.style.SUCCESS("  ✓ Should trigger notification"))
                    else:
                        if not in_window:
                            self.stdout.write(self.style.WARNING(f"  ⚠ Not in notification window (needs 28-32, has {days_remaining})"))
                        if not in_status:
                            self.stdout.write(self.style.WARNING(f"  ⚠ Status '{liq.status}' not in allowed statuses"))
                self.stdout.write("")
        else:
            self.stdout.write("Usage:")
            self.stdout.write("  python manage.py check_liquidation_status --travel-order-number <TO_NUMBER>")
            self.stdout.write("  python manage.py check_liquidation_status --all")

