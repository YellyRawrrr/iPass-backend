# models.py
# Database models for the Travel Order Management System
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import AbstractUser

class EmployeePosition(models.Model):
    """Employee position/role definitions"""
    position_name = models.CharField(max_length=100)
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return self.position_name

# --- USER MANAGEMENT ---
# User level hierarchy for the approval system
USER_LEVEL_CHOICES = [
    ('employee', 'Employee'),
    ('head', 'Head'),
    ('admin', 'Admin'),
    ('director', 'Director'),
    ('bookkeeper', 'Bookkeeper'),
    ('accountant', 'Accountant'),
]

EMPLOYEE_TYPE_CHOICES = [
    ('urdaneta_csc', 'Urdaneta CSC'),
    ('sison_csc', 'Sison CSC'),
    ('pugo_csc', 'Pugo CSC'),
    ('sudipen_csc', 'Sudipen CSC'),
    ('tagudin_csc', 'Tagudin CSC'),
    ('banayoyo_csc', 'Banayoyo CSC'),
    ('dingras_csc', 'Dingras CSC'),
    ('pangasinan_po', 'Pangasinan PO'),
    ('ilocossur_po', 'Ilocos Sur PO'),
    ('ilocosnorte_po', 'Ilocos Norte PO'),
    ('launion_po', 'La Union PO'),
    ('tmsd', 'TMSD'),
    ('afsd', 'AFSD'),
    ('regional', 'Regional')
]


class CustomUser(AbstractUser):
    """Extended user model with additional fields for the travel system"""
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    # Remove username field and override email field to make it unique
    username = None
    email = models.EmailField(unique=True, verbose_name='email address')
    
    prefix = models.CharField(max_length=10, blank=True, null=True)
    user_level = models.CharField(max_length=20, choices=USER_LEVEL_CHOICES)
    employee_type = models.CharField(max_length=30, choices=EMPLOYEE_TYPE_CHOICES, blank=True, null=True)
    employee_position = models.ForeignKey(EmployeePosition, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    must_change_password = models.BooleanField(default=False, help_text="User must change password on next login")
    
    @property
    def full_name(self):
        """Returns formatted full name with prefix"""
        prefix_str = f"{self.prefix} " if self.prefix else ""
        return f"{prefix_str}{self.first_name} {self.last_name}"
    
# --- FUND MANAGEMENT ---
class Fund(models.Model):
    """Funding sources for travel orders"""
    source_of_fund = models.CharField(max_length=50)
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return self.source_of_fund

# --- PURPOSE MANAGEMENT ---
class Purpose(models.Model):
    """Purpose definitions for travel orders"""
    purpose_name = models.CharField(max_length=255)
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return self.purpose_name

# --- SPECIFIC ROLE MANAGEMENT ---
class SpecificRole(models.Model):
    """Specific role definitions for travel orders"""
    role_name = models.CharField(max_length=255)
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return self.role_name


# --- TRAVEL ORDER  ---
class TravelOrder(models.Model):
    """Main travel order model with multi-level approval workflow"""
    # Approval status choices for the hierarchical approval system
    STATUS_CHOICES = [
        ('Travel request is placed', 'Travel request is placed'),
        ('Approved by the CSC head', 'Approved by the CSC head'),
        ('Rejected by the CSC head.', 'Rejected by the CSC head'),
        ('Approved by the PO head', 'Approved by the PO head'),
        ('Rejected by the PO head', 'Rejected by the PO head'),
        ('Approved by the TMSD chief', 'Approved by the TMSD chief'),
        ('Rejected by the TMSD chief', 'Rejected by the TMSD chief'),
        ('Approved by the AFSD chief', 'Approved by the AFSD chief'),
        ('Rejected by the AFSD Chief', 'Rejected by the AFSD Chief'),
        ('Approved by the Regional Director', 'Approved by the Regional Director'),
        ('Rejected by the Regional Director', 'Rejected by the Regional Director'),
    ]

    MODE_OF_FILING = [
        ('IMMEDIATE','IMMEDIATE'),
        ('NOT_IMMEDIATE','NOT_IMMEDIATE')
    ]

    FUND_CLUSTER = [
        ('01_RF','01_RF'),
        ('07_TF','07_TF')
    ]



    employees = models.ManyToManyField(CustomUser, related_name='travel_orders')
    travel_order_number = models.CharField(max_length=50, blank=True, null=True, unique=True)
    #new
    mode_of_filing = models.CharField(max_length=20, choices=MODE_OF_FILING, blank=True)
    evidence = models.FileField(null=True, blank=True, upload_to='evidence/',  validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf'])])
    date_of_filing = models.DateField(auto_now_add=True)
    
    fund_cluster = models.CharField(max_length=10, choices=FUND_CLUSTER, blank=True)
    number_of_employees = models.IntegerField(default=0)
    
    destination = models.CharField(max_length=255, blank=True, null=True)
    distance = models.IntegerField(default=1, help_text="Distance in kilometers")
    
    purpose = models.ForeignKey('Purpose', on_delete=models.SET_NULL, null=True, blank=True, related_name='travel_orders')
    specific_role = models.ForeignKey('SpecificRole', on_delete=models.SET_NULL, null=True, blank=True, related_name='travel_orders')
    fund = models.ForeignKey(Fund, on_delete=models.SET_NULL, null=True, blank=True)
    date_travel_from = models.DateField(null=True, blank=True)
    date_travel_to = models.DateField(null=True, blank=True)
    official_station = models.CharField(max_length=100, blank=True, null=True)

    #validation
    prepared_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='prepared_travel_order')
    employee_position = models.ForeignKey(EmployeePosition, on_delete=models.SET_NULL, null=True, blank=True, related_name='travel_orders')
    prepared_by_position_name = models.CharField(max_length=255, blank=True, null=True, help_text="Position name of the person who prepared the travel order")
    prepared_by_user_type = models.CharField(max_length=100, blank=True, null=True, help_text="Type of user who prepared the travel order")
    approver_selection = models.JSONField(default=dict, blank=True, help_text="Selected approvers for each level in the approval chain")
    approver_position = models.JSONField(default=dict, blank=True, help_text="Positions for each approver level in the approval chain")
    
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Travel request is placed')
    approval_stage = models.IntegerField(default=0)
    current_approver = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='approving_orders')

    rejection_comment = models.TextField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(CustomUser,null=True, blank=True, on_delete=models.SET_NULL, related_name='rejected_orders')
    is_resubmitted = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False, help_text='True if this is a draft, False if submitted for approval')

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"TravelOrder to {self.destination} by {', '.join([e.full_name for e in self.employees.all()])}"

    
class Transportation(models.Model):
    means_of_transportation = models.CharField(max_length=50)
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return self.means_of_transportation

class Itinerary(models.Model):
    DESTINATION_CLUSTER_CHOICES = [
        ('Cluster I', 'Cluster I'),
        ('Cluster II', 'Cluster II'),
        ('Cluster III', 'Cluster III'),
    ]
    
    travel_order = models.ForeignKey(TravelOrder, related_name='itinerary', on_delete=models.CASCADE)
    transportation = models.ForeignKey(Transportation, on_delete=models.SET_NULL, null=True, blank=True)
    itinerary_date = models.DateField(null=True, blank=True)
    departure_time = models.TimeField(null=True, blank=True)
    arrival_time = models.TimeField(null=True, blank=True)
    destination_cluster = models.CharField(max_length=20, choices=DESTINATION_CLUSTER_CHOICES, blank=True, null=True)
    destination = models.CharField(max_length=255, blank=True, null=True)
    transportation_allowance = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Transportation Allowance", null=True, blank=True)
    per_diem = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    other_expense = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)

class EmployeeSignature(models.Model):
    order = models.OneToOneField(TravelOrder, on_delete=models.CASCADE, related_name='employee_signature')
    signed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    signature_photo = models.FileField(upload_to='signatures/employee/', null=True, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Employee Signature by {self.signed_by.full_name} for order {self.order.id}"
    
# -- Head Signature --
class Signature(models.Model):
    order = models.ForeignKey(TravelOrder, on_delete=models.CASCADE)
    signed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    signature_photo = models.FileField(upload_to='signatures/head/', null=True, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(null=True, blank=True)  

    def __str__(self):
        return f"Signed by {self.signed_by.full_name} for order {self.order.id}"

class TravelOrderApprovalSnapshot(models.Model):
    """Stores a snapshot of the travel order data when approved by each head"""
    travel_order = models.ForeignKey(TravelOrder, on_delete=models.CASCADE, related_name='approval_snapshots')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    approval_stage = models.IntegerField()
    approved_at = models.DateTimeField(auto_now_add=True)
    
    # Store the approved data as JSON
    approved_data = models.JSONField(default=dict, help_text="Snapshot of travel order data when approved")
    approved_itineraries = models.JSONField(default=list, help_text="Snapshot of itineraries when approved")
    
    def __str__(self):
        return f"Approval snapshot by {self.approved_by.full_name} at stage {self.approval_stage}"
    

    

#---- After Travel Report ------
class AfterTravelReport(models.Model):
    pap = models.CharField(max_length=255, help_text="Program/Activity/Project", blank=True, null=True)
    actual_output = models.CharField(max_length=255, blank=True, null=True)
    cash_advance = models.DateField(null=True, blank=True)
    period_of_implementation = models.DateField(null=True, blank=True)
    date_of_submission = models.DateField(null=True, blank=True)
    background = models.TextField(blank=True, null=True)
    highlights_of_activity = models.TextField(blank=True, null=True)
    ways_forward = models.TextField(blank=True, null=True)
    photo_documentation = models.JSONField(default=list, help_text="List of photo file paths")
    prepared_by = models.ManyToManyField(CustomUser, related_name='prepared_after_travel_reports', blank=True)
    office_head = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_after_travel_reports')
    regional_director = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='director_approved_after_travel_reports')
    travel_order = models.ForeignKey('TravelOrder', on_delete=models.CASCADE, null=True, blank=True, related_name='draft_after_travel_reports', help_text='Travel order this draft belongs to')
    is_draft = models.BooleanField(default=False, help_text='True if this is a draft, False if submitted for approval')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"After Travel Report - {self.pap}"

#---- Certificate of Travel Completed ------
class CertificateOfTravel(models.Model):
    STATION_CHOICES = [
        ('urdaneta_csc', 'Urdaneta Community Service Center'),
        ('sison_csc', 'Sison Community Service Center'),
        ('pugo_csc', 'Pugo Community Service Center'),
        ('sudipen_csc', 'Sudipen Community Service Center'),
        ('tagudin_csc', 'Tagudin Community Service Center'),
        ('banayoyo_csc', 'Banayoyo Community Service Center'),
        ('dingras_csc', 'Dingras Community Service Center'),
        ('pangasinan_po', 'Pangasinan Provincial Office'),
        ('ilocossur_po', 'Ilocos Sur Provincial Office'),
        ('ilocosnorte_po', 'Ilocos Norte Provincial Office'),
        ('regional', 'Regional Office'),
    ]

    FUND_CLUSTER_CHOICES = [
        ('01_RF', '01-RF'),
        ('07_TF', '07-TF'),
    ]

    DEVIATION_CHOICES = [
        ('strictly_accordance', 'Strictly in accordance with the approved itinerary'),
        ('cut_short_excess', 'Cut short as explained below. Excess payment in the amount of P____________'),
        ('cut_short_refunded', 'was refunded under O.R. No. _____________ dated _____________'),
        ('extended', 'Extended as explained below. Additional itinerary was submitted'),
        ('other_deviation', 'Other deviation as explained below'),
    ]

    EVIDENCE_CHOICES = [
        ('certificate_of_appearance', 'Certificate of Appearance'),
        ('others', 'Others'),
    ]

    agency_head = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificate_of_travel_agency_head')
    fund_cluster = models.CharField(max_length=10, choices=FUND_CLUSTER_CHOICES, blank=True, null=True)
    station = models.CharField(max_length=50, choices=STATION_CHOICES, blank=True, null=True)
    travel_order_number = models.CharField(max_length=50, blank=True, null=True)
    date_travel_from = models.DateField(null=True, blank=True)
    date_travel_to = models.DateField(null=True, blank=True)
    respectfully_submitted = models.ManyToManyField(CustomUser, related_name='certificate_of_travel_submitted', blank=True)
    approved = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificate_of_travel_approved')
    
    # Deviation tracking fields
    deviation_types = models.JSONField(default=list, help_text="List of selected deviation types", blank=True)
    explanations_justifications = models.TextField(blank=True, null=True)
    evidence_type = models.CharField(max_length=25, choices=EVIDENCE_CHOICES, blank=True, null=True)
    
    # Fields for cut short deviation
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    or_number = models.CharField(max_length=50, blank=True, null=True)
    or_date = models.DateField(null=True, blank=True)
    
    travel_order = models.ForeignKey('TravelOrder', on_delete=models.CASCADE, null=True, blank=True, related_name='draft_certificate_of_travel', help_text='Travel order this draft belongs to')
    is_draft = models.BooleanField(default=False, help_text='True if this is a draft, False if submitted for approval')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate of Travel Completed - {self.travel_order_number}"

#---- Certificate of Appearance ------
class CertificateOfAppearance(models.Model):
    certificate_of_appearance = models.FileField(upload_to='liquidations/certificate_of_appearance/', null=True, blank=True)
    travel_order = models.ForeignKey('TravelOrder', on_delete=models.CASCADE, null=True, blank=True, related_name='draft_certificate_of_appearance', help_text='Travel order this draft belongs to')
    is_draft = models.BooleanField(default=False, help_text='True if this is a draft, False if submitted for approval')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Certificate of Appearance - {self.travel_order.travel_order_number if self.travel_order else 'No Order'}"

#---- Liquidation ------
class Liquidation(models.Model):
    LIQUIDATION_STATUSES = [
        ('Pending', 'Pending'),
        ('Under Pre-Audit', 'Under Pre-Audit'),
        ('Under Final Audit', 'Under Final Audit'),
        ('Ready for Claim', 'Ready for Claim'),
        ('Rejected', 'Rejected'),
    ]

    travel_order = models.OneToOneField('TravelOrder', on_delete=models.CASCADE, related_name='liquidation')
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='uploaded_liquidations')
    certificate_of_travel = models.OneToOneField(CertificateOfTravel, on_delete=models.CASCADE, related_name='liquidation', null=True, blank=True)
    certificate_of_appearance = models.FileField(upload_to='liquidations/certificate_of_appearance/')
    after_travel_report = models.OneToOneField(AfterTravelReport, on_delete=models.CASCADE, related_name='liquidation', null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resubmitted_at = models.DateTimeField(null=True, blank=True)

    # Individual component status tracking
    after_travel_report_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('pending_review', 'Pending Review'),
        ('reviewer_approved', 'Reviewer Approved'),
        ('reviewer_rejected', 'Reviewer Rejected'),
        ('bookkeeper_approved', 'Bookkeeper Approved'),
        ('bookkeeper_rejected', 'Bookkeeper Rejected'),
        ('accountant_approved', 'Accountant Approved'),
        ('accountant_rejected', 'Accountant Rejected'),
    ], default='pending')
    
    certificate_of_travel_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('pending_review', 'Pending Review'),
        ('reviewer_approved', 'Reviewer Approved'),
        ('reviewer_rejected', 'Reviewer Rejected'),
        ('bookkeeper_approved', 'Bookkeeper Approved'),
        ('bookkeeper_rejected', 'Bookkeeper Rejected'),
        ('accountant_approved', 'Accountant Approved'),
        ('accountant_rejected', 'Accountant Rejected'),
    ], default='pending')
    
    certificate_of_appearance_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('bookkeeper_approved', 'Bookkeeper Approved'),
        ('bookkeeper_rejected', 'Bookkeeper Rejected'),
        ('accountant_approved', 'Accountant Approved'),
        ('accountant_rejected', 'Accountant Rejected'),
    ], default='pending')

    # Reviewer fields
    after_travel_report_reviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='after_travel_report_reviews')
    certificate_of_travel_reviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificate_of_travel_reviews')
    
    # Reviewer approval fields
    after_travel_report_reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='after_travel_report_approvals')
    after_travel_report_reviewed_at = models.DateTimeField(null=True, blank=True)
    after_travel_report_reviewer_comment = models.TextField(blank=True)
    after_travel_report_reviewer_signature = models.FileField(upload_to='signatures/liquidation/after_travel/', null=True, blank=True)
    
    certificate_of_travel_reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificate_of_travel_approvals')
    certificate_of_travel_reviewed_at = models.DateTimeField(null=True, blank=True)
    certificate_of_travel_reviewer_comment = models.TextField(blank=True)
    certificate_of_travel_reviewer_signature = models.FileField(upload_to='signatures/liquidation/certificate_of_travel/', null=True, blank=True)

    # Bookkeeper review fields
    reviewed_by_bookkeeper = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookkeeper_reviews')
    reviewed_at_bookkeeper = models.DateTimeField(null=True, blank=True)
    bookkeeper_comment = models.TextField(blank=True)
    
    # Individual component bookkeeper comments
    after_travel_report_bookkeeper_comment = models.TextField(blank=True)
    certificate_of_travel_bookkeeper_comment = models.TextField(blank=True)
    certificate_of_appearance_bookkeeper_comment = models.TextField(blank=True)

    # Accountant review fields
    reviewed_by_accountant = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='accountant_reviews')
    reviewed_at_accountant = models.DateTimeField(null=True, blank=True)
    accountant_comment = models.TextField(blank=True)
    
    # Individual component accountant comments
    after_travel_report_accountant_comment = models.TextField(blank=True)
    certificate_of_travel_accountant_comment = models.TextField(blank=True)
    certificate_of_appearance_accountant_comment = models.TextField(blank=True)

    # Final amount set by accountant during final audit
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, 
                                       help_text="Final amount set by accountant during final audit")

    # Legacy fields for backward compatibility
    is_bookkeeper_approved = models.BooleanField(null=True)
    is_accountant_approved = models.BooleanField(null=True)

    status = models.CharField(max_length=50, choices=LIQUIDATION_STATUSES, default='Pending')

    def update_status(self):
        print(f"DEBUG: update_status called for liquidation {self.id}")
        
        # Get all submitted components (not None/empty)
        submitted_components = []
        try:
            if self.after_travel_report:
                submitted_components.append(self.after_travel_report_status)
                print(f"DEBUG: ATR status: {self.after_travel_report_status}")
            if self.certificate_of_travel:
                submitted_components.append(self.certificate_of_travel_status)
                print(f"DEBUG: COT status: {self.certificate_of_travel_status}")
            if self.certificate_of_appearance:
                submitted_components.append(self.certificate_of_appearance_status)
                print(f"DEBUG: COA status: {self.certificate_of_appearance_status}")
        except AttributeError as e:
            print(f"DEBUG: AttributeError in update_status: {e}")
            # If fields don't exist, just return without changing status
            return
        
        print(f"DEBUG: Submitted components statuses: {submitted_components}")
        
        # If no components are submitted yet, keep as Pending
        if not submitted_components:
            self.status = 'Pending'
            self.save()
            print("DEBUG: No submitted components, set to Pending")
            return
        
        # Check if all submitted components are approved by accountant
        all_approved = all(status == 'accountant_approved' for status in submitted_components)
        
        # Check if any submitted component is rejected by accountant
        any_rejected = any(status == 'accountant_rejected' for status in submitted_components)
        
        # Check if all submitted components are approved by bookkeeper (ready for accountant)
        all_bookkeeper_approved = all(status == 'bookkeeper_approved' for status in submitted_components)
        
        # Check if any submitted component is rejected by bookkeeper
        any_bookkeeper_rejected = any(status == 'bookkeeper_rejected' for status in submitted_components)
        
        # Check if all submitted components are approved by reviewer (ready for bookkeeper)
        all_reviewer_approved = all(status == 'reviewer_approved' for status in submitted_components)
        
        # Check if any submitted component is rejected by reviewer
        any_reviewer_rejected = any(status == 'reviewer_rejected' for status in submitted_components)
        
        # Check if all submitted components are still pending or submitted
        all_pending = all(status in ['pending', 'pending_review', 'submitted'] for status in submitted_components)
        
        # Check if any component has been approved by accountant (but not all)
        any_accountant_approved = any(status == 'accountant_approved' for status in submitted_components)
        
        print(f"DEBUG: Status checks - all_approved: {all_approved}, any_rejected: {any_rejected}, all_bookkeeper_approved: {all_bookkeeper_approved}, any_bookkeeper_rejected: {any_bookkeeper_rejected}, all_reviewer_approved: {all_reviewer_approved}, any_reviewer_rejected: {any_reviewer_rejected}, all_pending: {all_pending}, any_accountant_approved: {any_accountant_approved}")
        
        if all_approved:
            self.status = 'Ready for Claim'
            print("DEBUG: Set status to Ready for Claim")
        elif any_rejected:
            self.status = 'Rejected'
            print("DEBUG: Set status to Rejected")
        elif any_accountant_approved and not all_approved:
            # Some components approved by accountant but not all - keep as Under Final Audit
            self.status = 'Under Final Audit'
            print("DEBUG: Set status to Under Final Audit (some accountant approved, not all)")
        elif all_bookkeeper_approved:
            self.status = 'Under Final Audit'
            print("DEBUG: Set status to Under Final Audit")
        elif any_bookkeeper_rejected:
            self.status = 'Under Pre-Audit'
            print("DEBUG: Set status to Under Pre-Audit")
        elif all_reviewer_approved:
            self.status = 'Under Pre-Audit'
            print("DEBUG: Set status to Under Pre-Audit (reviewer approved, ready for bookkeeper)")
        elif any_reviewer_rejected:
            self.status = 'Rejected'
            print("DEBUG: Set status to Rejected (reviewer rejected)")
        elif not all_pending:
            # Some components have been reviewed, set to Under Pre-Audit
            self.status = 'Under Pre-Audit'
            print("DEBUG: Set status to Under Pre-Audit (some reviewed)")
        else:
            # Components are submitted but still pending review - set to Pending
            self.status = 'Pending'
            print("DEBUG: Set status to Pending (components submitted, waiting for reviewer)")
        self.save()
        print(f"DEBUG: Final status: {self.status}")
    
    def get_component_status_summary(self):
        """Get a summary of all component statuses"""
        return {
            'after_travel_report': self.after_travel_report_status,
            'certificate_of_travel': self.certificate_of_travel_status,
            'certificate_of_appearance': self.certificate_of_appearance_status,
            'overall_status': self.status
        }

    # Liquidation deadline field
    liquidation_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline for liquidation completion")
    
    # Draft data storage (JSONField) - stores draft data directly on Liquidation
    after_travel_report_draft = models.JSONField(default=dict, blank=True, null=True, help_text="Draft data for after travel report")
    certificate_of_travel_draft = models.JSONField(default=dict, blank=True, null=True, help_text="Draft data for certificate of travel")
    certificate_of_appearance_draft = models.JSONField(default=dict, blank=True, null=True, help_text="Draft data for certificate of appearance (file path)")

    def __str__(self):
        return f"Liquidation for Travel Order {self.travel_order.travel_order_number}"


# --- NOTIFICATIONS ---
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('travel_approved', 'Travel Request Approved'),
        ('travel_rejected', 'Travel Request Rejected'),
        ('travel_rejected_by_next_approver', 'Travel Request Rejected by Next Approver'),
        ('travel_final_approved', 'Travel Request Finally Approved'),
        ('new_approval_needed', 'New Approval Needed'),
        ('liquidation_approved', 'Liquidation Approved'),
        ('liquidation_rejected', 'Liquidation Rejected'),
        ('liquidation_submitted', 'Liquidation Submitted'),
        ('liquidation_needs_review', 'Liquidation Needs Review'),
        ('liquidation_deadline_approaching', 'Liquidation Deadline Approaching'),
        ('liquidation_expired', 'Liquidation Expired'),
        ('component_approved', 'Component Approved'),
        ('component_rejected', 'Component Rejected'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    travel_order = models.ForeignKey(TravelOrder, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.user.full_name}"


# --- TEMPORARY PASSWORD ---
class TemporaryPassword(models.Model):
    """Model to store temporary passwords for new users with expiration"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='temporary_passwords')
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.full_name} - Temporary Password"
    
    def is_expired(self):
        return timezone.now() > self.expires_at


# --- AUDIT LOG ---
class AuditLog(models.Model):
    ACTION_TYPES = [
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('resubmit', 'Resubmit'),
        ('view', 'View'),
        ('download', 'Download'),
        ('password_change', 'Password Change'),
        ('profile_update', 'Profile Update'),
    ]
    
    RESOURCE_TYPES = [
        ('travel_order', 'Travel Order'),
        ('liquidation', 'Liquidation'),
        ('user', 'User'),
        ('fund', 'Fund'),
        ('transportation', 'Transportation'),
        ('employee_position', 'Employee Position'),
        ('after_travel_report', 'After Travel Report'),
        ('notification', 'Notification'),
        ('system', 'System'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    resource_type = models.CharField(max_length=50, choices=RESOURCE_TYPES)
    resource_id = models.CharField(max_length=100, null=True, blank=True)
    resource_name = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField()
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource_type', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name if self.user else 'System'} - {self.action} {self.resource_type} at {self.timestamp}"


# --- BACKUP MANAGEMENT ---
class Backup(models.Model):
    BACKUP_TYPES = [
        ('full', 'Full SQL Database Backup'),
        ('data_only', 'Data Only SQL Backup'),
        ('schema_only', 'Schema Only SQL Backup'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    name = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES, default='full')
    file_path = models.CharField(max_length=500, null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_backups')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['backup_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.get_backup_type_display()} ({self.status})"


class Restore(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    backup_file = models.FileField(upload_to='backups/restore/')
    original_backup = models.ForeignKey(Backup, on_delete=models.SET_NULL, null=True, blank=True, related_name='restores')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    restored_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='restored_backups')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Restore from {self.backup_file.name} - {self.status}"