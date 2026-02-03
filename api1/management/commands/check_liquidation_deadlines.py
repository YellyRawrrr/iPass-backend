from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime, time as dt_time
from api1.models import Liquidation, Notification, TravelOrder
from api1.views import create_notification


class Command(BaseCommand):
    help = 'Check for liquidations approaching deadline and send notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days before deadline to send notification (default: 30)'
        )

    def handle(self, *args, **options):
        days_before = options['days']
        today = timezone.now().date()
        target_deadline_date = today + timedelta(days=days_before)
        
        # Allow a window of ±2 days to catch liquidations that should be notified
        # This ensures we don't miss notifications if the command runs slightly off schedule
        min_days = days_before - 2
        max_days = days_before + 2
        
        self.stdout.write(f"Checking for liquidations with deadlines in {days_before} days...")
        self.stdout.write(f"Target deadline date: {target_deadline_date}")
        self.stdout.write(f"Looking for liquidations with {min_days} to {max_days} days remaining\n")
        
        notifications_sent = 0
        
        # PART 1: Check existing liquidations with set deadlines
        self.stdout.write("Checking existing liquidations...")
        all_liquidations = Liquidation.objects.filter(
            liquidation_deadline__isnull=False,
            liquidation_deadline__date__gte=today,
            status__in=['Pending', 'Under Pre-Audit', 'Under Final Audit']
        )
        
        # Filter to find liquidations where deadline is approximately days_before away
        expiring_liquidations = []
        for liquidation in all_liquidations:
            days_remaining = (liquidation.liquidation_deadline.date() - today).days
            # Check if days remaining is within the target window (e.g., 28-32 days for 30-day notification)
            if min_days <= days_remaining <= max_days:
                expiring_liquidations.append({
                    'liquidation': liquidation,
                    'deadline': liquidation.liquidation_deadline.date(),
                    'days_remaining': days_remaining,
                    'user': liquidation.uploaded_by
                })
        
        self.stdout.write(f"  Found {len(expiring_liquidations)} existing liquidations with deadlines in {days_before} days (±2 days)")
        
        # PART 2: Check travel orders without liquidations yet (calculate expected deadline from date_travel_to)
        self.stdout.write("\nChecking travel orders without liquidations yet...")
        
        # Get all travel orders that are not rejected (exclude rejected statuses)
        # This includes any approved status or pending status
        rejected_statuses = [
            'Rejected by the CSC head.',
            'Rejected by the PO head',
            'Rejected by the TMSD chief',
            'Rejected by the AFSD Chief',
            'Rejected by the Regional Director'
        ]
        
        # Get all travel orders with date_travel_to that are not rejected
        approved_travel_orders = TravelOrder.objects.filter(
            date_travel_to__isnull=False
        ).exclude(
            status__in=rejected_statuses
        ).exclude(
            is_draft=True  # Exclude drafts
        )
        
        self.stdout.write(f"  Found {approved_travel_orders.count()} non-rejected travel orders with date_travel_to")
        
        # Debug: Show status breakdown
        status_counts = {}
        for to in approved_travel_orders:
            status = to.status
            status_counts[status] = status_counts.get(status, 0) + 1
        if status_counts:
            self.stdout.write(f"  Status breakdown: {status_counts}")
        
        # Get travel order IDs that already have liquidations
        travel_orders_with_liquidation = set(
            Liquidation.objects.filter(
                liquidation_deadline__isnull=False
            ).values_list('travel_order_id', flat=True)
        )
        
        self.stdout.write(f"  Travel orders with liquidations: {len(travel_orders_with_liquidation)}")
        
        # Filter to travel orders without liquidations
        travel_orders_without_liquidation = [
            to for to in approved_travel_orders 
            if to.id not in travel_orders_with_liquidation
        ]
        
        self.stdout.write(f"  Travel orders without liquidations: {len(travel_orders_without_liquidation)}")
        
        expiring_travel_orders = []
        for travel_order in travel_orders_without_liquidation:
            # Calculate expected deadline: date_travel_to + 90 days
            travel_end_datetime = timezone.make_aware(
                datetime.combine(travel_order.date_travel_to, dt_time.max)
            )
            expected_deadline = travel_end_datetime + timedelta(days=90)
            expected_deadline_date = expected_deadline.date()
            
            days_remaining = (expected_deadline_date - today).days
            
            # Debug output for specific travel order
            if travel_order.travel_order_number == "R1-2025-11-0006":
                self.stdout.write(f"\n  DEBUG - Travel Order: {travel_order.travel_order_number}")
                self.stdout.write(f"    Status: {travel_order.status}")
                self.stdout.write(f"    date_travel_to: {travel_order.date_travel_to}")
                self.stdout.write(f"    Expected deadline: {expected_deadline_date}")
                self.stdout.write(f"    Days remaining: {days_remaining}")
                self.stdout.write(f"    Window check: {min_days} <= {days_remaining} <= {max_days} = {min_days <= days_remaining <= max_days}")
            
            # Check if deadline hasn't passed yet
            if expected_deadline_date < today:
                continue
            
            # Check if days remaining is within the target window
            if min_days <= days_remaining <= max_days:
                expiring_travel_orders.append({
                    'travel_order': travel_order,
                    'deadline': expected_deadline_date,
                    'days_remaining': days_remaining,
                    'user': travel_order.prepared_by  # Notify the employee who prepared the travel order
                })
        
        self.stdout.write(f"  Found {len(expiring_travel_orders)} travel orders with expected deadlines in {days_before} days (±2 days)")
        
        # Combine both lists
        all_expiring_items = expiring_liquidations + expiring_travel_orders
        
        self.stdout.write(f"\nTotal items needing notification: {len(all_expiring_items)}")
        
        # Send notifications
        for item in all_expiring_items:
            travel_order = item.get('travel_order') or item['liquidation'].travel_order
            deadline = item['deadline']
            days_remaining = item['days_remaining']
            user = item['user']
            
            # Check if notification was already sent for this travel order today
            existing_notification = Notification.objects.filter(
                travel_order=travel_order,
                notification_type='liquidation_deadline_approaching',
                created_at__date=today
            ).exists()
            
            if existing_notification:
                self.stdout.write(f"  Notification already sent today for travel order {travel_order.travel_order_number}")
                continue
            
            # Send notification to the user
            if user:
                try:
                    deadline_str = deadline.strftime('%B %d, %Y')
                    title = f"Liquidation Deadline Approaching - {days_remaining} days remaining"
                    message = f"Your liquidation for travel order {travel_order.travel_order_number} has a deadline in {days_remaining} days. Please complete and submit your liquidation before {deadline_str} to avoid expiration."
                    
                    # Get liquidation object if it exists, otherwise pass None
                    liquidation = item.get('liquidation')
                    
                    # Create notification
                    create_notification(
                        user=user,
                        travel_order=travel_order,
                        notification_type='liquidation_deadline_approaching',
                        title=title,
                        message=message,
                        liquidation=liquidation  # Pass liquidation if exists, None otherwise
                    )
                    
                    self.stdout.write(f"  ✓ Notification sent to {user.email} for travel order {travel_order.travel_order_number} (deadline: {deadline.strftime('%Y-%m-%d')}, {days_remaining} days remaining)")
                    notifications_sent += 1
                    
                except Exception as e:
                    self.stdout.write(f"  ✗ Error sending notification for travel order {travel_order.travel_order_number}: {str(e)}")
            else:
                self.stdout.write(f"  ✗ No user found for travel order {travel_order.travel_order_number}")
        
        self.stdout.write(f"\nSuccessfully sent {notifications_sent} notifications")
        self.stdout.write("Liquidation deadline check completed")
