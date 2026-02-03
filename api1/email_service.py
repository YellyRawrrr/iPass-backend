import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import CustomUser, TemporaryPassword


def generate_temporary_password():
    """Generate a random 12-character temporary password"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(characters, k=12))


def send_user_creation_email(user, temporary_password):
    """Send email to new user with their credentials and temporary password"""
    try:
        subject = "Account Credentials for the IPass:Travel Order System"
        
        message = f"""
Dear {user.first_name or user.email},

Greetings!

We are pleased to inform you that your account for the IPass:Travel Order System has been successfully created. Please find your login details below:

Email: {user.email}
Temporary Password: {temporary_password}

Important Reminders:
- The temporary password is valid for 10 minutes only.
- You are required to change your password immediately upon your first login to ensure the security of your account.


Login Instructions:
1. Access the IPass:Travel Order System.
2. Enter your registered email address and the temporary password provided above.
3. You will be prompted to create a new password upon logging in.
4. Please ensure that your new password is strong and confidential.

Should you have any concerns or require assistance, you may contact your system administrator for support.

Thank you and welcome to the IPass:Travel Order System.

Best regards,
National Commisions on Indigenous Peoples Regional Office 1-ICT
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending user creation email to {user.email}: {e}")
        return False


def send_notification_email(user, travel_order, notification_type, title, message, liquidation=None):
    """Send email notification to user"""
    try:
        # Get user's full name
        user_name = user.get_full_name() or user.email
        
        # Email subject
        subject = f"NCIP Travel Management - {title}"
        
        # Create email body based on notification type
        email_body = create_notification_email_body(
            user_name, travel_order, notification_type, title, message, liquidation=liquidation
        )
        
        # Send email
        send_mail(
            subject,
            email_body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending notification email to {user.email}: {e}")
        return False


def create_notification_email_body(user_name, travel_order, notification_type, title, message, liquidation=None):
    """Create formatted email body for notifications"""
    
    # Base email template
    base_template = f"""
Dear {user_name},

{message}

Travel Request Details:
- Destination: {travel_order.destination}
- Date of Official Travel(From): {travel_order.date_travel_from}
- Date of Official Travel(To): {travel_order.date_travel_to}

"""
    
    # Add action-specific content
    if notification_type == 'new_approval_needed':
        action_content = """
Action Required: Please log in to the NCIP Travel Management System to review and approve this travel request.
"""
    elif notification_type in ['travel_approved', 'travel_final_approved']:
        action_content = """
Status: Your travel request has been approved. You may now proceed with your travel plans.
"""
    elif notification_type in ['travel_rejected', 'liquidation_rejected', 'component_rejected']:
        action_content = """
Action Required: Please review the rejection details and take necessary action. You may resubmit your request if needed.
"""
    elif notification_type == 'travel_rejected_by_next_approver':
        action_content = """
Status: A travel request you previously approved has been rejected by a later approver. Please review the details.
"""
    elif notification_type in ['liquidation_approved', 'component_approved']:
        # Add final amount information if liquidation is provided
        amount_info = ""
        if liquidation:
            try:
                # Calculate original grand total from itinerary
                from .models import Itinerary
                original_total = 0
                itineraries = Itinerary.objects.filter(travel_order=travel_order)
                for itinerary in itineraries:
                    if itinerary.total_amount:
                        original_total += float(itinerary.total_amount)
                original_total = round(original_total, 2)
                
                # Get final amount (if modified by accountant)
                final_amount = liquidation.final_amount
                
                if final_amount and float(final_amount) != original_total:
                    amount_info = f"""
Amount Information:
- Original Amount (from form): ₱{original_total:,.2f}
- Final Amount (as approved): ₱{float(final_amount):,.2f}
- Amount changed from ₱{original_total:,.2f} to ₱{float(final_amount):,.2f}

"""
                else:
                    amount_info = f"""
Amount Information:
- Final Amount: ₱{original_total:,.2f}

"""
            except Exception as e:
                print(f"Error calculating amounts for email: {e}")
        
        action_content = f"""
Status: Your liquidation has been approved and is ready for claim.
{amount_info}
Please proceed to claim your approved liquidation amount.
"""
    elif notification_type == 'liquidation_submitted':
        action_content = """
Status: Your liquidation has been submitted successfully and is under review.
"""
    elif notification_type == 'liquidation_needs_review':
        action_content = """
Action Required: Please log in to review the submitted liquidation documents.
"""
    elif notification_type == 'liquidation_deadline_approaching':
        # Extract deadline date from message if available
        deadline_info = ""
        if liquidation and liquidation.liquidation_deadline:
            deadline_date = liquidation.liquidation_deadline.strftime('%B %d, %Y')
            days_remaining = (liquidation.liquidation_deadline.date() - timezone.now().date()).days
            deadline_info = f"""
Deadline Information:
- Deadline Date: {deadline_date}
- Days Remaining: {days_remaining} day{'s' if days_remaining != 1 else ''}

"""
        
        action_content = f"""
{deadline_info}Action Required: Please complete and submit your liquidation documents before the deadline to avoid expiration.

If you have already submitted your liquidation, you can disregard this notification.
"""
    else:
        action_content = """
Please log in to the NCIP Travel Management System for more details.
"""
    
    return base_template + action_content


def send_bulk_notification_emails(users, travel_order, notification_type, title, message):
    """Send email notifications to multiple users"""
    success_count = 0
    for user in users:
        if send_notification_email(user, travel_order, notification_type, title, message):
            success_count += 1
    return success_count


def cleanup_expired_temporary_passwords():
    """Clean up expired temporary passwords"""
    from .models import TemporaryPassword
    expired_passwords = TemporaryPassword.objects.filter(expires_at__lt=timezone.now())
    count = expired_passwords.count()
    expired_passwords.delete()
    return count