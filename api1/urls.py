from django.urls import path
from .views import (
    TravelOrderCreateView, ApproveTravelOrderView, ResubmitTravelOrderView,
    CurrentUserView,TravelOrderDetailUpdateView,
    EmployeeListView, HeadListView, DirectorListView, MyTravelOrdersView, TravelOrderApprovalsView,
    FundListCreateView, TransportationCreateView,AdminTravelView, AdminLiquidationsView,
    FundDetailView,TransportationDetailView, EmployeeDetailUpdateView,
    EmployeePositionCreateView,EmployeePositionDetailView,
    PurposeCreateView, PurposeDetailView, SpecificRoleCreateView, SpecificRoleDetailView,
    SubmitLiquidationView, SubmitAfterTravelReportView, SubmitCertificateOfTravelView, SubmitCertificateOfAppearanceView,
    UpdateAfterTravelReportView, UpdateCertificateOfTravelView, UpdateCertificateOfAppearanceView,
    SaveDraftAfterTravelReportView, SaveDraftCertificateOfTravelView, SaveDraftCertificateOfAppearanceView,
    BookkeeperReviewView, BookkeeperComponentReviewView, AccountantReviewView, AccountantComponentReviewView, UpdateFinalAmountView, LiquidationListView,
    TravelOrdersNeedingLiquidationView, LiquidationDetailView, TravelOrderItineraryView,
    EmployeeDashboardAPIView, AdminDashboard, HeadDashboardAPIView, HeadApprovalHistoryView, DirectorDashboardView,TravelOrderReportView,
    NotificationListView, NotificationMarkReadView, NotificationMarkAllReadView, NotificationCountView, test_email_notification, debug_travel_order, check_token_validity,
    AfterTravelReportView, AuditLogListView, BackupListView, BackupDetailView, download_backup,
    RestoreListView, RestoreDetailView, ReportsAPIView,
    LiquidationReviewerView, LiquidationReviewerHistoryView, LiquidationComponentReviewView, UpdateLiquidationReviewerView,
    TravelOrderSignaturesView, TravelOrderPDFDataView,
    login_view, logout_view,
    refresh_token_view, protected_view, download_evidence, change_password_view
)

urlpatterns = [
     
    path('login/', login_view),
    path('logout/', logout_view),
    path('refresh/', refresh_token_view),
    path('protected/', protected_view),
    path('change-password/', change_password_view),

    #Users/Admin
    path('employees/', EmployeeListView.as_view(), name='employee-list'),
    path('heads/', HeadListView.as_view(), name='head-list'),
    path('directors/', DirectorListView.as_view(), name='director-list'),
    path('employees/<int:pk>/', EmployeeDetailUpdateView.as_view(), name='employee-update'),
    path('admin/travels/',AdminTravelView.as_view(), name='admin-travels'),
    path('admin/liquidations/',AdminLiquidationsView.as_view(), name='admin-liquidations'),
    path('reports/', TravelOrderReportView.as_view(), name='travel-order-report'),
    path('admin/reports/', ReportsAPIView.as_view(), name='admin-reports'),

    # Travel Order Routes
    path('travel-orders/', TravelOrderCreateView.as_view(), name='create-travel-order'),

    path('my-travel-orders/', MyTravelOrdersView.as_view(), name='my-travel-orders'),
    path('my-pending-approvals/', TravelOrderApprovalsView.as_view(), name='travel-order-approvals'),
    path('my-approval-history/', HeadApprovalHistoryView.as_view(), name='head-approval-history'),
    path('travel-orders/<int:pk>/', TravelOrderDetailUpdateView.as_view(), name='travel-order-detail-update'),
    path('travel-itinerary/<int:travel_order_id>/', TravelOrderItineraryView.as_view(), name='travel-order-itineraries'),
    path('travel-orders/<int:travel_order_id>/signatures/', TravelOrderSignaturesView.as_view(), name='travel-order-signatures'),
    path('travel-orders/<int:travel_order_id>/pdf-data/', TravelOrderPDFDataView.as_view(), name='travel-order-pdf-data'),
    
    #travels settings
    path('funds/', FundListCreateView.as_view(), name='funds'),
    path('transportation/', TransportationCreateView .as_view(), name='transportation'),
    path('funds/<int:pk>/', FundDetailView.as_view(), name='fund-detail'),
    path('transportation/<int:pk>/', TransportationDetailView.as_view(), name='transportation-detail'),
    path('employee-position/', EmployeePositionCreateView.as_view(), name='employee-position'),
    path('employee-position/<int:pk>/', EmployeePositionDetailView.as_view(), name='employee-position-detail'),
    path('purpose/', PurposeCreateView.as_view(), name='purpose'),
    path('purpose/<int:pk>/', PurposeDetailView.as_view(), name='purpose-detail'),
    path('specific-role/', SpecificRoleCreateView.as_view(), name='specific-role'),
    path('specific-role/<int:pk>/', SpecificRoleDetailView.as_view(), name='specific-role-detail'),

    #liquidation
    #  Employee: Submit or resubmit liquidation
    path('liquidation/<int:pk>/submit/', SubmitLiquidationView.as_view(), name='submit-liquidation'),
    
    # Individual liquidation component submissions
    path('liquidation/<int:pk>/submit-after-travel-report/', SubmitAfterTravelReportView.as_view(), name='submit-after-travel-report'),
    path('liquidation/<int:pk>/submit-certificate-of-travel/', SubmitCertificateOfTravelView.as_view(), name='submit-certificate-of-travel'),
    path('liquidation/<int:pk>/submit-certificate-of-appearance/', SubmitCertificateOfAppearanceView.as_view(), name='submit-certificate-of-appearance'),
    
    # Individual liquidation component updates (for rejected items)
    path('liquidation/<int:pk>/update-after-travel-report/', UpdateAfterTravelReportView.as_view(), name='update-after-travel-report'),
    path('liquidation/<int:pk>/update-certificate-of-travel/', UpdateCertificateOfTravelView.as_view(), name='update-certificate-of-travel'),
    path('liquidation/<int:pk>/update-certificate-of-appearance/', UpdateCertificateOfAppearanceView.as_view(), name='update-certificate-of-appearance'),
    
    # Draft save endpoints for liquidation forms
    path('liquidation/<int:pk>/save-draft-after-travel-report/', SaveDraftAfterTravelReportView.as_view(), name='save-draft-after-travel-report'),
    path('liquidation/<int:pk>/save-draft-certificate-of-travel/', SaveDraftCertificateOfTravelView.as_view(), name='save-draft-certificate-of-travel'),
    path('liquidation/<int:pk>/save-draft-certificate-of-appearance/', SaveDraftCertificateOfAppearanceView.as_view(), name='save-draft-certificate-of-appearance'),
    
    
    # After Travel Report
    path('after-travel-report/', AfterTravelReportView.as_view(), name='after-travel-report'),
    path('after-travel-report/<int:pk>/', AfterTravelReportView.as_view(), name='after-travel-report-detail'),

    #  Bookkeeper: Pre-audit (approve/reject)
    path('liquidation/<int:pk>/bookkeeper-review/', BookkeeperReviewView.as_view(), name='bookkeeper-review'),
    path('liquidation/<int:pk>/bookkeeper-review/<str:component>/', BookkeeperComponentReviewView.as_view(), name='bookkeeper-component-review'),

    #  Accountant: Final audit (approve/reject)
    path('liquidation/<int:pk>/accountant-review/', AccountantReviewView.as_view(), name='accountant-review'),
    path('liquidation/<int:pk>/accountant-review/<str:component>/', AccountantComponentReviewView.as_view(), name='accountant-component-review'),
    path('liquidation/<int:pk>/update-final-amount/', UpdateFinalAmountView.as_view(), name='update-final-amount'),

    #  All liquidations (admin/staff/bookkeeper view)
    path('liquidations/', LiquidationListView.as_view(), name='liquidation-list'),

    # 👤 Employee: View their own liquidation (history/dashboard)
    path("travel-orders-needing-liquidation/", TravelOrdersNeedingLiquidationView.as_view(), name="travel-orders-needing-liquidation"),

    # 🔍 Detail view
    path('liquidations/<int:pk>/', LiquidationDetailView.as_view(), name='liquidation-detail'),

    # 👥 Reviewer: View liquidations assigned to them
    path('liquidation-reviewer/', LiquidationReviewerView.as_view(), name='liquidation-reviewer'),
    path('liquidation-reviewer-history/', LiquidationReviewerHistoryView.as_view(), name='liquidation-reviewer-history'),
    path('liquidation/<int:liquidation_id>/review/<str:component_type>/', LiquidationComponentReviewView.as_view(), name='liquidation-component-review'),
    path('liquidation/<int:liquidation_id>/update-reviewer/', UpdateLiquidationReviewerView.as_view(), name='update-liquidation-reviewer'),




   
    path('approve-travel-order/<int:pk>/', ApproveTravelOrderView.as_view(), name='approve-travel-order'),
    path('resubmit-travel-order/<int:pk>/', ResubmitTravelOrderView.as_view(), name='resubmit-travel-order'),

    #dashboard
    path('employee-dashboard/', EmployeeDashboardAPIView.as_view(), name='employee-dashboard'),
    path('admin-dashboard/', AdminDashboard.as_view(), name='travel-order-chart'),
    path('head-dashboard/', HeadDashboardAPIView.as_view(), name='head-dashboard'),
    path('director-dashboard/', DirectorDashboardView.as_view(), name='director-dashboard'),

    # Authenticated User Info
    path('user-info/', CurrentUserView.as_view(), name='user-info'),
    
    # Evidence Download
    path('travel-orders/<int:travel_order_id>/evidence/', download_evidence, name='download-evidence'),
    
    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/mark-read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    path('notifications/count/', NotificationCountView.as_view(), name='notification-count'),
    path('test-email-notification/', test_email_notification, name='test-email-notification'),
    path('debug-travel-order/<int:pk>/', debug_travel_order, name='debug-travel-order'),
    path('check-token-validity/', check_token_validity, name='check-token-validity'),
    
    # Audit Logs
    path('audit-logs/', AuditLogListView.as_view(), name='audit-log-list'),
    
    # Backup and Restore
    path('backups/', BackupListView.as_view(), name='backup-list'),
    path('backups/<int:pk>/', BackupDetailView.as_view(), name='backup-detail'),
    path('backups/<int:pk>/download/', download_backup, name='download-backup'),
    path('restores/', RestoreListView.as_view(), name='restore-list'),
    path('restores/<int:pk>/', RestoreDetailView.as_view(), name='restore-detail'),
    
]