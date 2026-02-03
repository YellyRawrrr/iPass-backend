# views.py
# API views for the Travel Order Management System
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models.functions import TruncMonth
from django.db.models import Count, Q
from django.db import models
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from datetime import timedelta, datetime
from collections import defaultdict 
import json
import os
import uuid
from django.utils.dateparse import parse_date
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from datetime import timedelta
from django.utils.timezone import now
from .models import TravelOrder, Signature, CustomUser, Fund, Transportation, EmployeePosition, Purpose, SpecificRole, Liquidation, EmployeeSignature, Itinerary, Notification, AfterTravelReport, CertificateOfTravel, CertificateOfAppearance, AuditLog, Backup, Restore, TravelOrderApprovalSnapshot, TemporaryPassword
from django.contrib.auth import get_user_model
from .serializers import TravelOrderSerializer, UserSerializer, FundSerializer, TransportationSerializer, EmployeePositionSerializer, PurposeSerializer, SpecificRoleSerializer, LiquidationSerializer, ItinerarySerializer, TravelOrderSimpleSerializer, TravelOrderReportSerializer, NotificationSerializer, AfterTravelReportSerializer, CertificateOfTravelSerializer, CertificateOfAppearanceSerializer, AuditLogSerializer, BackupSerializer, RestoreSerializer, EmployeeSignatureSerializer
from .utils import get_approval_chain, get_next_head, build_status_map
from .email_service import send_notification_email, send_bulk_notification_emails, generate_temporary_password, send_user_creation_email
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
import os
import mimetypes


def create_notification(user, travel_order, notification_type, title, message, liquidation=None):
    """Helper function to create notifications and send email"""
    # Create system notification
    notification = Notification.objects.create(
        user=user,
        travel_order=travel_order,
        notification_type=notification_type,
        title=title,
        message=message
    )
    
    # Send email notification
    try:
        email_sent = send_notification_email(user, travel_order, notification_type, title, message, liquidation=liquidation)
        if email_sent:
            notification.email_sent = True
            notification.email_sent_at = timezone.now()
            notification.save()
    except Exception as e:
        print(f"Error sending email notification to {user.email}: {e}")
        # Don't fail the notification creation if email fails


def log_audit_event(user, action, resource_type, resource_id=None, resource_name=None, description="", request=None, metadata=None):
    """Helper function to create audit log entries"""
    user_agent = None
    
    if request:
        # Get user agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length
    
    AuditLog.objects.create(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        resource_name=resource_name,
        description=description,
        user_agent=user_agent,
        metadata=metadata or {}
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """User authentication endpoint - returns JWT tokens on successful login"""
    email = request.data.get('email')
    password = request.data.get('password')

    # Authenticate using email as username
    user = authenticate(request, username=email, password=password)

    if user:
        # Check if user is active
        if not user.is_active:
            return Response({
                "message": "Account is inactive. Please contact an administrator.",
                "error_code": "user_inactive"
            }, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Log successful login
        log_audit_event(
            user=user,
            action='login',
            resource_type='system',
            description=f'User {user.email} logged in successfully',
            request=request
        )

        # Check if user must change password
        if user.must_change_password:
            response = Response({
                "message": "Password change required", 
                "must_change_password": True,
                "user_id": user.id,
                "access_token": access_token,
                "refresh_token": str(refresh)
            }, status=status.HTTP_200_OK)
        else:
            response = Response({
                "message": "Login Successful",
                "access_token": access_token,
                "refresh_token": str(refresh)
            }, status=status.HTTP_200_OK)

        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        cookie_secure = settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False)
        cookie_httponly = settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True)
        cookie_samesite = settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax")
        access_token_lifetime = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
        refresh_token_lifetime = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

        response.set_cookie(cookie_name, access_token, httponly=cookie_httponly, secure=cookie_secure,
                            samesite=cookie_samesite, max_age=access_token_lifetime)
        response.set_cookie('refresh_token', str(refresh), httponly=cookie_httponly, secure=cookie_secure,
                            samesite=cookie_samesite, max_age=refresh_token_lifetime)

        return response
    return Response({"message": "Invalid Credentials"}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    # Log logout event
    log_audit_event(
        user=request.user,
        action='logout',
        resource_type='system',
        description=f'User {request.user.email} logged out',
        request=request
    )
    
    response = Response({'message': 'Logged out successfully'}, status=200)
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    refresh_token = request.COOKIES.get('refresh_token')
    if not refresh_token:
        return Response({'error': 'No refresh token'}, status=401)
    try:
        cookie_secure = settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False)
        cookie_httponly = settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True)
        cookie_samesite = settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax")
        access_token_lifetime = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())

        refresh = RefreshToken(refresh_token)
        
        # Get the user from the refresh token and check if they're active
        user_id = refresh.payload.get('user_id')
        if user_id:
            try:
                User = get_user_model()
                user = User.objects.get(id=user_id)
                if not user.is_active:
                    return Response({
                        'detail': 'User is inactive',
                        'error_code': 'user_inactive'
                    }, status=401)
            except User.DoesNotExist:
                return Response({'detail': 'User not found'}, status=401)
        
        access = str(refresh.access_token)
        new_refresh = str(refresh)

        res = Response({
            'access': access,
            'refresh': new_refresh
        }, status=200)
        res.set_cookie('access_token', access, httponly=cookie_httponly, samesite=cookie_samesite,
                       secure=cookie_secure, max_age=access_token_lifetime, path="/")
        res.set_cookie('refresh_token', new_refresh, httponly=cookie_httponly, samesite=cookie_samesite,
                       secure=cookie_secure, max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()), path="/")
        return res
    except Exception:
        return Response({'detail': 'Invalid refresh token'}, status=403)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def protected_view(request):
    return Response({
        "authenticated": True,
        "user": request.user.email
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """
    Change user password and clear must_change_password flag
    """
    user = request.user
    new_password = request.data.get('new_password')
    
    if not new_password:
        return Response({"error": "New password is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    if len(new_password) < 8:
        return Response({"error": "Password must be at least 8 characters long"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Set new password
    user.set_password(new_password)
    # Clear the must_change_password flag
    user.must_change_password = False
    user.save()
    
    return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)




class TravelOrderCreateView(APIView):
    """API view for creating new travel orders with file uploads"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        
        # Debug: Raw request data
        print("=== RAW REQUEST DATA ===")
        print(f"request.data keys: {list(request.data.keys())}")
        print(f"request.FILES keys: {list(request.FILES.keys())}")
        for key, value in request.data.items():
            if key in ['employees', 'itinerary']:
                print(f"{key}: {value} (type: {type(value)})")
        
        # Get approval chain
        approval_chain = get_approval_chain(user)
        next_head = get_next_head(approval_chain, 0, current_user=user) if approval_chain else None

        # Convert QueryDict to regular dict and handle list values properly
        data = {}
        for key, value in request.data.items():
            if isinstance(value, list) and len(value) == 1:
                # Extract single value from list (Django form processing creates lists)
                data[key] = value[0]
            else:
                data[key] = value

        # Parse itinerary
        if isinstance(data.get('itinerary'), str):
            try:
                data['itinerary'] = json.loads(data['itinerary'])
            except json.JSONDecodeError as e:
                return Response({'itinerary': ['Invalid itinerary format.']}, status=400)

        # Parse employees
        if isinstance(data.get('employees'), str):
            try:
                data['employees'] = json.loads(data['employees'])
            except json.JSONDecodeError as e:
                return Response({'employees': ['Invalid employees format.']}, status=400)

        # Parse approver_selection
        if isinstance(data.get('approver_selection'), str):
            try:
                data['approver_selection'] = json.loads(data['approver_selection'])
            except json.JSONDecodeError as e:
                return Response({'approver_selection': ['Invalid approver selection format.']}, status=400)

        # Ensure filer is in employees
        if user.id not in data['employees']:
            data['employees'].insert(0, user.id)

        # Check if this is a draft save
        is_draft = data.get('is_draft', False)
        if isinstance(is_draft, str):
            is_draft = is_draft.lower() == 'true'
        
        # Check if this is an amendment (creates new order with Amending- prefix)
        is_amend = data.get('mode', '').lower() == 'amend'
        original_travel_order_number = data.get('original_travel_order_number')
        print(f"DEBUG POST: is_amend = {is_amend}, original_travel_order_number = {original_travel_order_number}")
        
        # Clean up itinerary data for drafts: convert empty strings to None
        if is_draft and 'itinerary' in data:
            for item in data['itinerary']:
                if item.get('departure_time') == '':
                    item['departure_time'] = None
                if item.get('arrival_time') == '':
                    item['arrival_time'] = None
                if item.get('itinerary_date') == '':
                    item['itinerary_date'] = None
                if item.get('destination') == '':
                    item['destination'] = None
                if item.get('destination_cluster') == '':
                    item['destination_cluster'] = None
        
        # For drafts, clean up empty date fields by converting to None
        if is_draft:
            if not data.get('date_travel_from') or data.get('date_travel_from') == '':
                data['date_travel_from'] = None
            if not data.get('date_travel_to') or data.get('date_travel_to') == '':
                data['date_travel_to'] = None
            # purpose is now a ForeignKey, so set to None if empty (not a string)
            if not data.get('purpose') or data.get('purpose') == '':
                data['purpose'] = None
            # specific_role is now a ForeignKey, so set to None if empty (not a string)
            if not data.get('specific_role') or data.get('specific_role') == '':
                data['specific_role'] = None
        
        # For drafts, don't set approver or trigger workflow
        if not is_draft:
            data['current_approver'] = next_head.id if next_head else None
            data['approval_stage'] = 0
        else:
            # For drafts, clear approver info
            data['current_approver'] = None
            data['approval_stage'] = 0

        # Debug: Final data being validated
        print(f"FINAL VALIDATION DATA: {dict(data)}")
        
        # Validate and save
        serializer = TravelOrderSerializer(data=data)
        if serializer.is_valid():
            # Handle evidence file
            evidence_file = request.FILES.get('evidence')
            save_kwargs = {'prepared_by': user, 'is_draft': is_draft}
            if evidence_file:
                save_kwargs['evidence'] = evidence_file
                
            travel_order = serializer.save(**save_kwargs)
            travel_order.number_of_employees = travel_order.employees.count()

            # For amendments, store the original travel order number in approver_selection
            # Don't set "Amending-" prefix yet - that will be done when Regional Director approves
            # BUT: Directors always get a number immediately, even for amendments
            if is_amend and original_travel_order_number and not is_draft:
                # Store original number in approver_selection for later use when RD approves
                if not travel_order.approver_selection:
                    travel_order.approver_selection = {}
                travel_order.approver_selection['original_travel_order_number_for_amendment'] = original_travel_order_number
                
                # If director creates amendment, they get a regular number immediately (no "Amending-" prefix)
                # If non-director creates amendment, keep number as None until RD approves
                if user.user_level == 'director':
                    from .utils import generate_travel_order_number
                    travel_order.travel_order_number = generate_travel_order_number()
                    travel_order.current_approver = None
                    travel_order.approval_stage = 0
                    travel_order.status = "Travel request is placed"
                    travel_order.save(update_fields=['approver_selection', 'travel_order_number', 'current_approver', 'approval_stage', 'status'])
                    print(f"DEBUG POST: Director created amendment. Generated travel_order_number: {travel_order.travel_order_number}")
                else:
                    # Keep travel_order_number as None - will be set to "Amending-{original}" when RD approves
                    travel_order.travel_order_number = None
                    travel_order.save(update_fields=['approver_selection', 'travel_order_number'])
                    print(f"DEBUG POST: Amendment detected. Stored original_travel_order_number: {original_travel_order_number}")
            else:
                # 🔑 Director → auto-generate travel order number (only for non-drafts)
                if user.user_level == 'director' and not is_draft:
                    from .utils import generate_travel_order_number
                    travel_order.travel_order_number = generate_travel_order_number()
                    # No approvers needed
                    travel_order.current_approver = None
                    travel_order.approval_stage = 0
                    travel_order.status = "Travel request is placed"
                
                travel_order.save()

            # Handle signature photo
            signature_photo = request.FILES.get("signature_photo")
            if signature_photo:
                EmployeeSignature.objects.update_or_create(
                    order=travel_order,
                    defaults={
                        "signed_by": user,
                        "signature_photo": signature_photo
                    }
                )

            # Log travel order creation
            log_audit_event(
                user=user,
                action='create',
                resource_type='travel_order',
                resource_id=travel_order.id,
                resource_name=f"Travel to {travel_order.destination}",
                description=f'Created travel order to {travel_order.destination}' + (' as draft' if is_draft else ''),
                request=request
            )

            # Notify the head if there's a current approver (not for directors or drafts)
            if not is_draft and travel_order.current_approver and user.user_level != 'director':
                create_notification(
                    user=travel_order.current_approver,
                    travel_order=travel_order,
                    notification_type='new_approval_needed',
                    title=f'New Travel Request for Approval',
                    message=f'Travel request to {travel_order.destination} by {user.get_full_name()} needs your approval.'
                )

            print("SUCCESS: Travel order created")
            return Response(TravelOrderSerializer(travel_order).data, status=status.HTTP_201_CREATED)

        print(f"VALIDATION ERRORS: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class TravelOrderDetailUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, pk):
        order = get_object_or_404(TravelOrder.objects.select_related('purpose', 'specific_role'), pk=pk)
        serializer = TravelOrderSerializer(order, context={'request': request})
        return Response(serializer.data)

    def put(self, request, pk):
        order = get_object_or_404(TravelOrder.objects.select_related('purpose', 'specific_role'), pk=pk)

        if order.prepared_by != request.user:
            return Response({'error': 'Forbidden'}, status=403)

        # Convert QueryDict to regular dict and handle list values properly
        data = {}
        for key, value in request.data.items():
            if isinstance(value, list) and len(value) == 1:
                # Extract single value from list (Django form processing creates lists)
                data[key] = value[0]
            else:
                data[key] = value

        # Parse employees
        if isinstance(data.get('employees'), str):
            try:
                data['employees'] = json.loads(data['employees'])
            except json.JSONDecodeError:
                return Response({'employees': ['Invalid employees format.']}, status=400)
            
        # Parse itinerary
        if isinstance(data.get('itinerary'), str):
            try:
                data['itinerary'] = json.loads(data['itinerary'])
            except json.JSONDecodeError:
                return Response({'itinerary': ['Invalid itinerary format.']}, status=400)

        # Check if this is a draft save
        is_draft = data.get('is_draft', False)
        if isinstance(is_draft, str):
            is_draft = is_draft.lower() == 'true'
        
        # Check if this is an amendment
        is_amend = data.get('mode', '').lower() == 'amend'
        print(f"DEBUG: is_amend = {is_amend}, mode = {data.get('mode')}")
        print(f"DEBUG: order.travel_order_number = {order.travel_order_number}")
        
        # Clean up itinerary data for drafts: convert empty strings to None
        if is_draft and 'itinerary' in data:
            for item in data['itinerary']:
                if item.get('departure_time') == '':
                    item['departure_time'] = None
                if item.get('arrival_time') == '':
                    item['arrival_time'] = None
                if item.get('itinerary_date') == '':
                    item['itinerary_date'] = None
                if item.get('destination') == '':
                    item['destination'] = None
                if item.get('destination_cluster') == '':
                    item['destination_cluster'] = None
        
        # For drafts, clean up empty date fields by converting to None
        if is_draft:
            if not data.get('date_travel_from') or data.get('date_travel_from') == '':
                data['date_travel_from'] = None
            if not data.get('date_travel_to') or data.get('date_travel_to') == '':
                data['date_travel_to'] = None
            # purpose is now a ForeignKey, so set to None if empty (not a string)
            if not data.get('purpose') or data.get('purpose') == '':
                data['purpose'] = None
            # specific_role is now a ForeignKey, so set to None if empty (not a string)
            if not data.get('specific_role') or data.get('specific_role') == '':
                data['specific_role'] = None
        
        serializer = TravelOrderSerializer(order, data=data)
        if serializer.is_valid():
            # Handle evidence file if provided
            evidence_file = request.FILES.get('evidence')
            
            # Store original travel order number for amendments (before any updates)
            original_travel_order_number = None
            if is_amend and order.travel_order_number:
                original_travel_order_number = order.travel_order_number
                print(f"DEBUG: Amendment detected. Original travel_order_number: {original_travel_order_number}")
            
            # For drafts, don't reset approval workflow
            if is_draft:
                save_kwargs = {
                    'is_draft': True,
                }
            else:
                # Check if this was originally a draft - if so, treat as new submission, not resubmission
                was_draft = order.is_draft
                
                if was_draft:
                    # First-time submission from draft - treat as new submission
                    # Directors get travel order number immediately
                    if request.user.user_level == 'director':
                        from .utils import generate_travel_order_number
                        # Generate new number if not set or if it was set to None (e.g., from amendment logic)
                        travel_order_num = order.travel_order_number if order.travel_order_number and not order.travel_order_number.startswith('Amending-') else generate_travel_order_number()
                        save_kwargs = {
                            'approval_stage': 0,
                            'current_approver': None,
                            'is_resubmitted': False,
                            'status': 'Travel request is placed',
                            'is_draft': False,
                            'travel_order_number': travel_order_num,
                        }
                    else:
                        save_kwargs = {
                            'approval_stage': 0,
                            'current_approver': get_next_head(get_approval_chain(request.user), 0, current_user=request.user),
                            'is_resubmitted': False,  # Not a resubmission, it's the first submission
                            'status': 'Travel request is placed',  # Normal status for new submission
                            'is_draft': False,
                        }
                else:
                    # Resubmission of previously submitted order - treat as resubmission
                    # Directors get travel order number immediately
                    if request.user.user_level == 'director':
                        from .utils import generate_travel_order_number
                        # Generate new number if not set or if it was set to None (e.g., from amendment logic)
                        travel_order_num = order.travel_order_number if order.travel_order_number and not order.travel_order_number.startswith('Amending-') else generate_travel_order_number()
                        save_kwargs = {
                            'approval_stage': 0,
                            'current_approver': None,
                            'is_resubmitted': True,
                            'rejected_by': None,
                            'rejection_comment': '',
                            'rejected_at': None,
                            'status': 'Travel request is placed',
                            'is_draft': False,
                            'travel_order_number': travel_order_num,
                        }
                    else:
                        save_kwargs = {
                            'approval_stage': 0,
                            'current_approver': get_next_head(get_approval_chain(request.user), 0, current_user=request.user),
                            'is_resubmitted': True,
                            'rejected_by': None,
                            'rejection_comment': '',
                            'rejected_at': None,
                            'status': 'Travel Order Resubmitted',  # ✅ Reset status from 'rejected'
                            'is_draft': False,
                        }
                    
                    # For amendments, store the original travel order number in approver_selection
                    # Don't set "Amending-" prefix yet - that will be done when Regional Director approves
                    # BUT: Directors always get a number immediately, even for amendments
                    if original_travel_order_number:
                        # Store original number in approver_selection for later use when RD approves
                        if not order.approver_selection:
                            order.approver_selection = {}
                        order.approver_selection['original_travel_order_number_for_amendment'] = original_travel_order_number
                        
                        # If director creates amendment, they get a regular number immediately (no "Amending-" prefix)
                        # If non-director creates amendment, keep number as None until RD approves
                        if request.user.user_level == 'director':
                            from .utils import generate_travel_order_number
                            save_kwargs['travel_order_number'] = generate_travel_order_number()
                            save_kwargs['current_approver'] = None
                            print(f"DEBUG: Director created amendment. Generated travel_order_number: {save_kwargs['travel_order_number']}")
                        else:
                            # Keep travel_order_number as None - will be set to "Amending-{original}" when RD approves
                            save_kwargs['travel_order_number'] = None
                        print(f"DEBUG: Amendment detected. Stored original_travel_order_number: {original_travel_order_number}")
            
            if evidence_file:
                save_kwargs['evidence'] = evidence_file
            
            # Save the serializer first
            updated_order = serializer.save(**save_kwargs)
            
            # For directors: ensure they have a travel order number if not set
            if request.user.user_level == 'director' and not is_draft and not updated_order.travel_order_number:
                from .utils import generate_travel_order_number
                updated_order.travel_order_number = generate_travel_order_number()
                updated_order.current_approver = None
                updated_order.approval_stage = 0
                updated_order.status = "Travel request is placed"
                updated_order.save(update_fields=['travel_order_number', 'current_approver', 'approval_stage', 'status'])
                print(f"DEBUG: Director travel order updated. Generated travel_order_number: {updated_order.travel_order_number}")
            
            # For amendments, ensure the original number is stored in approver_selection
            # Don't set "Amending-" prefix yet - that will be done when Regional Director approves
            # BUT: Directors already got their number above, so skip this for directors
            if is_amend and original_travel_order_number and request.user.user_level != 'director':
                if not updated_order.approver_selection:
                    updated_order.approver_selection = {}
                updated_order.approver_selection['original_travel_order_number_for_amendment'] = original_travel_order_number
                # Keep travel_order_number as None - will be set to "Amending-{original}" when RD approves
                if updated_order.travel_order_number and updated_order.travel_order_number.startswith('Amending-'):
                    updated_order.travel_order_number = None
                updated_order.save(update_fields=['approver_selection', 'travel_order_number'])
                print(f"DEBUG: Amendment detected. Stored original_travel_order_number: {original_travel_order_number}")
            
            # Handle signature photo for resubmission
            signature_photo = request.FILES.get("signature_photo")
            if signature_photo:
                print(f"DEBUG: Processing resubmission signature for order {order.id}")
                EmployeeSignature.objects.update_or_create(
                    order=order,
                    defaults={
                        "signed_by": request.user,
                        "signature_photo": signature_photo
                    }
                )
                print(f"DEBUG: Resubmission signature saved successfully")
            
            return Response(serializer.data)
        return Response(serializer.errors, status=400)



    
class FundListCreateView(APIView):
    def get(self, request):
        include_archived = request.query_params.get('include_archived') == 'true'
        if include_archived:
            funds = Fund.objects.all().order_by('-id')
        else:
            funds = Fund.objects.filter(is_archived=False).order_by('-id')
        serializer = FundSerializer(funds, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FundSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FundDetailView(APIView):
    def put(self, request, pk):
        fund = get_object_or_404(Fund, pk=pk)
        serializer = FundSerializer(fund, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def patch(self, request, pk):
        fund = get_object_or_404(Fund, pk=pk)
        serializer = FundSerializer(fund, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TransportationCreateView(APIView):
    def get(self, request):
        include_archived = request.query_params.get('include_archived') == 'true'
        qs = Transportation.objects.all().order_by('-id')
        if not include_archived:
            qs = qs.filter(is_archived=False)
        serializer = TransportationSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TransportationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TransportationDetailView(APIView):
    def put(self, request, pk):
        transportation = get_object_or_404(Transportation, pk=pk)
        serializer = TransportationSerializer(transportation, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        transportation = get_object_or_404(Transportation, pk=pk)
        serializer = TransportationSerializer(transportation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    
class EmployeePositionCreateView(APIView):
    def get(self, request):
        include_archived = request.query_params.get('include_archived') == 'true'
        qs = EmployeePosition.objects.all().order_by('-id')
        if not include_archived:
            qs = qs.filter(is_archived=False)
        serializer = EmployeePositionSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = EmployeePositionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmployeePositionDetailView(APIView):
    def put(self, request, pk):
        emp_position = get_object_or_404(EmployeePosition, pk=pk)
        serializer = EmployeePositionSerializer(emp_position, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        emp_position = get_object_or_404(EmployeePosition, pk=pk)
        serializer = EmployeePositionSerializer(emp_position, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PurposeCreateView(APIView):
    def get(self, request):
        include_archived = request.query_params.get('include_archived') == 'true'
        qs = Purpose.objects.all().order_by('-id')
        if not include_archived:
            qs = qs.filter(is_archived=False)
        serializer = PurposeSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PurposeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PurposeDetailView(APIView):
    def put(self, request, pk):
        purpose = get_object_or_404(Purpose, pk=pk)
        serializer = PurposeSerializer(purpose, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        purpose = get_object_or_404(Purpose, pk=pk)
        serializer = PurposeSerializer(purpose, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpecificRoleCreateView(APIView):
    def get(self, request):
        include_archived = request.query_params.get('include_archived') == 'true'
        qs = SpecificRole.objects.all().order_by('-id')
        if not include_archived:
            qs = qs.filter(is_archived=False)
        serializer = SpecificRoleSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SpecificRoleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SpecificRoleDetailView(APIView):
    def put(self, request, pk):
        specific_role = get_object_or_404(SpecificRole, pk=pk)
        serializer = SpecificRoleSerializer(specific_role, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        specific_role = get_object_or_404(SpecificRole, pk=pk)
        serializer = SpecificRoleSerializer(specific_role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# View: MY FILED TRAVEL ORDERS
class MyTravelOrdersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.user_level == 'admin':
            orders = TravelOrder.objects.select_related('purpose', 'specific_role').all().order_by('-submitted_at')
        else:
            orders = TravelOrder.objects.select_related('purpose', 'specific_role').filter(prepared_by=user).order_by('-submitted_at')

        serializer = TravelOrderSerializer(orders.distinct(), many=True, context={'request': request})
        return Response(serializer.data)

    
class TravelOrderItineraryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, travel_order_id):
        # Get the travel order to check its current status
        travel_order = get_object_or_404(TravelOrder.objects.select_related('purpose', 'specific_role'), id=travel_order_id)
        
        # Get all itineraries for this travel order
        all_itineraries = Itinerary.objects.filter(travel_order__id=travel_order_id).order_by('id')
        
        # Debug: Log the number of itineraries found
        print(f"DEBUG: Found {all_itineraries.count()} itineraries for travel order {travel_order_id}")
        
        # Return ALL itineraries for this travel order
        serializer = ItinerarySerializer(all_itineraries, many=True)
        
        return Response(serializer.data)


# View: APPROVALS TO REVIEW (only where current_approver is the logged-in user)
class TravelOrderApprovalsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        orders = TravelOrder.objects.select_related('purpose', 'specific_role').filter(
            current_approver=user
        ).exclude(
            status__in=[
                'Approved by the Regional Director',
                'Rejected by the Regional Director',
            ]
        ).order_by('-submitted_at')

        serializer = TravelOrderSerializer(orders.distinct(), many=True)
        return Response(serializer.data)



@method_decorator(csrf_exempt, name='dispatch')
class ApproveTravelOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        order = get_object_or_404(TravelOrder, pk=pk)
        user = request.user

        # Debug logging
        print(f"=== APPROVAL DEBUG ===")
        print(f"Travel Order ID: {pk}")
        print(f"Current User ID: {user.id}")
        print(f"Current User: {user.email}")
        print(f"Order Current Approver ID: {order.current_approver.id if order.current_approver else None}")
        print(f"Order Current Approver: {order.current_approver.email if order.current_approver else None}")
        print(f"Order Status: {order.status}")
        print(f"Order Approval Stage: {order.approval_stage}")
        print(f"Are they equal? {order.current_approver == user}")
        print(f"=====================")

        if order.current_approver != user:
            return Response({
                "error": "Unauthorized approval.",
                "debug": {
                    "current_user_id": user.id,
                    "current_approver_id": order.current_approver.id if order.current_approver else None,
                    "travel_order_id": pk
                }
            }, status=403)

        decision = request.data.get('decision')
        comment = request.data.get('comment')
        signature_photo = request.FILES.get('signature_photo')

        # Map employee_type to status strings from your STATUS_CHOICES
        status_map = build_status_map()


        if decision == 'approve':
            filer = order.prepared_by
            chain = get_approval_chain(filer)
            current_stage = chain[order.approval_stage] if order.approval_stage < len(chain) else 'regional'

            next_stage = order.approval_stage + 1
            next_head = get_next_head(chain, next_stage, current_user=user)

            if current_stage in status_map:
                order.status = status_map[current_stage]['approve']

            if next_head:
                order.current_approver = next_head
                order.approval_stage = next_stage
            else:
                # ✅ Final approval by Regional Director
                order.current_approver = None
                order.status = status_map['regional']['approve']

                # ✅ Auto-generate travel order number
                from .utils import generate_travel_order_number
                
                # Check if this is an amendment (has original_travel_order_number stored in approver_selection)
                original_number_for_amendment = None
                if order.approver_selection and isinstance(order.approver_selection, dict):
                    original_number_for_amendment = order.approver_selection.get('original_travel_order_number_for_amendment')
                
                if original_number_for_amendment:
                    # This is an amendment - set to "Amending-{original_number}" when RD approves
                    order.travel_order_number = generate_travel_order_number(original_number=original_number_for_amendment)
                    print(f"DEBUG: Regional Director approved amendment. Set travel_order_number to: {order.travel_order_number}")
                elif not order.travel_order_number:
                    # No number set yet and not an amendment, generate a new regular one
                    order.travel_order_number = generate_travel_order_number()

            order.is_resubmitted = False

            if signature_photo:
                Signature.objects.create(
                    order=order,
                    signed_by=user,
                    signature_photo=signature_photo,
                    comment=comment 
                )

            # Create approval snapshot with current data
            # Get current itineraries
            current_itineraries = Itinerary.objects.filter(travel_order=order)
            itineraries_data = []
            for itinerary in current_itineraries:
                itineraries_data.append({
                    'id': itinerary.id,
                    'destination': itinerary.destination,
                    'itinerary_date': itinerary.itinerary_date.isoformat() if itinerary.itinerary_date else None,
                    'departure_time': itinerary.departure_time.isoformat() if itinerary.departure_time else None,
                    'arrival_time': itinerary.arrival_time.isoformat() if itinerary.arrival_time else None,
                    'transportation': itinerary.transportation.id if itinerary.transportation else None,
                    'transportation_allowance': float(itinerary.transportation_allowance) if itinerary.transportation_allowance else 0,
                    'per_diem': float(itinerary.per_diem) if itinerary.per_diem else 0,
                    'others': float(itinerary.other_expense) if itinerary.other_expense else 0,
                    'total': float(itinerary.total_amount) if itinerary.total_amount else 0
                })
            
            # Create snapshot of current travel order data
            approval_snapshot = TravelOrderApprovalSnapshot.objects.create(
                travel_order=order,
                approved_by=user,
                approval_stage=order.approval_stage,
                approved_data={
                    'destination': order.destination,
                    'date_travel_from': order.date_travel_from.isoformat() if order.date_travel_from else None,
                    'date_travel_to': order.date_travel_to.isoformat() if order.date_travel_to else None,
                    'specific_role': order.specific_role.role_name if order.specific_role else None,
                    'purpose': order.purpose.purpose_name if order.purpose else None,
                    'fund_cluster': order.fund_cluster,
                    'mode_of_filing': order.mode_of_filing,
                    'distance': int(order.distance) if order.distance else 0,
                    'official_station': order.official_station,
                    'prepared_by_name': order.prepared_by.get_full_name() if order.prepared_by else None,
                    'prepared_by_position': order.prepared_by_position_name,
                    'employees': [emp.get_full_name() for emp in order.employees.all()]
                },
                approved_itineraries=itineraries_data
            )

            order.save()
            
            # Log approval action
            log_audit_event(
                user=user,
                action='approve',
                resource_type='travel_order',
                resource_id=order.id,
                resource_name=f"Travel to {order.destination}",
                description=f'Approved travel order to {order.destination}',
                request=request,
                metadata={'status': order.status, 'approval_stage': order.approval_stage}
            )
            
            # Notify the employee that their request was approved by this head
            if order.prepared_by:
                create_notification(
                    user=order.prepared_by,
                    travel_order=order,
                    notification_type='travel_approved',
                    title=f'Travel Request Approved by {user.get_full_name()}',
                    message=f'Your travel request to {order.destination} has been approved by {user.get_full_name()}.'
                )
            
            # If there's a next approver, notify them
            if next_head:
                create_notification(
                    user=next_head,
                    travel_order=order,
                    notification_type='new_approval_needed',
                    title=f'New Travel Request for Approval',
                    message=f'Travel request to {order.destination} by {order.prepared_by.get_full_name()} needs your approval.'
                )
            else:
                # Final approval - notify the employee again with final approval message
                if order.prepared_by:
                    create_notification(
                        user=order.prepared_by,
                        travel_order=order,
                        notification_type='travel_final_approved',
                        title=f'Travel Request Finally Approved',
                        message=f'Your travel request to {order.destination} has been finally approved. Travel order number: {order.travel_order_number}'
                    )
            
            return Response({"message": "Travel order approved."}, status=200)


        elif decision == 'reject':
            if not comment:
                return Response({"error": "Rejection comment is required."}, status=400)

            filer = order.prepared_by
            chain = get_approval_chain(filer)
            current_stage = chain[order.approval_stage] if order.approval_stage < len(chain) else 'regional'

            if current_stage in status_map:
                order.status = status_map[current_stage]['reject']
            else:
                order.status = 'Rejected'

            order.rejection_comment = comment
            order.rejected_by = user
            order.rejected_at = timezone.now()
            order.current_approver = None
            order.save()
            
            # Log rejection action
            log_audit_event(
                user=user,
                action='reject',
                resource_type='travel_order',
                resource_id=order.id,
                resource_name=f"Travel to {order.destination}",
                description=f'Rejected travel order to {order.destination}. Reason: {comment}',
                request=request,
                metadata={'status': order.status, 'comment': comment}
            )
            
            # Create notification for the employee who filed the request
            if order.prepared_by:
                create_notification(
                    user=order.prepared_by,
                    travel_order=order,
                    notification_type='travel_rejected',
                    title=f'Travel Request Rejected',
                    message=f'Your travel request to {order.destination} has been rejected. Reason: {comment}'
                )
            
            # Notify previous approvers that their approved request was rejected
            previous_signatures = Signature.objects.filter(order=order).order_by('-signed_at')
            for signature in previous_signatures:
                if signature.signed_by != user:  # Don't notify the current rejector
                    create_notification(
                        user=signature.signed_by,
                        travel_order=order,
                        notification_type='travel_rejected_by_next_approver',
                        title=f'Travel Request Rejected',
                        message=f'Travel request to {order.destination} that you approved was rejected by {user.get_full_name()}. Reason: {comment}'
                    )

            return Response({"message": "Travel order rejected."}, status=200)

        return Response({"error": "Invalid decision."}, status=400)





@method_decorator(csrf_exempt, name='dispatch')
class ResubmitTravelOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        order = get_object_or_404(TravelOrder, pk=pk)
        user = request.user

        # Ensure user is among original employees
        if not order.employees.filter(id=user.id).exists():
            return Response({"error": "Unauthorized."}, status=403)

        if 'rejected' not in order.status.lower():
            return Response({"error": "Only rejected orders can be resubmitted."}, status=400)


        # Get approval chain based on the filer
        filer = order.prepared_by
        approval_chain = get_approval_chain(filer)
        next_head = get_next_head(approval_chain, 0, current_user=filer)

        if not next_head:
            return Response({"error": "No head found to reassign this order to."}, status=400)

        # Reset important fields
        order.status = 'Travel request is placed'
        order.current_approver = next_head
        order.approval_stage = 0
        order.is_resubmitted = True
        order.rejection_comment = None
        order.rejected_at = None
        order.rejected_by = None
        order.travel_order_number = None  # Clear the old number if it existed

        order.save()

        # Notify the head about the resubmitted travel order
        create_notification(
            user=next_head,
            travel_order=order,
            notification_type='new_approval_needed',
            title=f'Travel Request Resubmitted for Approval',
            message=f'Travel request to {order.destination} by {filer.get_full_name()} has been resubmitted and needs your approval.'
        )

        return Response({
            "message": f"Travel order successfully resubmitted to {next_head.email}."
        }, status=200)




class CurrentUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "email": user.email,
            "prefix": user.prefix,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "user_level": user.user_level,
            "employee_type": user.employee_type,
            "employee_position": user.employee_position.id if user.employee_position else None,
            "employee_position_name": user.employee_position.position_name if user.employee_position else None,
            "must_change_password": user.must_change_password
        })


@api_view(['POST'])
@permission_classes([AllowAny])
def change_password_view(request):
    """Change password for first-time login users"""
    user_id = request.data.get('user_id')
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    
    if not user_id or not current_password or not new_password:
        return Response({
            "error": "User ID, current password, and new password are required"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = CustomUser.objects.get(id=user_id)
        if not user.must_change_password:
            return Response({
                "error": "User does not need to change password"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify current password
        if not user.check_password(current_password):
            return Response({
                "error": "Current password is incorrect"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set new password
        user.set_password(new_password)
        user.must_change_password = False
        user.save()
        
        # Return success response without generating tokens
        # User will need to log in again with new credentials
        return Response({
            "message": "Password changed successfully. Please log in again with your new credentials.",
            "requires_verification": False
        }, status=status.HTTP_200_OK)
        
    except CustomUser.DoesNotExist:
        return Response({
            "error": "User not found"
        }, status=status.HTTP_404_NOT_FOUND)







class EmployeeListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        users = CustomUser.objects.all().order_by('-id')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        # Only allow admin users to create new employees
        if request.user.user_level not in ['admin', 'director']:
            return Response({'error': 'Only administrators can create new users'}, status=status.HTTP_403_FORBIDDEN)
        
        # Convert QueryDict to regular dict and handle list values properly
        data = {}
        for key, value in request.data.items():
            if isinstance(value, list) and len(value) == 1:
                # Extract single value from list (Django form processing creates lists)
                data[key] = value[0]
            else:
                data[key] = value
        
        # Generate temporary password
        temporary_password = generate_temporary_password()
        data['password'] = temporary_password
        
        serializer = UserSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Create temporary password record with 10-minute expiration
            TemporaryPassword.objects.create(
                user=user,
                password=temporary_password,
                expires_at=timezone.now() + timedelta(minutes=10)
            )
            
            # Send welcome email with credentials
            email_sent = send_user_creation_email(user, temporary_password)
            
            # Log user creation
            log_audit_event(
                user=request.user,
                action='create',
                resource_type='user',
                resource_id=user.id,
                resource_name=f"{user.first_name} {user.last_name}",
                description=f'Created user account for {user.first_name} {user.last_name}',
                request=request,
                metadata={
                    'email': user.email, 
                    'user_level': user.user_level,
                    'email_sent': email_sent,
                    'temporary_password_expires': (timezone.now() + timedelta(minutes=10)).isoformat()
                }
            )
            
            response_data = UserSerializer(user).data
            response_data['temporary_password'] = temporary_password
            response_data['email_sent'] = email_sent
            response_data['password_expires_at'] = (timezone.now() + timedelta(minutes=10)).isoformat()
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HeadListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get all users with head level for prepared by dropdown"""
        heads = CustomUser.objects.filter(user_level='head').order_by('first_name', 'last_name')
        serializer = UserSerializer(heads, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Log user creation
            log_audit_event(
                user=request.user,
                action='create',
                resource_type='user',
                resource_id=user.id,
                resource_name=f"{user.first_name} {user.last_name}",
                description=f'Created user account for {user.first_name} {user.last_name}',
                request=request,
                metadata={'email': user.email, 'user_level': user.user_level}
            )
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DirectorListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get all users with director level for agency head and approved dropdowns"""
        directors = CustomUser.objects.filter(user_level='director').order_by('first_name', 'last_name')
        serializer = UserSerializer(directors, many=True)
        return Response(serializer.data)


class EmployeeDetailUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            user = CustomUser.objects.get(id=pk)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        if 'password' in data and not data['password']:
            data.pop('password')
        elif 'password' in data:
            data['password'] = make_password(data['password'])

        serializer = UserSerializer(user, data=data, partial=True)
        if serializer.is_valid():
            updated_user = serializer.save()
            
            # Log user update
            log_audit_event(
                user=request.user,
                action='update',
                resource_type='user',
                resource_id=updated_user.id,
                resource_name=f"{updated_user.first_name} {updated_user.last_name}",
                description=f'Updated user account for {updated_user.first_name} {updated_user.last_name}',
                request=request,
                metadata={'email': updated_user.email, 'user_level': updated_user.user_level}
            )
            
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class AdminTravelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        travel = TravelOrder.objects.select_related('purpose', 'specific_role').all().order_by('-submitted_at')
        serializer = TravelOrderSerializer(travel, many=True, context={'request': request})
        return Response(serializer.data)
    

class AfterTravelReportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Get Regional Director
        regional_director = CustomUser.objects.filter(user_level='director').first()
        
        # Parse JSON fields
        data = request.data.copy()
        if isinstance(data.get('prepared_by'), str):
            try:
                data['prepared_by'] = json.loads(data['prepared_by'])
            except json.JSONDecodeError:
                return Response({'prepared_by': ['Invalid prepared_by format.']}, status=400)
        
        # Use office_head from frontend if provided, otherwise fallback to logic
        if not data.get('office_head'):
            # Use the first selected head from prepared_by as office_head
            if data.get('prepared_by') and len(data['prepared_by']) > 0:
                # Get the first head from the prepared_by list
                first_head_id = data['prepared_by'][0]
                try:
                    first_head = CustomUser.objects.get(id=first_head_id, user_level='head')
                    data['office_head'] = first_head.id
                except CustomUser.DoesNotExist:
                    # Fallback to TMSD head if the selected head is not found or not a head
                    tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                    if tmsd_head:
                        data['office_head'] = tmsd_head.id
            else:
                # Fallback to TMSD head if no prepared_by is provided
                tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                if tmsd_head:
                    data['office_head'] = tmsd_head.id
        
        if regional_director:
            data['regional_director'] = regional_director.id
        
        # Handle file uploads
        photo_files = request.FILES.getlist('photo_documentation')
        
        # Validate photo files
        for photo in photo_files:
            # Validate file type for photos
            allowed_photo_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff', 'image/webp']
            if photo.content_type not in allowed_photo_types:
                return Response({
                    'error': f'Invalid photo file type: {photo.name}. Only image files (JPG, PNG, GIF, BMP, TIFF, WEBP) are allowed.'
                }, status=400)
            
            # Validate file size (5MB limit for photos)
            max_photo_size = 5 * 1024 * 1024  # 5MB
            if photo.size > max_photo_size:
                return Response({
                    'error': f'Photo file too large: {photo.name}. Maximum size is 5MB.'
                }, status=400)
        
        
        # Store file paths in JSON fields
        photo_paths = []
        
        # Save photo files to media directory
        for photo in photo_files:
            # Create a unique filename to avoid conflicts
            import uuid
            file_extension = os.path.splitext(photo.name)[1]
            unique_filename = f"evidence/after_travel_photos/{uuid.uuid4()}{file_extension}"
            photo_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(photo_path), exist_ok=True)
            
            # Save file
            with open(photo_path, 'wb+') as destination:
                for chunk in photo.chunks():
                    destination.write(chunk)
            
            # Store relative path for database
            photo_paths.append(unique_filename)
        
        
        data['photo_documentation'] = photo_paths
        
        serializer = AfterTravelReportSerializer(data=data)
        if serializer.is_valid():
            after_travel_report = serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def get(self, request, pk=None):
        if pk:
            after_travel_report = get_object_or_404(AfterTravelReport, pk=pk)
            serializer = AfterTravelReportSerializer(after_travel_report)
            return Response(serializer.data)
        else:
            after_travel_reports = AfterTravelReport.objects.all()
            serializer = AfterTravelReportSerializer(after_travel_reports, many=True)
            return Response(serializer.data)

class SubmitAfterTravelReportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Check if travel order has a travel order number
        if not travel_order.travel_order_number:
            return Response({'error': 'Travel order must be approved before liquidation can be submitted.'}, status=400)

        # Check if travel order is within 3 months of travel end date
        now = timezone.now().date()
        three_months_ago = now - timedelta(days=90)
        if travel_order.date_travel_to < three_months_ago:
            return Response({
                'error': f'Liquidation period has expired. Travel ended on {travel_order.date_travel_to}, but liquidation must be submitted within 3 months of travel completion.'
            }, status=400)

        # Check if liquidation already exists and has after travel report
        if hasattr(travel_order, 'liquidation') and travel_order.liquidation.after_travel_report:
            return Response({'error': 'After travel report already exists for this travel order.'}, status=400)

        # Handle after travel report creation
        after_travel_report_data = request.data.get('after_travel_report')
        
        if not after_travel_report_data:
            return Response({'error': 'After travel report data is required.'}, status=400)
        
        if isinstance(after_travel_report_data, str):
            try:
                after_travel_report_data = json.loads(after_travel_report_data)
            except json.JSONDecodeError:
                return Response({'after_travel_report': ['Invalid after_travel_report format.']}, status=400)
        
        # Get Regional Director
        regional_director = CustomUser.objects.filter(user_level='director').first()
        
        # Use office_head from frontend if provided, otherwise fallback to logic
        if not after_travel_report_data.get('office_head'):
            # Use the first selected head from prepared_by as office_head
            if after_travel_report_data.get('prepared_by') and len(after_travel_report_data['prepared_by']) > 0:
                # Get the first head from the prepared_by list
                first_head_id = after_travel_report_data['prepared_by'][0]
                try:
                    first_head = CustomUser.objects.get(id=first_head_id, user_level='head')
                    after_travel_report_data['office_head'] = first_head.id
                except CustomUser.DoesNotExist:
                    # Fallback to TMSD head if the selected head is not found or not a head
                    tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                    if tmsd_head:
                        after_travel_report_data['office_head'] = tmsd_head.id
            else:
                # Fallback to TMSD head if no prepared_by is provided
                tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                if tmsd_head:
                    after_travel_report_data['office_head'] = tmsd_head.id
        
        if regional_director:
            after_travel_report_data['regional_director'] = regional_director.id
        
        # Handle file uploads for after travel report
        photo_files = request.FILES.getlist('photo_documentation')
        
        # Check if there's an existing draft with photos in Liquidation
        liquidation = None
        draft_data = None
        try:
            liquidation = Liquidation.objects.get(travel_order=travel_order)
            draft_data = liquidation.after_travel_report_draft
        except Liquidation.DoesNotExist:
            pass
        
        # If no new files are provided but draft exists with photos, use draft photos
        if not photo_files and draft_data and draft_data.get('photo_documentation'):
            # Use existing draft photos
            photo_paths = draft_data['photo_documentation'] if isinstance(draft_data['photo_documentation'], list) else []
        else:
            # Validate photo files
            for photo in photo_files:
                # Validate file type for photos
                allowed_photo_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff', 'image/webp']
                if photo.content_type not in allowed_photo_types:
                    return Response({
                        'error': f'Invalid photo file type: {photo.name}. Only image files (JPG, PNG, GIF, BMP, TIFF, WEBP) are allowed.'
                    }, status=400)
                
                # Validate file size (5MB limit for photos)
                max_photo_size = 5 * 1024 * 1024  # 5MB
                if photo.size > max_photo_size:
                    return Response({
                        'error': f'Photo file too large: {photo.name}. Maximum size is 5MB.'
                    }, status=400)
            
            
            # Store file paths by saving actual files
            photo_paths = []
            
            # Save new photo files to media directory
            # Note: When new photos are uploaded, we only use the new photos (not draft photos)
            # Draft photos are only used if no new photos are uploaded (handled above)
            import uuid
            for photo in photo_files:
                # Create a unique filename to avoid conflicts
                file_extension = os.path.splitext(photo.name)[1]
                unique_filename = f"evidence/after_travel_photos/{uuid.uuid4()}{file_extension}"
                photo_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(photo_path), exist_ok=True)
                
                # Save file
                with open(photo_path, 'wb+') as destination:
                    for chunk in photo.chunks():
                        destination.write(chunk)
                
                # Store relative path for database
                photo_paths.append(unique_filename)
        
        
        after_travel_report_data['photo_documentation'] = photo_paths
        
        after_travel_report_serializer = AfterTravelReportSerializer(data=after_travel_report_data)
        if after_travel_report_serializer.is_valid():
            after_travel_report = after_travel_report_serializer.save()
            
            # Clear draft data from Liquidation after successful submission
            if liquidation and liquidation.after_travel_report_draft:
                liquidation.after_travel_report_draft = {}
                liquidation.save()
            
            # Create or update liquidation with after travel report
            # Calculate deadline: 90 days from travel end date (date_travel_to)
            # Convert date_travel_to to datetime at end of day for consistent calculation
            from datetime import datetime, time as dt_time
            travel_end_datetime = timezone.make_aware(datetime.combine(travel_order.date_travel_to, dt_time.max))
            liquidation_deadline = travel_end_datetime + timedelta(days=90)
            
            liquidation, created = Liquidation.objects.get_or_create(
                travel_order=travel_order,
                defaults={
                    'uploaded_by': request.user,
                    'liquidation_deadline': liquidation_deadline  # 90 days from travel end date
                }
            )
            
            # Set deadline if liquidation already existed but doesn't have one
            if not created and not liquidation.liquidation_deadline:
                liquidation.liquidation_deadline = liquidation_deadline
                liquidation.save()
            
            # Update only the essential fields to avoid foreign key issues
            liquidation.after_travel_report = after_travel_report
            try:
                liquidation.after_travel_report_status = 'pending_review'
            except AttributeError:
                print("DEBUG: after_travel_report_status field doesn't exist yet")
            
            # Set the reviewer for after travel report
            try:
                if after_travel_report.office_head:
                    liquidation.after_travel_report_reviewer = after_travel_report.office_head
                    # Assign the reviewer (already handled by serializer)
                else:
                    print("DEBUG: No office_head user selected for after travel report")
            except AttributeError:
                print("DEBUG: after_travel_report_reviewer field doesn't exist yet")
            
            # Save only the essential fields, avoiding foreign key fields entirely
            try:
                liquidation.save(update_fields=['after_travel_report', 'after_travel_report_status', 'after_travel_report_reviewer'])
            except AttributeError:
                # Fallback if new fields don't exist yet
                liquidation.save(update_fields=['after_travel_report', 'after_travel_report_status'])
            
            try:
                liquidation.update_status()  # Set proper status based on components
            except Exception as e:
                print(f"DEBUG: update_status failed: {e}")
                # Fallback: set status manually
                liquidation.status = 'Pending'
                liquidation.save()
            
            print(f"DEBUG: After travel report submitted. Liquidation ID: {liquidation.id}, Status: {liquidation.status}")
            
            # Notify bookkeepers about new after travel report
            try:
                bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
                for bookkeeper in bookkeepers:
                    create_notification(
                        user=bookkeeper,
                        travel_order=travel_order,
                        notification_type='liquidation_needs_review',
                        title=f'After Travel Report Submitted',
                        message=f'After travel report for travel order {travel_order.travel_order_number} has been submitted and needs your review.'
                    )
                print("DEBUG: Bookkeepers notified about new after travel report")
            except Exception as e:
                print(f"DEBUG: Error notifying bookkeepers: {e}")
                # Don't fail the submission if notification fails
            
            return Response({
                'message': 'After travel report submitted successfully.',
                'after_travel_report': AfterTravelReportSerializer(after_travel_report).data
            }, status=201)
        else:
            return Response(after_travel_report_serializer.errors, status=400)


class SubmitCertificateOfTravelView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Check if travel order has a travel order number
        if not travel_order.travel_order_number:
            return Response({'error': 'Travel order must be approved before liquidation can be submitted.'}, status=400)

        # Check if travel order is within 3 months of travel end date
        now = timezone.now().date()
        three_months_ago = now - timedelta(days=90)
        if travel_order.date_travel_to < three_months_ago:
            return Response({
                'error': f'Liquidation period has expired. Travel ended on {travel_order.date_travel_to}, but liquidation must be submitted within 3 months of travel completion.'
            }, status=400)

        # Debug: Print received data
        print("=== CERTIFICATE OF TRAVEL SUBMISSION DEBUG ===")
        print(f"Request data: {dict(request.data)}")
        print(f"Request FILES: {dict(request.FILES)}")
        
        # Debug: List available users
        all_users = CustomUser.objects.all().values('id', 'email', 'first_name', 'last_name', 'user_level')
        print(f"Available users: {list(all_users)}")

        # Parse JSON fields and convert to regular dict
        data = dict(request.data)
        
        # Handle single-value fields that come as lists from QueryDict
        for field in ['fund_cluster', 'station', 'evidence_type', 'explanations_justifications', 'refund_amount', 'or_number', 'or_date']:
            if field in data and isinstance(data[field], list) and len(data[field]) == 1:
                data[field] = data[field][0]
        
        # Handle deviation_types as JSON array
        if 'deviation_types' in data:
            if isinstance(data['deviation_types'], str):
                try:
                    data['deviation_types'] = json.loads(data['deviation_types'])
                except json.JSONDecodeError:
                    data['deviation_types'] = []
            elif isinstance(data['deviation_types'], list) and len(data['deviation_types']) == 1:
                try:
                    data['deviation_types'] = json.loads(data['deviation_types'][0])
                except json.JSONDecodeError:
                    data['deviation_types'] = []
        
        # Handle respectfully_submitted field
        if isinstance(data.get('respectfully_submitted'), str):
            try:
                data['respectfully_submitted'] = json.loads(data['respectfully_submitted'])
            except json.JSONDecodeError:
                return Response({'respectfully_submitted': ['Invalid respectfully_submitted format.']}, status=400)
        elif isinstance(data.get('respectfully_submitted'), list):
            # Handle case where it's already a list (from QueryDict)
            try:
                # If it's a list with one string element, parse it
                if len(data['respectfully_submitted']) == 1 and isinstance(data['respectfully_submitted'][0], str):
                    data['respectfully_submitted'] = json.loads(data['respectfully_submitted'][0])
                # If it's already a list of integers, use it as is
                elif all(isinstance(x, int) for x in data['respectfully_submitted']):
                    data['respectfully_submitted'] = data['respectfully_submitted']
                else:
                    # Handle nested arrays - flatten them
                    parsed_list = []
                    for item in data['respectfully_submitted']:
                        if isinstance(item, str):
                            try:
                                parsed_item = json.loads(item)
                                if isinstance(parsed_item, list):
                                    parsed_list.extend(parsed_item)
                                else:
                                    parsed_list.append(parsed_item)
                            except json.JSONDecodeError:
                                parsed_list.append(item)
                        elif isinstance(item, list):
                            parsed_list.extend(item)
                        else:
                            parsed_list.append(item)
                    data['respectfully_submitted'] = parsed_list
            except (json.JSONDecodeError, TypeError):
                return Response({'respectfully_submitted': ['Invalid respectfully_submitted format.']}, status=400)
        
        # Handle approved field if it's a list
        if 'approved' in data and isinstance(data['approved'], list) and len(data['approved']) > 0:
            data['approved'] = data['approved'][0]
        
        # Validate that the approved user exists
        if 'approved' in data and data['approved']:
            try:
                approved_user = CustomUser.objects.get(id=data['approved'])
                print(f"DEBUG: Approved user found: {approved_user.email} (ID: {approved_user.id})")
            except CustomUser.DoesNotExist:
                print(f"DEBUG: User with ID {data['approved']} does not exist")
                return Response({'error': f'Selected user with ID {data["approved"]} does not exist.'}, status=400)
        
        # Get Regional Director for agency_head only (not for approved)
        regional_director = CustomUser.objects.filter(user_level='director').first()
        if regional_director:
            data['agency_head'] = regional_director.id
        else:
            return Response({'error': 'No Regional Director found in the system.'}, status=400)
        
        # Set travel order number and dates
        data['travel_order_number'] = travel_order.travel_order_number
        data['date_travel_from'] = travel_order.date_travel_from
        data['date_travel_to'] = travel_order.date_travel_to
        
        # Convert or_date string to date object if present
        if 'or_date' in data and data['or_date']:
            try:
                from datetime import datetime
                data['or_date'] = datetime.strptime(data['or_date'], '%Y-%m-%d').date()
            except ValueError:
                return Response({'or_date': ['Invalid date format. Use YYYY-MM-DD.']}, status=400)
        
        # Ensure respectfully_submitted is a flat list of integers
        if 'respectfully_submitted' in data:
            respectfully_submitted = data['respectfully_submitted']
            print(f"Before final processing: {respectfully_submitted} (type: {type(respectfully_submitted)})")
            
            # Final flattening to ensure it's a flat list
            if isinstance(respectfully_submitted, list):
                flattened = []
                for item in respectfully_submitted:
                    if isinstance(item, list):
                        flattened.extend(item)
                    else:
                        flattened.append(item)
                data['respectfully_submitted'] = flattened
                print(f"After final processing: {flattened}")
            else:
                print(f"Unexpected type: {type(respectfully_submitted)}")
        
        print(f"Final data for serializer: {data}")
        
        # Create certificate of travel
        certificate_serializer = CertificateOfTravelSerializer(data=data)
        if certificate_serializer.is_valid():
            certificate_of_travel = certificate_serializer.save()
            
            # Create or update liquidation with certificate of travel
            # Calculate deadline: 90 days from travel end date (date_travel_to)
            # Convert date_travel_to to datetime at end of day for consistent calculation
            from datetime import datetime, time as dt_time
            travel_end_datetime = timezone.make_aware(datetime.combine(travel_order.date_travel_to, dt_time.max))
            liquidation_deadline = travel_end_datetime + timedelta(days=90)
            
            liquidation, created = Liquidation.objects.get_or_create(
                travel_order=travel_order,
                defaults={
                    'uploaded_by': request.user,
                    'liquidation_deadline': liquidation_deadline  # 90 days from travel end date
                }
            )
            
            # Set deadline if liquidation already existed but doesn't have one
            if not created and not liquidation.liquidation_deadline:
                liquidation.liquidation_deadline = liquidation_deadline
                liquidation.save()
            
            # Update only the essential fields to avoid foreign key issues
            liquidation.certificate_of_travel = certificate_of_travel
            try:
                liquidation.certificate_of_travel_status = 'pending_review'
            except AttributeError:
                print("DEBUG: certificate_of_travel_status field doesn't exist yet")
            
            # Set the reviewer for certificate of travel
            try:
                if certificate_of_travel.approved:
                    liquidation.certificate_of_travel_reviewer = certificate_of_travel.approved
                    # Assign the reviewer (already handled by serializer)
                else:
                    print("DEBUG: No approved user selected for certificate of travel")
            except AttributeError:
                print("DEBUG: certificate_of_travel_reviewer field doesn't exist yet")
            
            # Save only the essential fields, avoiding foreign key fields entirely
            try:
                liquidation.save(update_fields=['certificate_of_travel', 'certificate_of_travel_status', 'certificate_of_travel_reviewer'])
            except AttributeError:
                # Fallback if new fields don't exist yet
                liquidation.save(update_fields=['certificate_of_travel', 'certificate_of_travel_status'])
            
            try:
                liquidation.update_status()  # Set proper status based on components
            except Exception as e:
                print(f"DEBUG: update_status failed: {e}")
                # Fallback: set status manually
                liquidation.status = 'Pending'
                liquidation.save()
            
            # Notify bookkeepers about new certificate of travel
            try:
                bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
                for bookkeeper in bookkeepers:
                    create_notification(
                        user=bookkeeper,
                        travel_order=travel_order,
                        notification_type='liquidation_needs_review',
                        title=f'Certificate of Travel Submitted',
                        message=f'Certificate of travel for travel order {travel_order.travel_order_number} has been submitted and needs your review.'
                    )
                print("DEBUG: Bookkeepers notified about new certificate of travel")
            except Exception as e:
                print(f"DEBUG: Error notifying bookkeepers: {e}")
                # Don't fail the submission if notification fails
            
            return Response({
                'message': 'Certificate of travel submitted successfully.',
                'certificate_of_travel': CertificateOfTravelSerializer(certificate_of_travel).data
            }, status=201)
        else:
            print(f"Certificate serializer errors: {certificate_serializer.errors}")
            return Response(certificate_serializer.errors, status=400)


class SubmitCertificateOfAppearanceView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Check if travel order has a travel order number
        if not travel_order.travel_order_number:
            return Response({'error': 'Travel order must be approved before liquidation can be submitted.'}, status=400)

        # Check if travel order is within 3 months of travel end date
        now = timezone.now().date()
        three_months_ago = now - timedelta(days=90)
        if travel_order.date_travel_to < three_months_ago:
            return Response({
                'error': f'Liquidation period has expired. Travel ended on {travel_order.date_travel_to}, but liquidation must be submitted within 3 months of travel completion.'
            }, status=400)

        # Check if there's a draft file we can use
        draft_cert = CertificateOfAppearance.objects.filter(travel_order=travel_order, is_draft=True).first()
        
        certificate_file = request.FILES.get('certificate_of_appearance')
        if not certificate_file:
            # If no new file provided, check if we can use the draft file
            if draft_cert and draft_cert.certificate_of_appearance:
                certificate_file = draft_cert.certificate_of_appearance
            else:
                return Response({'error': 'Certificate of appearance file is required.'}, status=400)
        
        # Validate file type - only allow PDF and image files (for new uploads only, drafts are already validated)
        if request.FILES.get('certificate_of_appearance'):  # Only validate if it's a new upload
            allowed_types = [
                'application/pdf',
                'image/jpeg',
                'image/jpg',
                'image/png', 
                'image/gif',
                'image/bmp',
                'image/tiff',
                'image/webp'
            ]
            
            if certificate_file.content_type not in allowed_types:
                return Response({
                    'error': 'Invalid file type. Only PDF and image files (JPG, PNG, GIF, BMP, TIFF, WEBP) are allowed.'
                }, status=400)
            
            # Validate file size (10MB limit)
            max_size = 10 * 1024 * 1024  # 10MB
            if certificate_file.size > max_size:
                return Response({
                    'error': 'File size too large. Maximum size is 10MB.'
                }, status=400)

        # Create or update liquidation with certificate of appearance
        # Calculate deadline: 90 days from travel end date (date_travel_to)
        # Convert date_travel_to to datetime at end of day for consistent calculation
        from datetime import datetime, time as dt_time
        travel_end_datetime = timezone.make_aware(datetime.combine(travel_order.date_travel_to, dt_time.max))
        liquidation_deadline = travel_end_datetime + timedelta(days=90)
        
        liquidation, created = Liquidation.objects.get_or_create(
            travel_order=travel_order,
            defaults={
                'uploaded_by': request.user,
                'liquidation_deadline': liquidation_deadline  # 90 days from travel end date
            }
        )
        
        # Set deadline if liquidation already existed but doesn't have one
        if not created and not liquidation.liquidation_deadline:
            liquidation.liquidation_deadline = liquidation_deadline
            liquidation.save()
        
        # Update only the essential fields to avoid foreign key issues
        liquidation.certificate_of_appearance = certificate_file
        try:
            liquidation.certificate_of_appearance_status = 'submitted'
        except AttributeError:
            print("DEBUG: certificate_of_appearance_status field doesn't exist yet")
        
        # Save only the essential fields, avoiding foreign key fields entirely
        liquidation.save(update_fields=['certificate_of_appearance', 'certificate_of_appearance_status'])
        
        # Clear any draft certificate of appearance after successful submission
        if draft_cert:
            draft_cert.delete()
        
        try:
            liquidation.update_status()  # Set proper status based on components
        except Exception as e:
            print(f"DEBUG: update_status failed: {e}")
            # Fallback: set status manually
            liquidation.status = 'Pending'
            liquidation.save()
        
        # Notify bookkeepers about new certificate of appearance
        try:
            bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
            for bookkeeper in bookkeepers:
                create_notification(
                    user=bookkeeper,
                    travel_order=travel_order,
                    notification_type='liquidation_needs_review',
                    title=f'Certificate of Appearance Submitted',
                    message=f'Certificate of appearance for travel order {travel_order.travel_order_number} has been submitted and needs your review.'
                )
            print("DEBUG: Bookkeepers notified about new certificate of appearance")
        except Exception as e:
            print(f"DEBUG: Error notifying bookkeepers: {e}")
            # Don't fail the submission if notification fails
        
        return Response({
            'message': 'Certificate of appearance submitted successfully.',
            'certificate_of_appearance': liquidation.certificate_of_appearance.url if liquidation.certificate_of_appearance else None
        }, status=201)


class LiquidationReviewerView(APIView):
    """View for reviewers to see pending liquidations assigned to them"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # For now, return empty list until migration is run
        # This prevents the NameError while we set up the database
        try:
            # Get liquidations where user is assigned as reviewer
            liquidations = Liquidation.objects.filter(
                models.Q(after_travel_report_reviewer=user) | 
                models.Q(certificate_of_travel_reviewer=user)
            ).select_related('travel_order', 'uploaded_by', 'after_travel_report', 'certificate_of_travel').order_by('-submitted_at')
            
            # Filter by status
            status_filter = request.query_params.get('status')
            if status_filter:
                if status_filter == 'pending_review':
                    liquidations = liquidations.filter(
                        models.Q(after_travel_report_status='pending_review') |
                        models.Q(certificate_of_travel_status='pending_review')
                    )
                elif status_filter == 'reviewer_approved':
                    liquidations = liquidations.filter(
                        models.Q(after_travel_report_status='reviewer_approved') |
                        models.Q(certificate_of_travel_status='reviewer_approved')
                    )
                elif status_filter == 'reviewer_rejected':
                    liquidations = liquidations.filter(
                        models.Q(after_travel_report_status='reviewer_rejected') |
                        models.Q(certificate_of_travel_status='reviewer_rejected')
                    )
            
            # Serialize the data
            liquidation_data = []
            for liquidation in liquidations:
                data = {
                    'id': liquidation.id,
                    'travel_order': {
                        'id': liquidation.travel_order.id,
                        'travel_order_number': liquidation.travel_order.travel_order_number,
                        'destination': liquidation.travel_order.destination,
                        'date_travel_from': liquidation.travel_order.date_travel_from,
                        'date_travel_to': liquidation.travel_order.date_travel_to,
                    },
                    'uploaded_by': {
                        'id': liquidation.uploaded_by.id,
                        'full_name': liquidation.uploaded_by.full_name,
                        'first_name': liquidation.uploaded_by.first_name,
                        'last_name': liquidation.uploaded_by.last_name,
                    },
                    'after_travel_report': {
                        'status': liquidation.after_travel_report_status,
                        'reviewer': liquidation.after_travel_report_reviewer.id if liquidation.after_travel_report_reviewer else None,
                        'reviewer_name': f"{liquidation.after_travel_report_reviewer.first_name} {liquidation.after_travel_report_reviewer.last_name}" if liquidation.after_travel_report_reviewer else None,
                        'submitted_at': liquidation.after_travel_report.created_at if liquidation.after_travel_report else None,
                    } if liquidation.after_travel_report else None,
                    'certificate_of_travel': {
                        'status': liquidation.certificate_of_travel_status,
                        'reviewer': liquidation.certificate_of_travel_reviewer.id if liquidation.certificate_of_travel_reviewer else None,
                        'reviewer_name': f"{liquidation.certificate_of_travel_reviewer.first_name} {liquidation.certificate_of_travel_reviewer.last_name}" if liquidation.certificate_of_travel_reviewer else None,
                        'submitted_at': liquidation.certificate_of_travel.created_at if liquidation.certificate_of_travel else None,
                    } if liquidation.certificate_of_travel else None,
                    'certificate_of_appearance': {
                        'status': liquidation.certificate_of_appearance_status,
                        'submitted_at': liquidation.submitted_at,
                    } if liquidation.certificate_of_appearance else None,
                    'submitted_at': liquidation.submitted_at,
                }
                liquidation_data.append(data)
            
            return Response(liquidation_data)
        except AttributeError as e:
            # Handle case where new fields don't exist yet
            print(f"DEBUG: AttributeError in LiquidationReviewerView: {e}")
            return Response([])


class LiquidationReviewerHistoryView(APIView):
    """View for reviewers to see history of their approved/rejected liquidations"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        
        try:
            # Get liquidations where user is assigned as reviewer and status is approved or rejected (not pending)
            liquidations = Liquidation.objects.filter(
                (models.Q(after_travel_report_reviewer=user) & 
                 (models.Q(after_travel_report_status='reviewer_approved') | 
                  models.Q(after_travel_report_status='reviewer_rejected'))) |
                (models.Q(certificate_of_travel_reviewer=user) & 
                 (models.Q(certificate_of_travel_status='reviewer_approved') | 
                  models.Q(certificate_of_travel_status='reviewer_rejected')))
            ).select_related('travel_order', 'uploaded_by', 'after_travel_report', 'certificate_of_travel').order_by('-submitted_at')
            
            # Serialize the data
            liquidation_data = []
            for liquidation in liquidations:
                data = {
                    'id': liquidation.id,
                    'travel_order': {
                        'id': liquidation.travel_order.id,
                        'travel_order_number': liquidation.travel_order.travel_order_number,
                        'destination': liquidation.travel_order.destination,
                        'date_travel_from': liquidation.travel_order.date_travel_from,
                        'date_travel_to': liquidation.travel_order.date_travel_to,
                    },
                    'uploaded_by': {
                        'id': liquidation.uploaded_by.id,
                        'full_name': liquidation.uploaded_by.full_name,
                    },
                    'after_travel_report': {
                        'status': liquidation.after_travel_report_status,
                        'reviewer': liquidation.after_travel_report_reviewer.id if liquidation.after_travel_report_reviewer else None,
                        'reviewer_name': f"{liquidation.after_travel_report_reviewer.first_name} {liquidation.after_travel_report_reviewer.last_name}" if liquidation.after_travel_report_reviewer else None,
                    } if liquidation.after_travel_report else None,
                    'certificate_of_travel': {
                        'status': liquidation.certificate_of_travel_status,
                        'reviewer': liquidation.certificate_of_travel_reviewer.id if liquidation.certificate_of_travel_reviewer else None,
                        'reviewer_name': f"{liquidation.certificate_of_travel_reviewer.first_name} {liquidation.certificate_of_travel_reviewer.last_name}" if liquidation.certificate_of_travel_reviewer else None,
                    } if liquidation.certificate_of_travel else None,
                    'certificate_of_appearance': {
                        'status': liquidation.certificate_of_appearance_status,
                    } if liquidation.certificate_of_appearance else None,
                    'submitted_at': liquidation.submitted_at,
                }
                liquidation_data.append(data)
            
            return Response(liquidation_data)
        except AttributeError as e:
            print(f"DEBUG: AttributeError in LiquidationReviewerHistoryView: {e}")
            return Response([])


class LiquidationComponentReviewView(APIView):
    """View for reviewers to approve/reject specific liquidation components"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, liquidation_id, component_type):
        """
        Approve or reject a liquidation component
        component_type: 'after_travel_report' or 'certificate_of_travel'
        """
        try:
            liquidation = Liquidation.objects.get(id=liquidation_id)
        except Liquidation.DoesNotExist:
            return Response({'error': 'Liquidation not found'}, status=404)
        
        # Validate component type
        if component_type not in ['after_travel_report', 'certificate_of_travel']:
            return Response({'error': 'Invalid component type'}, status=400)
        
        # Check if user is the assigned reviewer
        if component_type == 'after_travel_report':
            if liquidation.after_travel_report_reviewer != request.user:
                return Response({'error': 'Unauthorized - not assigned as reviewer'}, status=403)
        elif component_type == 'certificate_of_travel':
            if liquidation.certificate_of_travel_reviewer != request.user:
                return Response({'error': 'Unauthorized - not assigned as reviewer'}, status=403)
        
        approve = request.data.get('approve', False)
        comment = request.data.get('comment', '')
        signature_photo = request.FILES.get('signature_photo')
        
        if component_type == 'after_travel_report':
            liquidation.after_travel_report_reviewed_by = request.user
            liquidation.after_travel_report_reviewed_at = timezone.now()
            liquidation.after_travel_report_reviewer_comment = comment
            if signature_photo:
                liquidation.after_travel_report_reviewer_signature = signature_photo
            
            if approve:
                liquidation.after_travel_report_status = 'reviewer_approved'
            else:
                liquidation.after_travel_report_status = 'reviewer_rejected'
                
        elif component_type == 'certificate_of_travel':
            liquidation.certificate_of_travel_reviewed_by = request.user
            liquidation.certificate_of_travel_reviewed_at = timezone.now()
            liquidation.certificate_of_travel_reviewer_comment = comment
            if signature_photo:
                liquidation.certificate_of_travel_reviewer_signature = signature_photo
            
            if approve:
                liquidation.certificate_of_travel_status = 'reviewer_approved'
            else:
                liquidation.certificate_of_travel_status = 'reviewer_rejected'
        
        liquidation.save()
        
        # Update overall liquidation status
        try:
            liquidation.update_status()
        except Exception as e:
            print(f"DEBUG: update_status failed: {e}")
        
        # Send notifications
        component_display_name = component_type.replace("_", " ").title()
        if approve:
            # Notify employee about approval
            try:
                create_notification(
                    user=liquidation.uploaded_by,
                    travel_order=liquidation.travel_order,
                    notification_type='component_approved',
                    title=f'{component_display_name} Approved by Reviewer',
                    message=f'Your {component_display_name.lower()} for travel order {liquidation.travel_order.travel_order_number} has been approved by the reviewer.'
                )
                print(f"DEBUG: Employee notified of {component_display_name} approval successfully")
            except Exception as e:
                print(f"DEBUG: Error notifying employee of approval: {e}")
                # Don't fail the approval if notification fails
            
            # Notify bookkeepers that component is ready for their review
            try:
                bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
                print(f"DEBUG: Found {bookkeepers.count()} bookkeepers to notify")
                for bookkeeper in bookkeepers:
                    create_notification(
                        user=bookkeeper,
                        travel_order=liquidation.travel_order,
                        notification_type='new_approval_needed',
                        title=f'{component_display_name} Ready for Bookkeeper Review',
                        message=f'{component_display_name} for travel order {liquidation.travel_order.travel_order_number} has been approved by reviewer and is ready for bookkeeper review.'
                    )
                print("DEBUG: Bookkeepers notified successfully")
            except Exception as e:
                print(f"DEBUG: Error notifying bookkeepers: {e}")
                # Don't fail the approval if notification fails
        else:
            # Notify employee about rejection
            try:
                create_notification(
                    user=liquidation.uploaded_by,
                    travel_order=liquidation.travel_order,
                    notification_type='component_rejected',
                    title=f'{component_display_name} Rejected by Reviewer',
                    message=f'Your {component_display_name.lower()} for travel order {liquidation.travel_order.travel_order_number} has been rejected by the reviewer. Reason: {comment if comment else "No reason provided"}'
                )
                print(f"DEBUG: Employee notified of {component_display_name} rejection successfully")
            except Exception as e:
                print(f"DEBUG: Error notifying employee of rejection: {e}")
                # Don't fail the rejection if notification fails
        
        action = 'approved' if approve else 'rejected'
        return Response({
            'message': f'{component_type.replace("_", " ").title()} {action} successfully',
            'status': liquidation.after_travel_report_status if component_type == 'after_travel_report' else liquidation.certificate_of_travel_status
        }, status=200)


class UpdateLiquidationReviewerView(APIView):
    """View to update reviewer assignment for existing liquidations"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, liquidation_id):
        """Update reviewer assignment for a liquidation"""
        try:
            liquidation = Liquidation.objects.get(id=liquidation_id)
        except Liquidation.DoesNotExist:
            return Response({'error': 'Liquidation not found'}, status=404)
        
        # Only allow admin or the liquidation owner to update
        if request.user.user_level != 'admin' and liquidation.uploaded_by != request.user:
            return Response({'error': 'Unauthorized'}, status=403)
        
        after_travel_report_reviewer = request.data.get('after_travel_report_reviewer')
        certificate_of_travel_reviewer = request.data.get('certificate_of_travel_reviewer')
        
        if after_travel_report_reviewer:
            try:
                reviewer = CustomUser.objects.get(id=after_travel_report_reviewer)
                liquidation.after_travel_report_reviewer = reviewer
                print(f"DEBUG: Updated after_travel_report_reviewer to: {reviewer.email}")
            except CustomUser.DoesNotExist:
                return Response({'error': 'Invalid reviewer ID for after travel report'}, status=400)
        
        if certificate_of_travel_reviewer:
            try:
                reviewer = CustomUser.objects.get(id=certificate_of_travel_reviewer)
                liquidation.certificate_of_travel_reviewer = reviewer
                print(f"DEBUG: Updated certificate_of_travel_reviewer to: {reviewer.email}")
            except CustomUser.DoesNotExist:
                return Response({'error': 'Invalid reviewer ID for certificate of travel'}, status=400)
        
        liquidation.save()
        
        return Response({
            'message': 'Reviewer assignment updated successfully',
            'after_travel_report_reviewer': liquidation.after_travel_report_reviewer.email if liquidation.after_travel_report_reviewer else None,
            'certificate_of_travel_reviewer': liquidation.certificate_of_travel_reviewer.email if liquidation.certificate_of_travel_reviewer else None
        }, status=200)


class SubmitLiquidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Check if travel order has a travel order number
        if not travel_order.travel_order_number:
            return Response({'error': 'Travel order must be approved before liquidation can be submitted.'}, status=400)

        # Check if liquidation already exists
        if hasattr(travel_order, 'liquidation'):
            return Response({'error': 'Liquidation already exists for this travel order.'}, status=400)

        # Check if travel order is within 3 months of travel end date
        now = timezone.now().date()
        three_months_ago = now - timedelta(days=90)
        if travel_order.date_travel_to < three_months_ago:
            return Response({
                'error': f'Liquidation period has expired. Travel ended on {travel_order.date_travel_to}, but liquidation must be submitted within 3 months of travel completion.'
            }, status=400)

        # Handle after travel report creation
        after_travel_report_data = request.data.get('after_travel_report')
        after_travel_report = None
        
        print("=== AFTER TRAVEL REPORT DATA ===")
        print(f"Raw data: {after_travel_report_data}")
        print(f"Type: {type(after_travel_report_data)}")
        
        if after_travel_report_data:
            if isinstance(after_travel_report_data, str):
                try:
                    after_travel_report_data = json.loads(after_travel_report_data)
                except json.JSONDecodeError:
                    return Response({'after_travel_report': ['Invalid after_travel_report format.']}, status=400)
            
            # Get Regional Director
            regional_director = CustomUser.objects.filter(user_level='director').first()
            
            # Use office_head from frontend if provided, otherwise fallback to logic
            if not after_travel_report_data.get('office_head'):
                # Use the first selected head from prepared_by as office_head
                if after_travel_report_data.get('prepared_by') and len(after_travel_report_data['prepared_by']) > 0:
                    # Get the first head from the prepared_by list
                    first_head_id = after_travel_report_data['prepared_by'][0]
                    try:
                        first_head = CustomUser.objects.get(id=first_head_id, user_level='head')
                        after_travel_report_data['office_head'] = first_head.id
                    except CustomUser.DoesNotExist:
                        # Fallback to TMSD head if the selected head is not found or not a head
                        tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                        if tmsd_head:
                            after_travel_report_data['office_head'] = tmsd_head.id
                else:
                    # Fallback to TMSD head if no prepared_by is provided
                    tmsd_head = CustomUser.objects.filter(user_level='head', employee_type='tmsd').first()
                    if tmsd_head:
                        after_travel_report_data['office_head'] = tmsd_head.id
            
            if regional_director:
                after_travel_report_data['regional_director'] = regional_director.id
            
            # Handle file uploads for after travel report
            photo_files = request.FILES.getlist('photo_documentation')
            
            photo_paths = [photo.name for photo in photo_files]
            
            after_travel_report_data['photo_documentation'] = photo_paths
            
            after_travel_report_serializer = AfterTravelReportSerializer(data=after_travel_report_data)
            if after_travel_report_serializer.is_valid():
                after_travel_report = after_travel_report_serializer.save()
            else:
                return Response(after_travel_report_serializer.errors, status=400)

        # Create liquidation
        liquidation_data = {
            'travel_order_id': travel_order.id,  # Add the travel_order_id
            'certificate_of_travel': request.FILES.get('certificate_of_travel'),
            'certificate_of_appearance': request.FILES.get('certificate_of_appearance'),
        }
        
        if after_travel_report:
            liquidation_data['after_travel_report'] = after_travel_report.id

        print("=== LIQUIDATION DATA ===")
        print(f"Liquidation data: {liquidation_data}")
        print(f"Files: {list(request.FILES.keys())}")

        serializer = LiquidationSerializer(data=liquidation_data)
        if serializer.is_valid():
            liquidation = serializer.save(uploaded_by=request.user)
            liquidation.update_status()  # Set initial status
            
            # Notify bookkeepers about new liquidation
            try:
                bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
                for bookkeeper in bookkeepers:
                    create_notification(
                        user=bookkeeper,
                        travel_order=travel_order,
                        notification_type='liquidation_needs_review',
                        title=f'New Liquidation Submitted',
                        message=f'Liquidation for travel order {travel_order.travel_order_number} has been submitted and needs your review.'
                    )
                print("DEBUG: Bookkeepers notified about new liquidation")
            except Exception as e:
                print(f"DEBUG: Error notifying bookkeepers: {e}")
                # Don't fail the liquidation creation if notification fails
            
            return Response(serializer.data, status=201)
        print("=== LIQUIDATION ERRORS ===")
        print(f"Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=400)





class BookkeeperReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Get liquidation details for bookkeeper review"""
        # Verify user is a bookkeeper
        if request.user.user_level != 'bookkeeper':
            return Response({"error": "Only bookkeepers can view this liquidation"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation.objects.select_related('travel_order__purpose', 'travel_order__specific_role'), pk=pk)
        
        print(f"DEBUG: Bookkeeper review - Liquidation ID: {liquidation.id}, Status: {liquidation.status}")
        
        # Bookkeeper can review any liquidation status
        
        serializer = LiquidationSerializer(liquidation, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        # Verify user is a bookkeeper
        if request.user.user_level != 'bookkeeper':
            return Response({"error": "Only bookkeepers can review this liquidation"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation, pk=pk)
        
        # Bookkeeper can review any liquidation status

        approve = request.data.get('approve', False)
        comment = request.data.get('comment', '')

        liquidation.is_bookkeeper_approved = approve
        liquidation.bookkeeper_comment = comment
        liquidation.reviewed_by_bookkeeper = request.user
        liquidation.reviewed_at_bookkeeper = timezone.now()
        
        liquidation.update_status()  # Use the update_status method
        
        # Send notifications
        if approve:
            # Notify accountants
            accountants = CustomUser.objects.filter(user_level='accountant')
            for accountant in accountants:
                create_notification(
                    user=accountant,
                    travel_order=liquidation.travel_order,
                    notification_type='new_approval_needed',
                    title=f'New Liquidation for Review',
                    message=f'Liquidation for travel order {liquidation.travel_order.travel_order_number} needs your review.'
                )
        else:
            # Notify employee
            create_notification(
                user=liquidation.uploaded_by,
                travel_order=liquidation.travel_order,
                notification_type='liquidation_rejected',
                title=f'Liquidation Rejected',
                message=f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been rejected. Reason: {comment}'
            )
        
        return Response({
            'message': 'Returned to employee for revision.' if not approve else 'Forwarded to accountant.',
            'status': 'success'
        }, status=status.HTTP_200_OK)


class BookkeeperComponentReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk, component):
        """Review individual liquidation components"""
        print(f"DEBUG: BookkeeperComponentReviewView - Component: {component}, PK: {pk}")
        
        # Verify user is a bookkeeper
        if request.user.user_level != 'bookkeeper':
            return Response({"error": "Only bookkeepers can review liquidation components"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation, pk=pk)
        print(f"DEBUG: Liquidation found - ID: {liquidation.id}, Status: {liquidation.status}")
        print(f"DEBUG: Submitted components - ATR: {bool(liquidation.after_travel_report)}, COT: {bool(liquidation.certificate_of_travel)}, COA: {bool(liquidation.certificate_of_appearance)}")
        
        # Verify liquidation is in the correct state
        if liquidation.status not in ['Under Pre-Audit', 'Pending', 'Under Final Audit']:
            print(f"DEBUG: Status check failed - Status: {liquidation.status} not in allowed states")
            return Response({"error": f"Liquidation is not in a reviewable state. Current status: {liquidation.status}"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        else:
            print(f"DEBUG: Status check passed - Status: {liquidation.status} is reviewable")

        # Validate component type
        valid_components = ['after_travel_report', 'certificate_of_travel', 'certificate_of_appearance']
        if component not in valid_components:
            print(f"DEBUG: Invalid component type - {component}")
            return Response({"error": "Invalid component type"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        else:
            print(f"DEBUG: Component type validation passed - {component}")

        approve = request.data.get('approve', False)
        comment = request.data.get('comment', '')
        print(f"DEBUG: Approve: {approve}, Comment: {comment}")

        # Check if the component was actually submitted
        component_submitted = False
        if component == 'after_travel_report' and liquidation.after_travel_report:
            component_submitted = True
        elif component == 'certificate_of_travel' and liquidation.certificate_of_travel:
            component_submitted = True
        elif component == 'certificate_of_appearance' and liquidation.certificate_of_appearance:
            component_submitted = True
        
        print(f"DEBUG: Component {component} submitted: {component_submitted}")
        
        if not component_submitted:
            return Response({"error": f"Component {component} was not submitted"}, 
                          status=status.HTTP_400_BAD_REQUEST)

        # Bookkeeper can review any component status
        print(f"DEBUG: Bookkeeper can review any component status - {component}")

        # Update component status
        status_field = f"{component}_status"
        comment_field = f"{component}_bookkeeper_comment"
        print(f"DEBUG: Status field: {status_field}, Comment field: {comment_field}")
        
        try:
            if approve:
                setattr(liquidation, status_field, 'bookkeeper_approved')
                print(f"DEBUG: Set {status_field} to bookkeeper_approved")
            else:
                setattr(liquidation, status_field, 'bookkeeper_rejected')
                print(f"DEBUG: Set {status_field} to bookkeeper_rejected")
                if not comment:
                    return Response({"error": "Comment is required when rejecting a component"}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            setattr(liquidation, comment_field, comment)
            print(f"DEBUG: Set {comment_field} to: {comment}")
        except AttributeError as e:
            # Handle case where new fields don't exist yet (migration not run)
            print(f"DEBUG: Field {status_field} or {comment_field} doesn't exist yet. Error: {e}")
            # For now, just update the main status
            if approve:
                liquidation.status = 'Under Final Audit'
                print("DEBUG: Set main status to Under Final Audit")
            else:
                liquidation.status = 'Rejected'
                liquidation.bookkeeper_comment = comment
                print("DEBUG: Set main status to Rejected")
        except Exception as e:
            print(f"DEBUG: Unexpected error setting fields: {e}")
            return Response({"error": f"Failed to update component status: {str(e)}"}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        liquidation.reviewed_by_bookkeeper = request.user
        liquidation.reviewed_at_bookkeeper = timezone.now()
        print(f"DEBUG: Set reviewer to {request.user.email}")
        
        # Save the liquidation with updated fields
        liquidation.save()
        print(f"DEBUG: Saved liquidation with updated fields")
        
        try:
            liquidation.update_status()
            print(f"DEBUG: update_status completed successfully")
        except Exception as e:
            print(f"DEBUG: update_status failed: {e}")
            # Fallback: just save the liquidation
            liquidation.save()
            print(f"DEBUG: Liquidation saved as fallback")
        
        # Send notifications
        component_display_name = component.replace("_", " ").title()
        if approve:
            # Notify employee about individual component approval
            try:
                create_notification(
                    user=liquidation.uploaded_by,
                    travel_order=liquidation.travel_order,
                    notification_type='component_approved',
                    title=f'{component_display_name} Approved by Bookkeeper',
                    message=f'Your {component_display_name.lower()} for travel order {liquidation.travel_order.travel_order_number} has been approved by the bookkeeper.'
                )
                print(f"DEBUG: Employee notified of {component_display_name} approval successfully")
            except Exception as e:
                print(f"DEBUG: Error notifying employee of approval: {e}")
                # Don't fail the approval if notification fails
            
            # Check if all SUBMITTED components are now approved by bookkeeper
            try:
                # Only check components that were actually submitted
                submitted_components = []
                if liquidation.after_travel_report:
                    submitted_components.append(liquidation.after_travel_report_status == 'bookkeeper_approved')
                if liquidation.certificate_of_travel:
                    submitted_components.append(liquidation.certificate_of_travel_status == 'bookkeeper_approved')
                if liquidation.certificate_of_appearance:
                    submitted_components.append(liquidation.certificate_of_appearance_status == 'bookkeeper_approved')
                
                # All submitted components must be approved
                all_approved = all(submitted_components) if submitted_components else False
                print(f"DEBUG: Submitted components check - {submitted_components}, all_approved: {all_approved}")
            except AttributeError as e:
                print(f"DEBUG: AttributeError checking component status: {e}")
                # If new fields don't exist, assume approved if status is Under Final Audit
                all_approved = liquidation.status == 'Under Final Audit'
            
            if all_approved:
                print("DEBUG: All submitted components approved, notifying accountants")
                # Notify accountants
                try:
                    accountants = CustomUser.objects.filter(user_level='accountant')
                    print(f"DEBUG: Found {accountants.count()} accountants to notify")
                    for accountant in accountants:
                        create_notification(
                            user=accountant,
                            travel_order=liquidation.travel_order,
                            notification_type='new_approval_needed',
                            title=f'Liquidation Ready for Review',
                            message=f'Liquidation for travel order {liquidation.travel_order.travel_order_number} is ready for final review.'
                        )
                    print("DEBUG: Accountants notified successfully")
                except Exception as e:
                    print(f"DEBUG: Error notifying accountants: {e}")
                    # Don't fail the approval if notification fails
        else:
            # Notify employee about rejection
            try:
                create_notification(
                    user=liquidation.uploaded_by,
                    travel_order=liquidation.travel_order,
                    notification_type='component_rejected',
                    title=f'Component Rejected',
                    message=f'Your {component.replace("_", " ")} for travel order {liquidation.travel_order.travel_order_number} has been rejected. Reason: {comment}'
                )
                print("DEBUG: Employee notified of rejection successfully")
            except Exception as e:
                print(f"DEBUG: Error notifying employee of rejection: {e}")
                # Don't fail the rejection if notification fails
        
        # Get component status safely
        try:
            component_status = getattr(liquidation, status_field)
            print(f"DEBUG: Retrieved component status: {component_status}")
        except AttributeError:
            component_status = 'bookkeeper_approved' if approve else 'bookkeeper_rejected'
            print(f"DEBUG: Using fallback component status: {component_status}")
        
        print(f"DEBUG: Returning success response for component {component}")
        return Response({
            'message': f'Component {component} {"approved" if approve else "rejected"} successfully.',
            'status': 'success',
            'component_status': component_status
        }, status=status.HTTP_200_OK)


class AccountantReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Get liquidation details for accountant review"""
        # Verify user is an accountant
        if request.user.user_level != 'accountant':
            return Response({"error": "Only accountants can view this liquidation"}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        liquidation = get_object_or_404(Liquidation.objects.select_related('travel_order__purpose', 'travel_order__specific_role'), pk=pk)
        
        # Accountant can review any liquidation status
        
        serializer = LiquidationSerializer(liquidation, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        # Verify user is an accountant
        if request.user.user_level != 'accountant':
            return Response({"error": "Only accountants can review this liquidation"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation, pk=pk)
        
        # Accountant can review any liquidation status

        approve = request.data.get('approve', False)
        comment = request.data.get('comment', '')

        liquidation.is_accountant_approved = approve
        liquidation.accountant_comment = comment
        liquidation.reviewed_by_accountant = request.user
        liquidation.reviewed_at_accountant = timezone.now()
        
        liquidation.update_status()  # Use the update_status method
        
        # Send notifications
        if approve:
            # Calculate original grand total from itinerary
            original_total = 0
            try:
                from .models import Itinerary
                itineraries = Itinerary.objects.filter(travel_order=liquidation.travel_order)
                for itinerary in itineraries:
                    if itinerary.total_amount:
                        original_total += float(itinerary.total_amount)
                original_total = round(original_total, 2)
            except Exception as e:
                print(f"DEBUG: Error calculating original total: {e}")
            
            # Get final amount (if modified by accountant)
            final_amount = liquidation.final_amount
            
            # Create message with amount information
            if final_amount and float(final_amount) != original_total:
                message = f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been approved and is ready for claim.\n\nFinal Amount: ₱{final_amount:,.2f} (changed from ₱{original_total:,.2f})'
            else:
                message = f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been approved and is ready for claim.\n\nFinal Amount: ₱{original_total:,.2f}'
            
            # Notify employee
            create_notification(
                user=liquidation.uploaded_by,
                travel_order=liquidation.travel_order,
                notification_type='liquidation_approved',
                title=f'Liquidation Approved',
                message=message,
                liquidation=liquidation  # Pass liquidation for email template
            )
        else:
            # Notify employee
            create_notification(
                user=liquidation.uploaded_by,
                travel_order=liquidation.travel_order,
                notification_type='liquidation_rejected',
                title=f'Liquidation Rejected',
                message=f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been rejected. Reason: {comment}'
            )
        
        return Response({
            'message': 'Liquidation approved and ready for claim.' if approve else 'Rejected by accountant.',
            'status': 'success'
        }, status=status.HTTP_200_OK)


class AccountantComponentReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk, component):
        """Review individual liquidation components as accountant"""
        # Verify user is an accountant
        if request.user.user_level != 'accountant':
            return Response({"error": "Only accountants can review liquidation components"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation, pk=pk)
        
        # Verify liquidation is in the correct state
        if liquidation.status != 'Under Final Audit':
            return Response({"error": "Liquidation is not ready for final audit"}, 
                          status=status.HTTP_400_BAD_REQUEST)

        # Validate component type
        valid_components = ['after_travel_report', 'certificate_of_travel', 'certificate_of_appearance']
        if component not in valid_components:
            return Response({"error": "Invalid component type"}, 
                          status=status.HTTP_400_BAD_REQUEST)

        # Check if component was approved by bookkeeper
        status_field = f"{component}_status"
        try:
            current_status = getattr(liquidation, status_field)
            print(f"DEBUG: Current status for {component}: {current_status}")
        except AttributeError as e:
            print(f"DEBUG: AttributeError getting {status_field}: {e}")
            return Response({"error": f"Component status field {status_field} does not exist. Please run migrations."}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Accountant can review any component status
        print(f"DEBUG: Accountant can review any component status - {component}, current status: {current_status}")

        approve = request.data.get('approve', False)
        comment = request.data.get('comment', '')
        
        try:
            if approve:
                setattr(liquidation, status_field, 'accountant_approved')
                print(f"DEBUG: Set {status_field} to accountant_approved")
                print(f"DEBUG: Before save - {status_field}: {getattr(liquidation, status_field)}")
            else:
                setattr(liquidation, status_field, 'accountant_rejected')
                print(f"DEBUG: Set {status_field} to accountant_rejected")
                if not comment:
                    return Response({"error": "Comment is required when rejecting a component"}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            # Update accountant comment
            comment_field = f"{component}_accountant_comment"
            setattr(liquidation, comment_field, comment)
            print(f"DEBUG: Set {comment_field} to: {comment}")
            
            liquidation.reviewed_by_accountant = request.user
            liquidation.reviewed_at_accountant = timezone.now()
            
            # Save the liquidation with updated fields
            liquidation.save()
            print(f"DEBUG: Saved liquidation with updated fields")
            print(f"DEBUG: After save - {status_field}: {getattr(liquidation, status_field)}")
            
            liquidation.update_status()
            print(f"DEBUG: Updated liquidation status to: {liquidation.status}")
            print(f"DEBUG: After update - ATR: {liquidation.after_travel_report_status}, COT: {liquidation.certificate_of_travel_status}, COA: {liquidation.certificate_of_appearance_status}")
            
            # Final verification - reload from database
            liquidation.refresh_from_db()
            print(f"DEBUG: After refresh from DB - {status_field}: {getattr(liquidation, status_field)}")
            
            # Send notifications BEFORE returning
            if approve:
                # Check if all SUBMITTED components are now approved by accountant
                try:
                    submitted_components_status_checks = []
                    if liquidation.after_travel_report:
                        submitted_components_status_checks.append(liquidation.after_travel_report_status == 'accountant_approved')
                    if liquidation.certificate_of_travel:
                        submitted_components_status_checks.append(liquidation.certificate_of_travel_status == 'accountant_approved')
                    if liquidation.certificate_of_appearance:
                        submitted_components_status_checks.append(liquidation.certificate_of_appearance_status == 'accountant_approved')
                    
                    # All submitted components must be approved
                    all_approved = all(submitted_components_status_checks) if submitted_components_status_checks else False
                    print(f"DEBUG: Checking if all approved - submitted_components_status_checks: {submitted_components_status_checks}, all_approved: {all_approved}")
                except AttributeError as e:
                    print(f"DEBUG: AttributeError checking component status: {e}")
                    # If new fields don't exist, assume approved if status is Ready for Claim
                    all_approved = liquidation.status == 'Ready for Claim'
                    print(f"DEBUG: Fallback check - status: {liquidation.status}, all_approved: {all_approved}")
                
                if all_approved:
                    print(f"DEBUG: All components approved! Sending notification email...")
                    # Calculate original grand total from itinerary
                    original_total = 0
                    try:
                        from .models import Itinerary
                        itineraries = Itinerary.objects.filter(travel_order=liquidation.travel_order)
                        for itinerary in itineraries:
                            if itinerary.total_amount:
                                original_total += float(itinerary.total_amount)
                        original_total = round(original_total, 2)
                        print(f"DEBUG: Calculated original_total: {original_total}")
                    except Exception as e:
                        print(f"DEBUG: Error calculating original total: {e}")
                    
                    # Get final amount (if modified by accountant)
                    final_amount = liquidation.final_amount
                    print(f"DEBUG: Final amount from liquidation: {final_amount}")
                    
                    # Create message with amount information
                    if final_amount and float(final_amount) != original_total:
                        message = f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been approved and is ready for claim.\n\nFinal Amount: ₱{final_amount:,.2f} (changed from ₱{original_total:,.2f})'
                    else:
                        message = f'Your liquidation for travel order {liquidation.travel_order.travel_order_number} has been approved and is ready for claim.\n\nFinal Amount: ₱{original_total:,.2f}'
                    
                    # Notify employee that liquidation is ready for claim
                    print(f"DEBUG: Calling create_notification for user: {liquidation.uploaded_by.email}")
                    create_notification(
                        user=liquidation.uploaded_by,
                        travel_order=liquidation.travel_order,
                        notification_type='liquidation_approved',
                        title=f'Liquidation Approved',
                        message=message,
                        liquidation=liquidation  # Pass liquidation for email template
                    )
                    print(f"DEBUG: Notification created and email sent (if successful)")
                else:
                    print(f"DEBUG: Not all components approved yet. Status checks: {submitted_components_status_checks if 'submitted_components_status_checks' in locals() else 'N/A'}")
            
            # Handle rejection notification
            if not approve:
                # Notify employee about rejection
                create_notification(
                    user=liquidation.uploaded_by,
                    travel_order=liquidation.travel_order,
                    notification_type='component_rejected',
                    title=f'Component Rejected',
                    message=f'Your {component.replace("_", " ")} for travel order {liquidation.travel_order.travel_order_number} has been rejected. Reason: {comment}'
                )
            
            return Response({
                'message': f'Component {component} approved successfully' if approve else f'Component {component} rejected',
                'status': 'success'
            }, status=status.HTTP_200_OK)
        except AttributeError as e:
            print(f"DEBUG: AttributeError setting fields: {e}")
            return Response({"error": f"Component status fields do not exist. Please run migrations. Error: {str(e)}"}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            print(f"DEBUG: Unexpected error: {e}")
            return Response({"error": f"Unexpected error: {str(e)}"}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateFinalAmountView(APIView):
    """Allow accountant to update the final amount during final audit"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        # Verify user is an accountant
        if request.user.user_level != 'accountant':
            return Response({"error": "Only accountants can update final amount"}, 
                          status=status.HTTP_403_FORBIDDEN)
            
        liquidation = get_object_or_404(Liquidation, pk=pk)
        
        # Verify liquidation is in the correct state
        if liquidation.status != 'Under Final Audit':
            return Response({"error": "Liquidation is not ready for final audit"}, 
                          status=status.HTTP_400_BAD_REQUEST)

        final_amount = request.data.get('final_amount')
        
        if final_amount is None:
            return Response({"error": "final_amount is required"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Convert to decimal if it's a string
            if isinstance(final_amount, str):
                final_amount = float(final_amount)
            
            if final_amount < 0:
                return Response({"error": "Final amount cannot be negative"}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Store old final amount for audit log
            old_final_amount = liquidation.final_amount
            
            # Calculate original amount from itinerary totals
            original_amount = 0
            try:
                from .models import Itinerary
                itineraries = Itinerary.objects.filter(travel_order=liquidation.travel_order)
                for itinerary in itineraries:
                    if itinerary.total_amount:
                        original_amount += float(itinerary.total_amount)
                original_amount = round(original_amount, 2)
            except Exception as e:
                print(f"DEBUG: Error calculating original amount for audit log: {e}")
            
            # Update final amount
            liquidation.final_amount = final_amount
            liquidation.reviewed_by_accountant = request.user
            liquidation.reviewed_at_accountant = timezone.now()
            liquidation.save()
            
            # Create audit log entry for amount change
            log_audit_event(
                user=request.user,
                action='update',
                resource_type='liquidation',
                resource_id=str(liquidation.id),
                resource_name=f"Liquidation for Travel Order {liquidation.travel_order.travel_order_number}",
                description=f"Accountant changed final amount from ₱{old_final_amount or original_amount:,.2f} to ₱{final_amount:,.2f} (Original amount: ₱{original_amount:,.2f})",
                request=request,
                metadata={
                    'original_amount': float(original_amount),
                    'previous_final_amount': float(old_final_amount) if old_final_amount else None,
                    'new_final_amount': float(final_amount),
                    'travel_order_number': liquidation.travel_order.travel_order_number,
                    'liquidation_id': liquidation.id
                }
            )
            
            return Response({
                'message': 'Final amount updated successfully',
                'final_amount': str(liquidation.final_amount),
                'status': 'success'
            }, status=status.HTTP_200_OK)
        except (ValueError, TypeError) as e:
            return Response({"error": f"Invalid final_amount value: {str(e)}"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Unexpected error: {str(e)}"}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
class UpdateAfterTravelReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        """Update an existing after travel report"""
        try:
            liquidation = Liquidation.objects.get(travel_order_id=pk)
        except Liquidation.DoesNotExist:
            return Response({'error': 'Liquidation not found'}, status=404)
        
        # Check if user is authorized to update (must be the uploader)
        if liquidation.uploaded_by != request.user:
            return Response({'error': 'Unauthorized to update this liquidation'}, status=403)
        
        # Check if after travel report exists and is rejected
        if not liquidation.after_travel_report:
            return Response({'error': 'No after travel report to update'}, status=400)
        
        if liquidation.after_travel_report_status not in ['reviewer_rejected', 'bookkeeper_rejected', 'accountant_rejected']:
            return Response({'error': 'After travel report is not in a rejected state'}, status=400)
        
        # Parse the after travel report data
        after_travel_report_data = json.loads(request.data.get('after_travel_report', '{}'))
        
        # Update the after travel report
        after_travel_report = liquidation.after_travel_report
        for field, value in after_travel_report_data.items():
            if hasattr(after_travel_report, field):
                if field == 'prepared_by':
                    after_travel_report.prepared_by.set(value)
                elif field == 'office_head':
                    # Handle foreign key relationship
                    if value:
                        try:
                            office_head = CustomUser.objects.get(id=value)
                            after_travel_report.office_head = office_head
                        except CustomUser.DoesNotExist:
                            return Response({'error': f'Office head with ID {value} not found'}, status=400)
                elif field == 'regional_director':
                    # Handle foreign key relationship
                    if value:
                        try:
                            regional_director = CustomUser.objects.get(id=value)
                            after_travel_report.regional_director = regional_director
                        except CustomUser.DoesNotExist:
                            return Response({'error': f'Regional director with ID {value} not found'}, status=400)
                elif field == 'photo_documentation':
                    # Handle photo documentation separately
                    continue
                else:
                    setattr(after_travel_report, field, value)
        
        # Handle photo documentation
        if 'photo_documentation' in request.FILES:
            # Clear existing photos and add new ones
            after_travel_report.photo_documentation = []
            for file in request.FILES.getlist('photo_documentation'):
                # Save file and add to photo_documentation
                file_path = f"evidence/after_travel_photos/{file.name}"
                with default_storage.open(file_path, 'wb+') as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                after_travel_report.photo_documentation.append(file_path)
        
        after_travel_report.save()
        
        # Reset the status to pending_review for re-review and reassign reviewer
        liquidation.after_travel_report_status = 'pending_review'
        liquidation.resubmitted_at = timezone.now()
        
        # Reassign the reviewer based on the office_head
        if after_travel_report.office_head:
            liquidation.after_travel_report_reviewer = after_travel_report.office_head
        
        liquidation.save()
        liquidation.update_status()
        
        # Notify the assigned reviewer about the resubmission
        if liquidation.after_travel_report_reviewer:
            create_notification(
                user=liquidation.after_travel_report_reviewer,
                travel_order=liquidation.travel_order,
                notification_type='travel_approved',  # Using existing type for reviewer notification
                title=f'After Travel Report Resubmitted for Review',
                message=f'After travel report for travel order {liquidation.travel_order.travel_order_number} has been resubmitted and is ready for your review.'
            )
        
        return Response({
            'message': 'After travel report updated successfully',
            'after_travel_report': AfterTravelReportSerializer(after_travel_report).data
        }, status=200)


class UpdateCertificateOfTravelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        """Update an existing certificate of travel"""
        try:
            liquidation = Liquidation.objects.get(travel_order_id=pk)
        except Liquidation.DoesNotExist:
            return Response({'error': 'Liquidation not found'}, status=404)
        
        # Check if user is authorized to update (must be the uploader)
        if liquidation.uploaded_by != request.user:
            return Response({'error': 'Unauthorized to update this liquidation'}, status=403)
        
        # Check if certificate of travel exists and is rejected
        if not liquidation.certificate_of_travel:
            return Response({'error': 'No certificate of travel to update'}, status=400)
        
        if liquidation.certificate_of_travel_status not in ['reviewer_rejected', 'bookkeeper_rejected', 'accountant_rejected']:
            return Response({'error': 'Certificate of travel is not in a rejected state'}, status=400)
        
        # Update the certificate of travel
        cert = liquidation.certificate_of_travel
        
        # Update basic fields
        for field in ['agency_head', 'fund_cluster', 'station', 'travel_order_number', 
                     'date_travel_from', 'date_travel_to', 'approved', 'deviation_types',
                     'explanations_justifications', 'evidence_type', 'refund_amount',
                     'or_number', 'or_date']:
            if field in request.data:
                if field == 'respectfully_submitted':
                    # Handle many-to-many field
                    user_ids = json.loads(request.data[field])
                    cert.respectfully_submitted.set(user_ids)
                elif field == 'agency_head':
                    # Handle foreign key relationship
                    if request.data[field]:
                        try:
                            agency_head = CustomUser.objects.get(id=request.data[field])
                            cert.agency_head = agency_head
                        except CustomUser.DoesNotExist:
                            return Response({'error': f'Agency head with ID {request.data[field]} not found'}, status=400)
                elif field == 'approved':
                    # Handle foreign key relationship
                    if request.data[field]:
                        try:
                            approved = CustomUser.objects.get(id=request.data[field])
                            cert.approved = approved
                        except CustomUser.DoesNotExist:
                            return Response({'error': f'Approved user with ID {request.data[field]} not found'}, status=400)
                elif field == 'deviation_types':
                    # Handle JSON field
                    cert.deviation_types = json.loads(request.data[field])
                elif field in ['date_travel_from', 'date_travel_to', 'or_date']:
                    # Handle date fields
                    if request.data[field]:
                        setattr(cert, field, request.data[field])
                elif field in ['refund_amount']:
                    # Handle decimal fields
                    if request.data[field]:
                        setattr(cert, field, request.data[field])
                else:
                    setattr(cert, field, request.data[field])
        
        cert.save()
        
        # Reset the status to pending_review for re-review and reassign reviewer
        liquidation.certificate_of_travel_status = 'pending_review'
        liquidation.resubmitted_at = timezone.now()
        
        # Reassign the reviewer based on the approved user
        if cert.approved:
            liquidation.certificate_of_travel_reviewer = cert.approved
        
        liquidation.save()
        liquidation.update_status()
        
        # Notify the assigned reviewer about the resubmission
        if liquidation.certificate_of_travel_reviewer:
            create_notification(
                user=liquidation.certificate_of_travel_reviewer,
                travel_order=liquidation.travel_order,
                notification_type='travel_approved',  # Using existing type for reviewer notification
                title=f'Certificate of Travel Resubmitted for Review',
                message=f'Certificate of travel for travel order {liquidation.travel_order.travel_order_number} has been resubmitted and is ready for your review.'
            )
        
        return Response({
            'message': 'Certificate of travel updated successfully',
            'certificate_of_travel': CertificateOfTravelSerializer(cert).data
        }, status=200)


class UpdateCertificateOfAppearanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        """Update an existing certificate of appearance"""
        try:
            liquidation = Liquidation.objects.get(travel_order_id=pk)
        except Liquidation.DoesNotExist:
            return Response({'error': 'Liquidation not found'}, status=404)
        
        # Check if user is authorized to update (must be the uploader)
        if liquidation.uploaded_by != request.user:
            return Response({'error': 'Unauthorized to update this liquidation'}, status=403)
        
        # Check if certificate of appearance exists and is rejected
        if not liquidation.certificate_of_appearance:
            return Response({'error': 'No certificate of appearance to update'}, status=400)
        
        if liquidation.certificate_of_appearance_status not in ['bookkeeper_rejected', 'accountant_rejected']:
            return Response({'error': 'Certificate of appearance is not in a rejected state'}, status=400)
        
        # Update the certificate of appearance file
        if 'certificate_of_appearance' in request.FILES:
            liquidation.certificate_of_appearance = request.FILES['certificate_of_appearance']
            liquidation.save()
        
        # Reset the status to submitted for re-review (certificate of appearance goes directly to bookkeeper)
        liquidation.certificate_of_appearance_status = 'submitted'
        liquidation.resubmitted_at = timezone.now()
        liquidation.save()
        liquidation.update_status()
        
        # Notify bookkeepers about the resubmission (certificate of appearance goes directly to bookkeeper)
        try:
            bookkeepers = CustomUser.objects.filter(user_level='bookkeeper')
            for bookkeeper in bookkeepers:
                create_notification(
                    user=bookkeeper,
                    travel_order=liquidation.travel_order,
                    notification_type='travel_approved',  # Using existing type for bookkeeper notification
                    title=f'Certificate of Appearance Resubmitted for Review',
                    message=f'Certificate of appearance for travel order {liquidation.travel_order.travel_order_number} has been resubmitted and is ready for your review.'
                )
        except Exception as e:
            print(f"DEBUG: Error notifying bookkeepers: {e}")
            # Don't fail the update if notification fails
        
        return Response({
            'message': 'Certificate of appearance updated successfully',
            'certificate_of_appearance': liquidation.certificate_of_appearance.url if liquidation.certificate_of_appearance else None
        }, status=200)


# Draft save/update endpoints for liquidation forms
class SaveDraftAfterTravelReportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """Create or update a draft after travel report - saves directly on Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Get or create Liquidation for this travel order
        liquidation, created = Liquidation.objects.get_or_create(
            travel_order=travel_order,
            defaults={'uploaded_by': request.user}
        )
        if not created:
            # Update uploaded_by if not set
            if not liquidation.uploaded_by:
                liquidation.uploaded_by = request.user
                liquidation.save()
        
        # Parse after travel report data
        after_travel_report_data = request.data.get('after_travel_report')
        if isinstance(after_travel_report_data, str):
            try:
                after_travel_report_data = json.loads(after_travel_report_data)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid after_travel_report format.'}, status=400)

        # Handle photo files (optional for drafts)
        photo_files = request.FILES.getlist('photo_documentation')
        photo_paths = []
        
        if photo_files:
            for photo in photo_files:
                allowed_photo_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff', 'image/webp']
                if photo.content_type not in allowed_photo_types:
                    continue  # Skip invalid files for drafts
                
                max_photo_size = 5 * 1024 * 1024  # 5MB
                if photo.size > max_photo_size:
                    continue  # Skip oversized files for drafts
                
                file_extension = os.path.splitext(photo.name)[1]
                unique_filename = f"evidence/after_travel_photos/{uuid.uuid4()}{file_extension}"
                photo_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
                
                os.makedirs(os.path.dirname(photo_path), exist_ok=True)
                
                with open(photo_path, 'wb+') as destination:
                    for chunk in photo.chunks():
                        destination.write(chunk)
                
                photo_paths.append(unique_filename)

        # Merge photo paths with existing ones if updating
        existing_draft_data = liquidation.after_travel_report_draft or {}
        if existing_draft_data.get('photo_documentation'):
            photo_paths = existing_draft_data['photo_documentation'] + photo_paths

        # Prepare draft data to save
        draft_data = {
            **after_travel_report_data,
            'photo_documentation': photo_paths
        }
        
        # Save draft data directly on Liquidation
        liquidation.after_travel_report_draft = draft_data
        liquidation.save()

        # Return response with draft data
        return Response({
            'message': 'Draft saved successfully',
            'after_travel_report': draft_data
        }, status=200)

    def get(self, request, pk):
        """Get draft after travel report for a travel order - from Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        try:
            liquidation = Liquidation.objects.get(travel_order=travel_order)
            draft_data = liquidation.after_travel_report_draft
            if draft_data:
                return Response({
                    'after_travel_report': draft_data
                }, status=200)
        except Liquidation.DoesNotExist:
            pass
        
        return Response({'message': 'No draft found'}, status=404)


class SaveDraftCertificateOfTravelView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """Create or update a draft certificate of travel - saves directly on Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Get or create Liquidation for this travel order
        liquidation, created = Liquidation.objects.get_or_create(
            travel_order=travel_order,
            defaults={'uploaded_by': request.user}
        )
        if not created:
            # Update uploaded_by if not set
            if not liquidation.uploaded_by:
                liquidation.uploaded_by = request.user
                liquidation.save()
        
        # Prepare data
        data = {}
        for key, value in request.data.items():
            if key not in ['respectfully_submitted', 'deviation_types']:
                data[key] = value
        
        # Handle JSON fields
        if 'respectfully_submitted' in request.data:
            try:
                if isinstance(request.data['respectfully_submitted'], str):
                    data['respectfully_submitted'] = json.loads(request.data['respectfully_submitted'])
                else:
                    data['respectfully_submitted'] = request.data['respectfully_submitted']
            except json.JSONDecodeError:
                return Response({'error': 'Invalid respectfully_submitted format.'}, status=400)

        if 'deviation_types' in request.data:
            try:
                if isinstance(request.data['deviation_types'], str):
                    data['deviation_types'] = json.loads(request.data['deviation_types'])
                else:
                    data['deviation_types'] = request.data['deviation_types']
            except json.JSONDecodeError:
                return Response({'error': 'Invalid deviation_types format.'}, status=400)

        # Save draft data directly on Liquidation
        liquidation.certificate_of_travel_draft = data
        liquidation.save()

        return Response({
            'message': 'Draft saved successfully',
            'certificate_of_travel': data
        }, status=200)

    def get(self, request, pk):
        """Get draft certificate of travel for a travel order - from Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        try:
            liquidation = Liquidation.objects.get(travel_order=travel_order)
            draft_data = liquidation.certificate_of_travel_draft
            if draft_data:
                return Response({
                    'certificate_of_travel': draft_data
                }, status=200)
        except Liquidation.DoesNotExist:
            pass
        
        return Response({'message': 'No draft found'}, status=404)


class SaveDraftCertificateOfAppearanceView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """Create or update a draft certificate of appearance - saves directly on Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        # Get or create Liquidation for this travel order
        liquidation, created = Liquidation.objects.get_or_create(
            travel_order=travel_order,
            defaults={'uploaded_by': request.user}
        )
        if not created:
            # Update uploaded_by if not set
            if not liquidation.uploaded_by:
                liquidation.uploaded_by = request.user
                liquidation.save()
        
        # Prepare draft data
        draft_data = {}
        certificate_file_path = None
        
        # Handle file upload
        if 'certificate_of_appearance' in request.FILES:
            certificate_file = request.FILES['certificate_of_appearance']
            
            # Validate file type
            allowed_types = [
                'application/pdf',
                'image/jpeg',
                'image/jpg',
                'image/png',
                'image/gif',
                'image/bmp',
                'image/tiff',
                'image/webp'
            ]
            
            if certificate_file.content_type not in allowed_types:
                return Response({
                    'error': 'Invalid file type. Allowed types: PDF, JPG, PNG, GIF, BMP, TIFF, WEBP'
                }, status=400)
            
            # Validate file size (10MB limit)
            max_size = 10 * 1024 * 1024  # 10MB
            if certificate_file.size > max_size:
                return Response({
                    'error': 'File size too large. Maximum size is 10MB.'
                }, status=400)
            
            # Save file
            file_extension = os.path.splitext(certificate_file.name)[1]
            unique_filename = f"liquidations/certificate_of_appearance/draft_{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'wb+') as destination:
                for chunk in certificate_file.chunks():
                    destination.write(chunk)
            
            certificate_file_path = unique_filename
        else:
            # Check if there's an existing draft file path
            existing_draft = liquidation.certificate_of_appearance_draft or {}
            certificate_file_path = existing_draft.get('certificate_of_appearance_url')
            
            if not certificate_file_path:
                # No file provided and no existing draft - require a file
                return Response({
                    'error': 'Certificate of appearance file is required.'
                }, status=400)
        
        # Store file path in draft data
        draft_data['certificate_of_appearance_url'] = certificate_file_path
        
        # Save draft data directly on Liquidation
        liquidation.certificate_of_appearance_draft = draft_data
        liquidation.save()

        return Response({
            'message': 'Draft saved successfully',
            'certificate_of_appearance': {
                'certificate_of_appearance_url': certificate_file_path
            }
        }, status=200)

    def get(self, request, pk):
        """Get draft certificate of appearance for a travel order - from Liquidation model"""
        try:
            travel_order = TravelOrder.objects.get(pk=pk)
        except TravelOrder.DoesNotExist:
            return Response({'error': 'Travel order not found.'}, status=404)

        try:
            liquidation = Liquidation.objects.get(travel_order=travel_order)
            draft_data = liquidation.certificate_of_appearance_draft
            if draft_data:
                return Response({
                    'certificate_of_appearance': {
                        'certificate_of_appearance_url': draft_data.get('certificate_of_appearance_url')
                    }
                }, status=200)
        except Liquidation.DoesNotExist:
            pass
        
        return Response({'message': 'No draft found'}, status=404)

    
class LiquidationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        show_completed = request.query_params.get('completed', 'false').lower() == 'true'
        
        # Filter liquidations based on user role and status
        if user.user_level == 'bookkeeper':
            # Bookkeepers can see liquidations that are under pre-audit or pending (need their review)
            liquidations = Liquidation.objects.filter(
                status__in=['Under Pre-Audit', 'Pending']
            ).select_related('travel_order').order_by('-submitted_at')
        elif user.user_level == 'accountant':
            # Accountants can see liquidations that are under final audit (bookkeeper approved)
            # or ready for claim (all components approved by accountant)
            # Also include liquidations where components are reviewer_approved (ready for accountant)
            liquidations = Liquidation.objects.filter(
                models.Q(status__in=['Under Final Audit', 'Ready for Claim']) |
                models.Q(after_travel_report_status='reviewer_approved') |
                models.Q(certificate_of_travel_status='reviewer_approved') |
                models.Q(certificate_of_appearance_status='bookkeeper_approved')
            ).select_related('travel_order').order_by('-submitted_at')
        elif user.user_level in ['admin', 'director']:
            # Admins and directors can see all liquidations
            liquidations = Liquidation.objects.select_related('travel_order').all().order_by('-submitted_at')
        else:
            # Other users see their own liquidations (including pending ones)
            # Use prefetch_related to handle broken relationships gracefully
            liquidations = Liquidation.objects.filter(
                uploaded_by=user
            ).prefetch_related('travel_order').order_by('-submitted_at')
            
            # Filter by completed status if requested
            if show_completed:
                # Return only completed liquidations (all three components accountant_approved)
                liquidations = liquidations.filter(
                    after_travel_report_status='accountant_approved',
                    certificate_of_travel_status='accountant_approved',
                    certificate_of_appearance_status='accountant_approved'
                )
            else:
                # Return only non-completed liquidations
                liquidations = liquidations.exclude(
                    after_travel_report_status='accountant_approved',
                    certificate_of_travel_status='accountant_approved',
                    certificate_of_appearance_status='accountant_approved'
                )
        
        serializer = LiquidationSerializer(liquidations, many=True, context={'request': request})
        return Response(serializer.data)


class AdminLiquidationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Only admins can access this endpoint
        if request.user.user_level != 'admin':
            return Response(
                {"error": "You do not have permission to access this resource"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get all liquidations for admin view
        liquidations = Liquidation.objects.select_related('travel_order').all().order_by('-submitted_at')
        
        serializer = LiquidationSerializer(liquidations, many=True, context={'request': request})
        return Response(serializer.data)
    

class TravelOrdersNeedingLiquidationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now().date()

        # Include ALL travel orders that need liquidation (including expired ones)
        # The frontend will handle disabling buttons for expired ones
        travel_orders = TravelOrder.objects.filter(
            prepared_by=user,
            travel_order_number__isnull=False,
            liquidation__isnull=True
        ).order_by("-date_travel_to")

        serializer = TravelOrderSimpleSerializer(travel_orders, many=True)
        return Response(serializer.data)
    
class LiquidationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        liquidation = get_object_or_404(Liquidation, pk=pk)
        
        # Check if user has permission to view this liquidation
        user = request.user
        can_view = False
        
        # Users can view their own liquidations
        if liquidation.uploaded_by == user:
            can_view = True
        # Reviewers can view liquidations they're assigned to review
        elif (hasattr(liquidation, 'after_travel_report_reviewer') and liquidation.after_travel_report_reviewer == user) or \
             (hasattr(liquidation, 'certificate_of_travel_reviewer') and liquidation.certificate_of_travel_reviewer == user):
            can_view = True
        # Bookkeepers can view liquidations they need to review
        elif user.user_level == 'bookkeeper' and liquidation.status == 'Under Pre-Audit':
            can_view = True
        # Accountants can view liquidations they need to review
        elif user.user_level == 'accountant' and liquidation.status == 'Under Final Audit':
            can_view = True
        # Admins and directors can view all liquidations
        elif user.user_level in ['admin', 'director']:
            can_view = True
        
        if not can_view:
            return Response(
                {"error": "You do not have permission to view this liquidation"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = LiquidationSerializer(liquidation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class EmployeeDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = now().date()
        start_of_month = today.replace(day=1)

        # Travel requests filed by this employee
        own_orders = TravelOrder.objects.filter(prepared_by=user)
        
        # Travel requests that have been approved (using approval snapshots)
        approved_travel_orders = TravelOrderApprovalSnapshot.objects.filter(
            travel_order__prepared_by=user
        ).values_list('travel_order', flat=True).distinct()
        
        # Travel requests that have been rejected
        rejected_travel_orders = own_orders.filter(
            status__icontains='rejected'
        )

        # Current month travel orders for calendar - use serializer to get all fields
        current_month_orders = own_orders.filter(
            submitted_at__date__gte=start_of_month
        )
        serializer = TravelOrderSerializer(current_month_orders, many=True, context={'request': request})

        # Total claims (liquidations) filed by this employee
        total_claims = Liquidation.objects.filter(
            travel_order__prepared_by=user
        ).count()

        data = {
            'counts': {
                'total_travel_request': own_orders.count(),
                'total_claims': total_claims,
                'approve_travel_request': len(approved_travel_orders),
                'disapprove_travel_request': rejected_travel_orders.count(),
            },
            'travel_orders': serializer.data
        }

        return Response(data)
    



class AdminDashboard(APIView):
    def get(self, request):
        groups = {
            "Pangasinan PO + CSCs": ['pangasinan_po', 'urdaneta_csc', 'sison_csc'],
            "La Union PO + CSCs": ['launion_po', 'sudipen_csc', 'pugo_csc'],
            "Ilocos Sur PO + CSCs": ['ilocossur_po', 'tagudin_csc', 'banayoyo_csc'],
            "Ilocos Norte PO + CSCs": ['ilocosnorte_po', 'dingras_csc'],
        }

        # Generate list of last 12 months
        now_time = datetime.now()
        month_list = [
            (now_time.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
            for i in reversed(range(12))
        ]

        result = defaultdict(lambda: {month: 0 for month in month_list})

        # Travel orders grouped by month and employee_type
        orders = TravelOrder.objects.filter(submitted_at__isnull=False).annotate(
            month=TruncMonth('submitted_at')
        ).values('month', 'employees__employee_type').annotate(
            count=Count('id')
        ).order_by('month')

        for entry in orders:
            month = entry['month'].strftime('%Y-%m')
            emp_type = entry['employees__employee_type']
            for group_name, types in groups.items():
                if emp_type in types:
                    result[group_name][month] += entry['count']

        # Summary counts
        total_travel_requests = TravelOrder.objects.count()

        # Approved: All travels that have a travel order number
        approved_by_director = TravelOrder.objects.filter(
            travel_order_number__isnull=False
        ).exclude(travel_order_number='').count()

        disapproved = TravelOrder.objects.filter(
            status__in=[
                'Rejected by the CSC head.',
                'Rejected by the PO head',
                'Rejected by the TMSD chief',
                'Rejected by the AFSD Chief',
                'Rejected by the Regional Director'
            ]
        ).count()

        # Liquidation amount data by office based on employee office assignments
        liquidation_amounts = {}
        liquidations = Liquidation.objects.select_related('travel_order').prefetch_related('travel_order__itinerary', 'travel_order__employees').all()
        
        for liquidation in liquidations:
            if not liquidation.travel_order:
                continue
                
            # Get office from employee assignments
            employees = liquidation.travel_order.employees.all()
            office_name = 'Unknown Office'
            
            if employees.exists():
                # Get the first employee's office type to determine office
                first_employee = employees.first()
                employee_type = getattr(first_employee, 'employee_type', None)
                
                if employee_type:
                    # Map employee_type to office names
                    if employee_type in ['pangasinan_po', 'urdaneta_csc', 'sison_csc']:
                        office_name = 'Pangasinan PO and CSC'
                    elif employee_type in ['launion_po', 'sudipen_csc', 'pugo_csc']:
                        office_name = 'La Union PO and CSC'
                    elif employee_type in ['ilocossur_po', 'tagudin_csc', 'banayoyo_csc']:
                        office_name = 'Ilocos Sur PO and CSC'
                    elif employee_type in ['ilocosnorte_po', 'dingras_csc']:
                        office_name = 'Ilocos Norte PO and CSC'
                    elif employee_type in ['tmsd', 'afsd', 'regional']:
                        office_name = 'Regional Office'
                    else:
                        office_name = f"{employee_type.replace('_', ' ').title()} Office"
                else:
                    # Fallback to fund_cluster if employee_type is not set
                    fund_cluster = liquidation.travel_order.fund_cluster
                    if fund_cluster:
                        fund_cluster_lower = fund_cluster.lower()
                        if 'pangasinan' in fund_cluster_lower:
                            office_name = 'Pangasinan PO and CSC'
                        elif 'la union' in fund_cluster_lower:
                            office_name = 'La Union PO and CSC'
                        elif 'ilocos sur' in fund_cluster_lower:
                            office_name = 'Ilocos Sur PO and CSC'
                        elif 'ilocos norte' in fund_cluster_lower:
                            office_name = 'Ilocos Norte PO and CSC'
                        else:
                            office_name = f"{fund_cluster} Office"
            
            # Sum total amounts from itineraries
            office_total = 0
            if liquidation.travel_order.itinerary:
                for itinerary in liquidation.travel_order.itinerary.all():
                    office_total += float(itinerary.total_amount or 0)
            
            liquidation_amounts[office_name] = liquidation_amounts.get(office_name, 0) + office_total

        return Response({
            "labels": month_list,
            "datasets": [
                {
                    "label": group,
                    "data": [result[group][month] for month in month_list]
                } for group in groups
            ],
            "total_travel_requests": total_travel_requests,
            "approved_by_director": approved_by_director,
            "disapproved": disapproved,
            "liquidation_amounts": liquidation_amounts
        })

class HeadDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = now().date()
        start_of_month = today.replace(day=1)

        # Travel requests filed by this head
        own_orders = TravelOrder.objects.filter(prepared_by=user)
        
        # Travel requests that this head has approved (using approval snapshots)
        approved_by_head = TravelOrderApprovalSnapshot.objects.filter(approved_by=user).values_list('travel_order', flat=True)
        approved_travel_orders = TravelOrder.objects.filter(id__in=approved_by_head)
        
        # Travel requests that this head has rejected
        rejected_by_head = TravelOrder.objects.filter(
            rejected_by=user,
            status__icontains='rejected'
        )

        # Pending approvals for this head
        pending_approvals = TravelOrder.objects.filter(
            current_approver=user, 
            status__icontains='placed'
        )

        # Travel requests filed by this head that were approved by Regional Director
        approved_by_regional_director = own_orders.filter(
            status__icontains='approved by the regional director'
        )

        # Travel requests filed by this head that were rejected by Regional Director
        rejected_by_regional_director = own_orders.filter(
            status__icontains='rejected by the regional director'
        )

        # Get all travel orders the head has access to (prepared by them OR approved by them)
        all_accessible_orders = TravelOrder.objects.filter(
            Q(prepared_by=user) | Q(id__in=approved_by_head)
        ).distinct()

        # Calculate date range: 6 months back and 12 months forward from today for calendar
        # This allows the calendar to show travel orders when users navigate between months
        # Start: 6 months before current month
        if today.month <= 6:
            start_range = today.replace(year=today.year - 1, month=today.month + 6, day=1)
        else:
            start_range = today.replace(month=today.month - 6, day=1)
        
        # End: 12 months after current month
        end_year = today.year
        end_month = today.month + 12
        if end_month > 12:
            end_year += end_month // 12
            end_month = ((end_month - 1) % 12) + 1
        
        # Get last day of that month
        if end_month == 12:
            end_range = today.replace(year=end_year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_range = today.replace(year=end_year, month=end_month + 1, day=1) - timedelta(days=1)

        # Filter travel orders by travel dates that fall within the date range
        # A travel order should appear if its travel dates overlap with the range
        calendar_orders = all_accessible_orders.filter(
            Q(date_travel_from__lte=end_range, date_travel_from__gte=start_range) |  # Starts in range
            Q(date_travel_to__gte=start_range, date_travel_to__lte=end_range) |  # Ends in range
            Q(date_travel_from__lte=start_range, date_travel_to__gte=end_range)  # Spans the entire range
        ).exclude(date_travel_from__isnull=True).exclude(date_travel_to__isnull=True)
        
        serializer = TravelOrderSerializer(calendar_orders, many=True, context={'request': request})

        # Total claims (liquidations) filed by this head
        total_claims = Liquidation.objects.filter(
            travel_order__prepared_by=user
        ).count()

        data = {
            'counts': {
                # Travel requests filed by this head
                'total_travel_request': own_orders.count(),
                'total_claims': total_claims,
                # Travels approved by Regional Director (from travels filed by this head)
                'approve_travel_request': approved_by_regional_director.count(),
                # Travels disapproved by Regional Director (from travels filed by this head)
                'disapprove_travel_request': rejected_by_regional_director.count(),
                
                # Approval activities by this head
                'pending_approvals': pending_approvals.count(),
                # Travels approved by this head
                'approved_travels': approved_travel_orders.count(),
                # Travels rejected by this head
                'rejected_travels': rejected_by_head.count(),
            },
            'travel_orders': serializer.data
        }

        return Response(data)

class HeadApprovalHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Travel requests that this head has approved (using approval snapshots)
        approved_by_head = TravelOrderApprovalSnapshot.objects.filter(approved_by=user).values_list('travel_order', flat=True)
        approved_orders = TravelOrder.objects.filter(id__in=approved_by_head).order_by('-submitted_at')
        
        # Travel requests that this head has rejected
        rejected_orders = TravelOrder.objects.filter(
            rejected_by=user,
            status__icontains='rejected'
        ).order_by('-submitted_at')
        
        approved_serializer = TravelOrderSerializer(approved_orders, many=True)
        rejected_serializer = TravelOrderSerializer(rejected_orders, many=True)
        
        return Response({
            'approved': approved_serializer.data,
            'rejected': rejected_serializer.data
        })
    
class DirectorDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.user_level != 'director':
            return Response({'error': 'Unauthorized'}, status=403)

        today = now().date()
        start_of_month = today.replace(day=1)

        # Travel requests filed by this director
        own_orders = TravelOrder.objects.filter(prepared_by=user)
        
        # Travel requests that this director has approved (using approval snapshots)
        approved_by_director = TravelOrderApprovalSnapshot.objects.filter(approved_by=user).values_list('travel_order', flat=True)
        approved_travel_orders = TravelOrder.objects.filter(id__in=approved_by_director)
        
        # Travel requests that this director has rejected
        rejected_by_director = TravelOrder.objects.filter(
            rejected_by=user,
            status__icontains='rejected'
        )

        # Pending approvals for this director
        pending_approvals = TravelOrder.objects.filter(
            current_approver=user, 
            status__icontains='placed'
        )

        # === MONTH LIST (12 MONTHS) ===
        now = datetime.now()
        month_list = [
            (now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
            for i in reversed(range(12))
        ]

        groups = {
            "Pangasinan PO + CSCs": ['pangasinan_po', 'urdaneta_csc', 'sison_csc'],
            "La Union PO + CSCs": ['launion_po', 'sudipen_csc', 'pugo_csc'],
            "Ilocos Sur PO + CSCs": ['ilocossur_po', 'tagudin_csc', 'banayoyo_csc'],
            "Ilocos Norte PO + CSCs": ['ilocosnorte_po', 'dingras_csc'],
        }

        result = defaultdict(lambda: {month: 0 for month in month_list})

        orders = TravelOrder.objects.filter(submitted_at__isnull=False).annotate(
            month=TruncMonth('submitted_at')
        ).values('month', 'employees__employee_type').annotate(count=Count('id'))

        for entry in orders:
            month = entry['month'].strftime('%Y-%m')
            emp_type = entry['employees__employee_type']
            for group_name, types in groups.items():
                if emp_type in types:
                    result[group_name][month] += entry['count']

        chart_data = {
            "labels": month_list,
            "datasets": [
                {
                    "label": group,
                    "data": [result[group][month] for month in month_list]
                } for group in groups
            ]
        }

        # Current month travel orders for calendar
        current_month_orders = own_orders.filter(
            submitted_at__date__gte=start_of_month
        ).values(
            'destination', 'date_travel_from', 'date_travel_to', 'status'
        )

        return Response({
            "stats": {
                # Travel requests filed by this director
                "total_travel_request": own_orders.count(),
                "approve_travel_request": approved_travel_orders.count(),
                "disapprove_travel_request": rejected_by_director.count(),
                
                # Approval activities by this director
                "pending_approvals": pending_approvals.count(),
                "approved_travels": approved_travel_orders.count(),
                "rejected_travels": rejected_by_director.count(),
            },
            "travel_orders": list(current_month_orders),
            "chart": chart_data
        })
    
class TravelOrderReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            return Response({"error": "Start date and end date are required."}, status=400)

        queryset = TravelOrder.objects.filter(
            date_travel_from__gte=parse_date(start_date),
            date_travel_to__lte=parse_date(end_date)
        ).order_by('date_travel_from')

        serializer = TravelOrderReportSerializer(queryset, many=True)
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_evidence(request, travel_order_id):
    """
    Download evidence file for a travel order with proper authentication and headers
    """
    try:
        travel_order = get_object_or_404(TravelOrder, id=travel_order_id)
        
        # Check if user has permission to view this travel order
        user = request.user
        if user.user_level not in ['admin', 'director']:
            # Check if user is involved in this travel order
            if not (travel_order.prepared_by == user or travel_order.employees.filter(id=user.id).exists()):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        if not travel_order.evidence:
            return Response({'error': 'No evidence file found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the file path
        file_path = travel_order.evidence.path
        
        if not os.path.exists(file_path):
            return Response({'error': 'File not found on server'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get file info
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Read file and create response
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{file_name}"'
            response['Content-Length'] = file_size
            response['Access-Control-Allow-Origin'] = 'http://localhost:5173'
            response['Access-Control-Allow-Credentials'] = 'true'
            return response
            
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- NOTIFICATION VIEWS ---
class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get all notifications for the current user"""
        notifications = Notification.objects.filter(user=request.user)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)


class NotificationMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        """Mark a specific notification as read"""
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({"message": "Notification marked as read"}, status=200)
        except Notification.DoesNotExist:
            return Response({"error": "Notification not found"}, status=404)


class NotificationMarkAllReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        """Mark all notifications as read for the current user"""
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read"}, status=200)


class NotificationCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get count of unread notifications"""
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count}, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_email_notification(request):
    """Test endpoint to send a test email notification"""
    try:
        # Get the first travel order for testing
        travel_order = TravelOrder.objects.first()
        if not travel_order:
            return Response({'error': 'No travel orders found for testing'}, status=404)
        
        # Send test email
        success = send_notification_email(
            user=request.user,
            travel_order=travel_order,
            notification_type='travel_approved',
            title='Test Email Notification',
            message='This is a test email notification to verify email functionality.'
        )
        
        if success:
            return Response({'message': 'Test email sent successfully'})
        else:
            return Response({'error': 'Failed to send test email'}, status=500)
            
    except Exception as e:
        return Response({'error': f'Error sending test email: {str(e)}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_token_validity(request):
    """Check if the current token is valid and return server time"""
    try:
        return Response({
            'valid': True,
            'server_time': timezone.now().isoformat(),
            'user_id': request.user.id,
            'message': 'Token is valid'
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def debug_travel_order(request, pk):
    """Debug endpoint to check travel order approval status"""
    try:
        order = get_object_or_404(TravelOrder, pk=pk)
        user = request.user
        
        # Get approval chain for the prepared_by user
        filer = order.prepared_by
        filer_chain = get_approval_chain(filer) if filer else []
        
        # Get what the next head should be at current stage
        next_head_should_be = get_next_head(filer_chain, order.approval_stage, current_user=user) if filer else None
        
        return Response({
            'travel_order_id': pk,
            'current_user_id': user.id,
            'current_user_email': user.email,
            'current_user_employee_type': user.employee_type,
            'current_user_level': user.user_level,
            'current_approver_id': order.current_approver.id if order.current_approver else None,
            'current_approver_email': order.current_approver.email if order.current_approver else None,
            'current_approver_employee_type': order.current_approver.employee_type if order.current_approver else None,
            'current_approver_level': order.current_approver.user_level if order.current_approver else None,
            'status': order.status,
            'approval_stage': order.approval_stage,
            'can_approve': order.current_approver == user,
            'prepared_by_id': order.prepared_by.id if order.prepared_by else None,
            'prepared_by_email': order.prepared_by.email if order.prepared_by else None,
            'prepared_by_employee_type': order.prepared_by.employee_type if order.prepared_by else None,
            'prepared_by_level': order.prepared_by.user_level if order.prepared_by else None,
            'filer_approval_chain': filer_chain,
            'next_head_should_be_id': next_head_should_be.id if next_head_should_be else None,
            'next_head_should_be_email': next_head_should_be.email if next_head_should_be else None,
            'next_head_should_be_employee_type': next_head_should_be.employee_type if next_head_should_be else None,
            'next_head_should_be_level': next_head_should_be.user_level if next_head_should_be else None,
        })
    except Exception as e:
        return Response({'error': f'Error getting travel order debug info: {str(e)}'}, status=500)


# --- AUDIT LOG VIEWS ---
class AuditLogListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get audit logs with filtering and pagination"""
        # Only admins can view audit logs
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can view audit logs"}, status=403)
        
        # Get query parameters
        user_id = request.query_params.get('user_id')
        action = request.query_params.get('action')
        resource_type = request.query_params.get('resource_type')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        search = request.query_params.get('search')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        
        # Start with all audit logs
        queryset = AuditLog.objects.all()
        
        # Apply filters
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if action:
            queryset = queryset.filter(action=action)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        if start_date:
            try:
                start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=start_date)
            except ValueError:
                pass
        if end_date:
            try:
                end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=end_date)
            except ValueError:
                pass
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(resource_name__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__email__icontains=search)
            )
        
        # Get total count
        total_count = queryset.count()
        
        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        queryset = queryset[start:end]
        
        # Serialize the data
        serializer = AuditLogSerializer(queryset, many=True)
        
        return Response({
            'results': serializer.data,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })


# --- BACKUP AND RESTORE UTILITIES ---
import subprocess
import threading
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.core.management import call_command
from io import StringIO
import tempfile
import shutil


def create_database_backup(backup_obj):
    """Create a database backup using Django's dumpdata command with SQL output"""
    try:
        backup_obj.status = 'in_progress'
        backup_obj.save()
        
        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{backup_obj.name}_{timestamp}.sql"
        file_path = os.path.join(backup_dir, filename)
        
        # Get database settings
        db_settings = settings.DATABASES['default']
        
        # Create SQL backup based on backup type
        if backup_obj.backup_type == 'full':
            # Full database backup using pg_dump or mysqldump
            if db_settings['ENGINE'] == 'django.db.backends.postgresql':
                cmd = [
                    'pg_dump',
                    '--host', db_settings.get('HOST', 'localhost'),
                    '--port', str(db_settings.get('PORT', 5432)),
                    '--username', db_settings.get('USER', ''),
                    '--dbname', db_settings.get('NAME', ''),
                    '--no-password',  # Use .pgpass or environment variables
                    '--format', 'plain',
                    '--file', file_path
                ]
            elif db_settings['ENGINE'] == 'django.db.backends.mysql':
                cmd = [
                    'mysqldump',
                    '--host', db_settings.get('HOST', 'localhost'),
                    '--port', str(db_settings.get('PORT', 3306)),
                    '--user', db_settings.get('USER', ''),
                    '--password=' + db_settings.get('PASSWORD', ''),
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    db_settings.get('NAME', ''),
                    '--result-file=' + file_path
                ]
            else:
                # Fallback to SQLite or use dumpdata for other databases
                with open(file_path, 'w', encoding='utf-8') as f:
                    call_command('dumpdata', '--indent', '2', '--format', 'json', stdout=f)
                # Convert JSON to SQL-like format
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"-- SQL Backup generated from JSON dumpdata\n")
                    f.write(f"-- Backup Name: {backup_obj.name}\n")
                    f.write(f"-- Created: {timezone.now()}\n")
                    f.write(f"-- Type: {backup_obj.backup_type}\n\n")
                    f.write(f"-- JSON Data:\n{json_data}")
        elif backup_obj.backup_type == 'data_only':
            # Data only backup
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Data Only Backup\n")
                f.write(f"-- Backup Name: {backup_obj.name}\n")
                f.write(f"-- Created: {timezone.now()}\n\n")
                call_command('dumpdata', '--indent', '2', '--format', 'json', stdout=f)
            
            # Convert JSON to SQL-like format with proper JSON Data marker
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = f.read()
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Data Only Backup\n")
                f.write(f"-- Backup Name: {backup_obj.name}\n")
                f.write(f"-- Created: {timezone.now()}\n\n")
                f.write(f"-- JSON Data:\n{json_data}")
        else:  # schema_only
            # Schema only backup
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Schema Only Backup\n")
                f.write(f"-- Backup Name: {backup_obj.name}\n")
                f.write(f"-- Created: {timezone.now()}\n\n")
                call_command('dumpdata', '--indent', '2', '--format', 'json', '--exclude', 'contenttypes', '--exclude', 'auth.Permission', stdout=f)
            
            # Convert JSON to SQL-like format with proper JSON Data marker
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = f.read()
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Schema Only Backup\n")
                f.write(f"-- Backup Name: {backup_obj.name}\n")
                f.write(f"-- Created: {timezone.now()}\n\n")
                f.write(f"-- JSON Data:\n{json_data}")
        
        # Execute database-specific backup command if applicable
        if backup_obj.backup_type == 'full' and db_settings['ENGINE'] in ['django.db.backends.postgresql', 'django.db.backends.mysql']:
            try:
                # Check if the database command is available
                if db_settings['ENGINE'] == 'django.db.backends.mysql':
                    # Check if mysqldump is available
                    try:
                        subprocess.run(['mysqldump', '--version'], check=True, capture_output=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        raise FileNotFoundError("mysqldump not available")
                elif db_settings['ENGINE'] == 'django.db.backends.postgresql':
                    # Check if pg_dump is available
                    try:
                        subprocess.run(['pg_dump', '--version'], check=True, capture_output=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        raise FileNotFoundError("pg_dump not available")
                
                # Execute the backup command
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                
                # Verify the file was created and has content
                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    raise Exception("Backup file was not created or is empty")
                    
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"Database command failed: {e}")
                print("Falling back to Django dumpdata...")
                # Fallback to dumpdata if database command fails
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"-- SQL Backup (Django dumpdata fallback)\n")
                    f.write(f"-- Backup Name: {backup_obj.name}\n")
                    f.write(f"-- Created: {timezone.now()}\n")
                    f.write(f"-- Reason: {str(e)}\n\n")
                    call_command('dumpdata', '--indent', '2', '--format', 'json', stdout=f)
                
                # Convert JSON to SQL-like format with proper JSON Data marker
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"-- SQL Backup (Django dumpdata fallback)\n")
                    f.write(f"-- Backup Name: {backup_obj.name}\n")
                    f.write(f"-- Created: {timezone.now()}\n")
                    f.write(f"-- Reason: {str(e)}\n\n")
                    f.write(f"-- JSON Data:\n{json_data}")
        
        # Update backup object
        backup_obj.file_path = file_path
        backup_obj.file_size = os.path.getsize(file_path)
        backup_obj.status = 'completed'
        backup_obj.completed_at = timezone.now()
        backup_obj.save()
        
        # Log backup creation
        log_audit_event(
            user=backup_obj.created_by,
            action='create',
            resource_type='system',
            resource_id=backup_obj.id,
            resource_name=f"Backup: {backup_obj.name}",
            description=f'Created {backup_obj.backup_type} SQL backup: {backup_obj.name}',
            metadata={'backup_type': backup_obj.backup_type, 'file_size': backup_obj.file_size, 'file_type': 'sql'}
        )
        
    except Exception as e:
        backup_obj.status = 'failed'
        backup_obj.save()
        print(f"Backup failed: {str(e)}")


def restore_database(restore_obj, allow_database_clear=False):
    """Restore database from SQL backup file
    
    Args:
        restore_obj: The restore object
        allow_database_clear: If True, allows clearing database as last resort (DANGEROUS)
    """
    try:
        restore_obj.status = 'in_progress'
        restore_obj.save()
        
        # Get database settings
        db_settings = settings.DATABASES['default']
        
        # Optional: Clear existing data to avoid conflicts
        # Uncomment the next line if you want to clear the database before restore
        # call_command('flush', '--noinput', verbosity=0)
        
        # Create a temporary file for the restore
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.sql', delete=False, encoding='utf-8') as temp_file:
                temp_file_path = temp_file.name
                # Read the uploaded backup file with proper encoding
                # Django FileField doesn't support encoding parameter, so we always read as binary first
                with restore_obj.backup_file.open('rb') as backup_file:
                    content_bytes = backup_file.read()
                    if not content_bytes:
                        raise Exception("Backup file is empty or could not be read")
                    # Try to decode with UTF-8, fallback to latin-1 if needed
                    try:
                        content_text = content_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        print("UTF-8 decode failed, trying latin-1...")
                        content_text = content_bytes.decode('latin-1', errors='replace')
                    temp_file.write(content_text)
                temp_file.flush()
                
                # Verify the temp file was written correctly
                if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
                    raise Exception("Temporary backup file is empty or was not created")
                
                # Check if it's a SQL file or JSON fallback
                with open(temp_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content or len(content.strip()) == 0:
                    raise Exception("Backup file appears to be empty or contains no data")
            
            # Debug: Check the backup file content
            print(f"Backup file content length: {len(content)}")
            print(f"Backup file content preview: {content[:500]}...")
            print(f"Contains '-- JSON Data:': {'-- JSON Data:' in content}")
            
            # Check if it's a JSON backup (from Django dumpdata) or SQL backup
            # Priority 1: Check for Django dumpdata JSON content first
            if '-- JSON Data:' in content:
                # It's a Django dumpdata backup with JSON content
                print("Detected Django dumpdata backup with JSON content")
                json_start = content.find('-- JSON Data:') + len('-- JSON Data:')
                json_content = content[json_start:].strip()
                
                # Debug: Check what we extracted
                print(f"JSON content length: {len(json_content)}")
                print(f"JSON content preview: {json_content[:200]}...")
                
                if not json_content:
                    print("ERROR: No JSON content found after '-- JSON Data:' marker")
                    raise Exception("Backup file contains no JSON data after '-- JSON Data:' marker")
                
                # Clean the JSON content - remove any SQL comments that might be included
                lines = json_content.split('\n')
                json_lines = []
                in_json = False
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Check if this line starts JSON (array or object)
                    if line.startswith('[') or line.startswith('{'):
                        in_json = True
                    # Skip SQL comment lines
                    if line.startswith('--'):
                        continue
                    # Only include lines when we're in JSON content
                    if in_json:
                        json_lines.append(line)
                
                # Join the cleaned JSON lines
                cleaned_json = '\n'.join(json_lines)
                print(f"Cleaned JSON content length: {len(cleaned_json)}")
                print(f"Cleaned JSON preview: {cleaned_json[:200]}...")
                
                if not cleaned_json:
                    print("ERROR: No valid JSON content found after cleaning")
                    raise Exception("Backup file contains no valid JSON data after cleaning")
                
                # Use the cleaned JSON content
                json_content = cleaned_json
                
                # Save as JSON and use loaddata with multiple strategies
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False, encoding='utf-8') as json_file:
                    json_file.write(json_content)
                    json_file.flush()
                    print(f"Using Django loaddata to restore from JSON file: {json_file.name}")
                    
                    # Debug: Verify the JSON file was written correctly
                    with open(json_file.name, 'r', encoding='utf-8') as f:
                        written_content = f.read()
                    print(f"Written JSON file length: {len(written_content)}")
                    print(f"Written JSON preview: {written_content[:200]}...")
                    
                    # Try multiple loaddata strategies to handle conflicts
                    try:
                        # Strategy 1: Try with ignore conflicts
                        print("Attempting loaddata with ignore_conflicts=True...")
                        call_command('loaddata', json_file.name, verbosity=2, ignorenonexistent=True)
                        print("Loaddata completed successfully!")
                    except Exception as e1:
                        print(f"Strategy 1 failed: {e1}")
                        print(f"Strategy 1 detailed error: {str(e1)}")
                        try:
                            # Strategy 2: Try with natural keys
                            print("Attempting loaddata with natural keys...")
                            call_command('loaddata', json_file.name, verbosity=2, ignorenonexistent=True)
                            print("Loaddata with natural keys completed successfully!")
                        except Exception as e2:
                            print(f"Strategy 2 failed: {e2}")
                            print(f"Strategy 2 detailed error: {str(e2)}")
                            try:
                                # Strategy 3: Try standard loaddata
                                print("Attempting standard loaddata...")
                                call_command('loaddata', json_file.name, verbosity=2)
                                print("Standard loaddata completed successfully!")
                            except Exception as e3:
                                print(f"Strategy 3 failed: {e3}")
                                print(f"Strategy 3 detailed error: {str(e3)}")
                                
                                # Strategy 4: Try to clean the JSON data
                                print("Attempting to clean JSON data...")
                                try:
                                    # json and os are already imported at the top of the file
                                    
                                    # Check if file exists and has content
                                    if not os.path.exists(json_file.name) or os.path.getsize(json_file.name) == 0:
                                        print("JSON file is empty or doesn't exist")
                                        raise Exception("JSON file is empty")
                                    
                                    with open(json_file.name, 'r', encoding='utf-8') as f:
                                        content = f.read().strip()
                                    
                                    if not content:
                                        print("JSON file content is empty")
                                        raise Exception("JSON file content is empty")
                                    
                                    data = json.loads(content)
                                    
                                    # First pass: Build a map of valid primary keys for each model
                                    valid_pks = {}  # {model_name: set of valid pks}
                                    for item in data:
                                        model_name = item.get('model', '')
                                        pk = item.get('pk')
                                        if pk and pk != 0:
                                            if model_name not in valid_pks:
                                                valid_pks[model_name] = set()
                                            valid_pks[model_name].add(pk)
                                    
                                    # Map foreign key field names to their target models
                                    fk_model_map = {
                                        'travel_order_id': 'api1.travelorder',
                                        'travel_order': 'api1.travelorder',
                                        'user_id': 'api1.customuser',
                                        'user': 'api1.customuser',
                                        'created_by_id': 'api1.customuser',
                                        'created_by': 'api1.customuser',
                                        'restored_by_id': 'api1.customuser',
                                        'restored_by': 'api1.customuser',
                                        'uploaded_by_id': 'api1.customuser',
                                        'uploaded_by': 'api1.customuser',
                                        'prepared_by': 'api1.customuser',  # ManyToMany, but we'll check individual IDs
                                        'purpose_id': 'api1.purpose',
                                        'purpose': 'api1.purpose',
                                        'fund_id': 'api1.fund',
                                        'fund': 'api1.fund',
                                        'original_backup_id': 'api1.backup',
                                        'original_backup': 'api1.backup',
                                    }
                                    
                                    # Filter out problematic records
                                    cleaned_data = []
                                    skipped_count = 0
                                    
                                    for item in data:
                                        try:
                                            # Skip records with invalid primary keys (AutoField doesn't accept 0)
                                            if 'pk' in item and item['pk'] == 0:
                                                print(f"Skipping record with pk=0: {item.get('model', 'unknown')}")
                                                skipped_count += 1
                                                continue
                                            
                                            model_name = item.get('model', '')
                                            fields = item.get('fields', {})
                                            
                                            # Skip audit log and admin log entries with invalid foreign keys (they're not critical)
                                            if model_name in ['api1.auditlog', 'admin.logentry']:
                                                user_id = fields.get('user')
                                                if user_id and user_id not in valid_pks.get('api1.customuser', set()):
                                                    skipped_count += 1
                                                    continue
                                            
                                            # Check foreign key references
                                            skip_record = False
                                            for field_name, field_value in fields.items():
                                                if field_value is None or field_value == '':
                                                    continue
                                                
                                                # Handle ManyToMany fields (arrays)
                                                if isinstance(field_value, list):
                                                    if field_name == 'prepared_by':  # ManyToMany field
                                                        # Check if all referenced users exist
                                                        for user_id in field_value:
                                                            if user_id and user_id not in valid_pks.get('api1.customuser', set()):
                                                                print(f"Skipping {model_name} pk={item.get('pk')} with invalid prepared_by user_id={user_id}")
                                                                skip_record = True
                                                                break
                                                        if skip_record:
                                                            break
                                                    continue
                                                
                                                # Check if this field references another model
                                                target_model = fk_model_map.get(field_name)
                                                
                                                # If not in map, try to infer from _id suffix
                                                if not target_model and field_name.endswith('_id') and field_value and field_value != 0:
                                                    base_name = field_name[:-3]  # Remove '_id'
                                                    # Common patterns
                                                    if base_name == 'travel_order':
                                                        target_model = 'api1.travelorder'
                                                    elif base_name in ['user', 'created_by', 'restored_by', 'uploaded_by']:
                                                        target_model = 'api1.customuser'
                                                    elif base_name == 'purpose':
                                                        target_model = 'api1.purpose'
                                                    elif base_name == 'fund':
                                                        target_model = 'api1.fund'
                                                    elif base_name == 'original_backup':
                                                        target_model = 'api1.backup'
                                                
                                                # Check foreign key references
                                                if target_model and field_value:
                                                    if field_value not in valid_pks.get(target_model, set()):
                                                        print(f"Skipping {model_name} pk={item.get('pk')} with invalid foreign key {field_name}={field_value} (target {target_model} doesn't exist)")
                                                        skip_record = True
                                                        skipped_count += 1
                                                        break
                                            
                                            if not skip_record:
                                                cleaned_data.append(item)
                                                
                                        except Exception as clean_error:
                                            print(f"Skipping problematic record: {clean_error}")
                                            skipped_count += 1
                                            continue
                                    
                                    # Write cleaned data
                                    with open(json_file.name, 'w', encoding='utf-8') as f:
                                        json.dump(cleaned_data, f)
                                    
                                    print(f"Cleaned {skipped_count} problematic records (kept {len(cleaned_data)} out of {len(data)})")
                                    
                                    # Try loading in dependency order to avoid foreign key issues
                                    # Group by model and load base models first
                                    model_order = [
                                        'contenttypes.contenttype',  # Content types first
                                        'auth.permission',
                                        'auth.group',
                                        'api1.customuser',  # Users before anything that references them
                                        'api1.fund',
                                        'api1.purpose',
                                        'api1.specificrole',
                                        'api1.transportation',
                                        'api1.employeeposition',
                                        'api1.travelorder',  # Travel orders before liquidations
                                        'api1.liquidation',
                                        'api1.aftertravelreport',
                                        'api1.certificateoftravel',
                                        'api1.certificateofappearance',
                                        'api1.itinerary',
                                        'api1.signature',
                                        'api1.employeesignature',
                                        'api1.notification',
                                        'api1.backup',
                                        'api1.restore',
                                    ]
                                    
                                    # Group cleaned data by model
                                    data_by_model = {}
                                    for item in cleaned_data:
                                        model = item.get('model', '')
                                        if model not in data_by_model:
                                            data_by_model[model] = []
                                        data_by_model[model].append(item)
                                    
                                    # Try loading in order
                                    loaded_models = []
                                    failed_models = []
                                    
                                    # First, try loading all models in dependency order
                                    for model_name in model_order:
                                        if model_name in data_by_model:
                                            model_file_path = None
                                            try:
                                                # Create a temporary file with just this model's data
                                                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False, encoding='utf-8') as model_file:
                                                    model_file_path = model_file.name
                                                    json.dump(data_by_model[model_name], model_file)
                                                    model_file.flush()
                                                
                                                # File is now closed, safe to use
                                                try:
                                                    call_command('loaddata', model_file_path, verbosity=0, ignorenonexistent=True)
                                                    loaded_models.append(model_name)
                                                    print(f"Successfully loaded {model_name} ({len(data_by_model[model_name])} records)")
                                                except Exception as model_error:
                                                    print(f"Failed to load {model_name}: {model_error}")
                                                    failed_models.append((model_name, str(model_error)))
                                                
                                            except Exception as e:
                                                print(f"Error processing {model_name}: {e}")
                                                failed_models.append((model_name, str(e)))
                                            finally:
                                                # Clean up the temporary file (with retry for Windows)
                                                if model_file_path and os.path.exists(model_file_path):
                                                    max_retries = 3
                                                    for retry in range(max_retries):
                                                        try:
                                                            # Small delay to ensure file is released
                                                            import time
                                                            if retry > 0:
                                                                time.sleep(0.5)
                                                            os.unlink(model_file_path)
                                                            break
                                                        except (OSError, PermissionError) as unlink_error:
                                                            if retry == max_retries - 1:
                                                                print(f"Warning: Could not delete temporary file {model_file_path}: {unlink_error}")
                                                            else:
                                                                print(f"Retrying file deletion (attempt {retry + 1}/{max_retries})...")
                                                        except Exception as unlink_error:
                                                            print(f"Warning: Could not delete temporary file {model_file_path}: {unlink_error}")
                                                            break
                                    
                                    # Then try loading any remaining models not in the order list
                                    for model_name, model_data in data_by_model.items():
                                        if model_name not in model_order:
                                            model_file_path = None
                                            try:
                                                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False, encoding='utf-8') as model_file:
                                                    model_file_path = model_file.name
                                                    json.dump(model_data, model_file)
                                                    model_file.flush()
                                                
                                                # File is now closed, safe to use
                                                try:
                                                    call_command('loaddata', model_file_path, verbosity=0, ignorenonexistent=True)
                                                    loaded_models.append(model_name)
                                                    print(f"Successfully loaded {model_name} ({len(model_data)} records)")
                                                except Exception as model_error:
                                                    print(f"Failed to load {model_name}: {model_error}")
                                                    failed_models.append((model_name, str(model_error)))
                                                
                                            except Exception as e:
                                                print(f"Error processing {model_name}: {e}")
                                                failed_models.append((model_name, str(e)))
                                            finally:
                                                # Clean up the temporary file (with retry for Windows)
                                                if model_file_path and os.path.exists(model_file_path):
                                                    max_retries = 3
                                                    for retry in range(max_retries):
                                                        try:
                                                            # Small delay to ensure file is released
                                                            import time
                                                            if retry > 0:
                                                                time.sleep(0.5)
                                                            os.unlink(model_file_path)
                                                            break
                                                        except (OSError, PermissionError) as unlink_error:
                                                            if retry == max_retries - 1:
                                                                print(f"Warning: Could not delete temporary file {model_file_path}: {unlink_error}")
                                                            else:
                                                                print(f"Retrying file deletion (attempt {retry + 1}/{max_retries})...")
                                                        except Exception as unlink_error:
                                                            print(f"Warning: Could not delete temporary file {model_file_path}: {unlink_error}")
                                                            break
                                    
                                    # If we loaded at least some models, consider it a partial success
                                    if loaded_models:
                                        print(f"Partially restored: {len(loaded_models)} model(s) loaded successfully, {len(failed_models)} model(s) failed")
                                        if failed_models:
                                            failed_details = "; ".join([f"{m}: {e[:100]}" for m, e in failed_models[:5]])
                                            print(f"Failed models: {failed_details}")
                                        # Consider it successful if we loaded critical models
                                        critical_models = ['api1.customuser', 'api1.travelorder', 'api1.liquidation']
                                        if any(m in loaded_models for m in critical_models):
                                            print("Critical models loaded successfully - restore completed with warnings")
                                        else:
                                            raise Exception(f"Restore partially completed but critical models failed. Loaded: {', '.join(loaded_models[:5])}. Failed: {', '.join([m for m, _ in failed_models[:5]])}")
                                    else:
                                        raise Exception("No models could be loaded. All restore strategies failed.")
                                    
                                    # Clean up the original JSON file (with retry for Windows)
                                    if json_file.name and os.path.exists(json_file.name):
                                        max_retries = 3
                                        for retry in range(max_retries):
                                            try:
                                                import time
                                                if retry > 0:
                                                    time.sleep(0.5)
                                                os.unlink(json_file.name)
                                                break
                                            except (OSError, PermissionError) as cleanup_error:
                                                if retry == max_retries - 1:
                                                    print(f"Warning: Could not delete temporary file {json_file.name}: {cleanup_error}")
                                                else:
                                                    print(f"Retrying file deletion (attempt {retry + 1}/{max_retries})...")
                                            except Exception as cleanup_error:
                                                print(f"Warning: Could not delete temporary file {json_file.name}: {cleanup_error}")
                                                break
                                    
                                except Exception as e4:
                                    print(f"Strategy 4 failed: {e4}")
                                    print(f"Strategy 4 detailed error: {str(e4)}")
                                    
                                    # Strategy 5: Clear database and try again (only if allowed)
                                    if allow_database_clear:
                                        print("Attempting to clear database and restore...")
                                        try:
                                            # Clear the restored_by field BEFORE clearing database to avoid foreign key issues
                                            restore_obj.restored_by = None
                                            restore_obj.save()
                                            
                                            call_command('flush', '--noinput', verbosity=0)
                                            print("Database cleared successfully")
                                            
                                            call_command('loaddata', json_file.name, verbosity=2, ignorenonexistent=True)
                                            print("Restore after clearing completed successfully!")
                                        except Exception as e5:
                                            print(f"Strategy 5 failed: {e5}")
                                            print(f"Strategy 5 detailed error: {str(e5)}")
                                            # If all strategies fail, raise the original error
                                            raise Exception(f"All loaddata strategies failed. Last error: {e5}")
                                    else:
                                        print("Strategy 5 disabled to prevent data loss")
                                        print("All loaddata strategies failed. Restore cannot proceed without clearing database.")
                                        raise Exception("Restore failed: All strategies failed and database clearing is disabled to prevent data loss. Please check the backup file or try a different backup.")
                    
                    os.unlink(json_file.name)
                    
            # Priority 2: Check for pure JSON (starts with [ or {)
            elif content.strip().startswith('[') or content.strip().startswith('{'):
                # It's a pure JSON file - use loaddata with multiple strategies
                print("Detected pure JSON backup file")
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False, encoding='utf-8') as json_file:
                    json_file.write(content)
                    json_file.flush()
                    
                    # Try multiple loaddata strategies to handle conflicts
                    try:
                        # Strategy 1: Try with ignore conflicts
                        print("Attempting loaddata with ignore_conflicts=True...")
                        call_command('loaddata', json_file.name, verbosity=0, ignorenonexistent=True)
                        print("Loaddata completed successfully!")
                    except Exception as e1:
                        print(f"Strategy 1 failed: {e1}")
                        try:
                            # Strategy 2: Try standard loaddata
                            print("Attempting standard loaddata...")
                            call_command('loaddata', json_file.name, verbosity=0)
                            print("Standard loaddata completed successfully!")
                        except Exception as e2:
                            print(f"Strategy 2 failed: {e2}")
                            raise Exception(f"All loaddata strategies failed. Last error: {e2}")
                    
                    os.unlink(json_file.name)
                    
            # Priority 3: Check for native SQL files (only if database commands are available)
            elif content.strip().startswith('--') or 'CREATE TABLE' in content.upper():
                # It's a native SQL file - try database-specific restore
                print("Detected native SQL backup file")
                
                # Check if database commands are available first
                use_native_restore = False
                if db_settings['ENGINE'] == 'django.db.backends.mysql':
                    try:
                        subprocess.run(['mysql', '--version'], check=True, capture_output=True)
                        use_native_restore = True
                        print("MySQL command available, using native restore")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        print("MySQL command not available, falling back to loaddata")
                elif db_settings['ENGINE'] == 'django.db.backends.postgresql':
                    try:
                        subprocess.run(['psql', '--version'], check=True, capture_output=True)
                        use_native_restore = True
                        print("PostgreSQL command available, using native restore")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        print("PostgreSQL command not available, falling back to loaddata")
                
                if use_native_restore:
                    try:
                        if db_settings['ENGINE'] == 'django.db.backends.postgresql':
                            cmd = [
                                'psql',
                                '--host', db_settings.get('HOST', 'localhost'),
                                '--port', str(db_settings.get('PORT', 5432)),
                                '--username', db_settings.get('USER', ''),
                                '--dbname', db_settings.get('NAME', ''),
                                '--file', temp_file.name
                            ]
                            subprocess.run(cmd, check=True, capture_output=True, text=True)
                        elif db_settings['ENGINE'] == 'django.db.backends.mysql':
                            cmd = f"mysql --host={db_settings.get('HOST', 'localhost')} --port={db_settings.get('PORT', 3306)} --user={db_settings.get('USER', '')} --password={db_settings.get('PASSWORD', '')} {db_settings.get('NAME', '')} < {temp_file.name}"
                            subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Native restore failed: {e}")
                        print("Falling back to loaddata...")
                        use_native_restore = False
                
                if not use_native_restore:
                    # Fallback to loaddata - try to extract JSON or use the SQL content
                    print("Using Django loaddata fallback")
                    if '-- JSON Data:' in content:
                        json_start = content.find('-- JSON Data:') + len('-- JSON Data:')
                        json_content = content[json_start:].strip()
                    else:
                        # If it's pure SQL, we can't use loaddata - this is a limitation
                        raise Exception("Native SQL backup cannot be restored without database commands. Please use a JSON backup created by Django dumpdata.")
                    
                    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False, encoding='utf-8') as json_file:
                        json_file.write(json_content)
                        json_file.flush()
                        
                        # Try multiple loaddata strategies to handle conflicts
                        try:
                            # Strategy 1: Try with ignore conflicts
                            print("Attempting loaddata with ignore_conflicts=True...")
                            call_command('loaddata', json_file.name, verbosity=0, ignorenonexistent=True)
                            print("Loaddata completed successfully!")
                        except Exception as e1:
                            print(f"Strategy 1 failed: {e1}")
                            try:
                                # Strategy 2: Try standard loaddata
                                print("Attempting standard loaddata...")
                                call_command('loaddata', json_file.name, verbosity=0)
                                print("Standard loaddata completed successfully!")
                            except Exception as e2:
                                print(f"Strategy 2 failed: {e2}")
                                raise Exception(f"All loaddata strategies failed. Last error: {e2}")
                        
                        os.unlink(json_file.name)
        finally:
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    print(f"Warning: Could not delete temporary file {temp_file_path}: {cleanup_error}")
        
        restore_obj.status = 'completed'
        restore_obj.completed_at = timezone.now()
        
        # Try to save the restore object, but handle foreign key issues gracefully
        try:
            restore_obj.save()
        except Exception as save_error:
            print(f"Warning: Could not save restore object status: {save_error}")
            # Continue without failing the restore operation
        
        # Log restore operation (handle case where user was cleared)
        try:
            log_audit_event(
                user=restore_obj.restored_by,
                action='restore',
                resource_type='system',
                resource_id=restore_obj.id,
                resource_name=f"Restore from {restore_obj.backup_file.name}",
                description=f'Restored database from SQL backup file: {restore_obj.backup_file.name}',
            metadata={'original_backup': restore_obj.original_backup.name if restore_obj.original_backup else None, 'file_type': 'sql'}
        )
        except Exception as log_error:
            print(f"Warning: Could not log restore operation: {log_error}")
            # Continue without failing the restore operation
        
    except Exception as e:
        error_msg = str(e)
        # Truncate error message if too long (database field limit)
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "... (truncated)"
        
        restore_obj.status = 'failed'
        restore_obj.error_message = error_msg
        try:
            restore_obj.save()
        except Exception as save_error:
            print(f"Error saving failed restore status: {save_error}")
            # Try to update just the status and error_message directly
            try:
                Restore.objects.filter(pk=restore_obj.pk).update(
                    status='failed',
                    error_message=error_msg
                )
            except Exception as update_error:
                print(f"Error updating restore status: {update_error}")
        
        print(f"Restore failed: {error_msg}")


# --- BACKUP API VIEWS ---
class BackupListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List all backups"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can view backups"}, status=403)
        
        backups = Backup.objects.all()
        serializer = BackupSerializer(backups, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new backup"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can create backups"}, status=403)
        
        serializer = BackupSerializer(data=request.data)
        if serializer.is_valid():
            backup = serializer.save(created_by=request.user)
            
            # Start backup process in background thread
            thread = threading.Thread(target=create_database_backup, args=(backup,))
            thread.daemon = True
            thread.start()
            
            return Response(BackupSerializer(backup).data, status=201)
        return Response(serializer.errors, status=400)


class BackupDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        """Get backup details"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can view backup details"}, status=403)
        
        try:
            backup = Backup.objects.get(pk=pk)
            serializer = BackupSerializer(backup)
            return Response(serializer.data)
        except Backup.DoesNotExist:
            return Response({"error": "Backup not found"}, status=404)
    
    def delete(self, request, pk):
        """Delete a backup"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can delete backups"}, status=403)
        
        try:
            backup = Backup.objects.get(pk=pk)
            
            # Delete the backup file if it exists
            if backup.file_path and os.path.exists(backup.file_path):
                os.remove(backup.file_path)
            
            backup.delete()
            return Response({"message": "Backup deleted successfully"}, status=200)
        except Backup.DoesNotExist:
            return Response({"error": "Backup not found"}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_backup(request, pk):
    """Download a backup file"""
    if request.user.user_level != 'admin':
        return Response({"error": "Only administrators can download backups"}, status=403)
    
    try:
        backup = Backup.objects.get(pk=pk)
        
        if not backup.file_path or not os.path.exists(backup.file_path):
            return Response({"error": "Backup file not found"}, status=404)
        
        if backup.status != 'completed':
            return Response({"error": "Backup is not ready for download"}, status=400)
        
        # Log download
        log_audit_event(
            user=request.user,
            action='download',
            resource_type='system',
            resource_id=backup.id,
            resource_name=f"Backup: {backup.name}",
            description=f'Downloaded backup file: {backup.name}',
            request=request
        )
        
        # Return file for download
        with open(backup.file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/sql')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(backup.file_path)}"'
            return response
            
    except Backup.DoesNotExist:
        return Response({"error": "Backup not found"}, status=404)


# --- RESTORE API VIEWS ---
class RestoreListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List all restore operations"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can view restore operations"}, status=403)
        
        restores = Restore.objects.all()
        serializer = RestoreSerializer(restores, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new restore operation"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can restore backups"}, status=403)
        
        serializer = RestoreSerializer(data=request.data)
        if serializer.is_valid():
            restore = serializer.save(restored_by=request.user)
            
            # Start restore process in background thread
            thread = threading.Thread(target=restore_database, args=(restore,))
            thread.daemon = True
            thread.start()
            
            return Response(RestoreSerializer(restore).data, status=201)
        return Response(serializer.errors, status=400)


class RestoreDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        """Get restore details"""
        if request.user.user_level != 'admin':
            return Response({"error": "Only administrators can view restore details"}, status=403)
        
        try:
            restore = Restore.objects.get(pk=pk)
            serializer = RestoreSerializer(restore)
            return Response(serializer.data)
        except Restore.DoesNotExist:
            return Response({"error": "Restore not found"}, status=404)


# --- REPORTS API VIEWS ---
class ReportsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            # Only admins can access this endpoint
            if request.user.user_level != 'admin':
                return Response(
                    {"error": "You do not have permission to access this resource"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            report_type = request.query_params.get('type', 'all')
            print(f"ReportsAPIView: report_type = {report_type}")
            print(f"ReportsAPIView: query_params = {request.query_params}")
            
            if report_type == 'travels':
                return self.get_travels_report(request)
            elif report_type == 'liquidations':
                return self.get_liquidations_report(request)
            else:
                return self.get_all_reports(request)
        except Exception as e:
            print(f"ReportsAPIView error: {str(e)}")
            return Response(
                {"error": f"Internal server error: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_travels_report(self, request):
        """Get filtered travel orders report"""
        try:
            # Get filter parameters
            office = request.query_params.get('office', '')
            status_filter = request.query_params.get('status', '')
            date_from = request.query_params.get('date_from', '')
            date_to = request.query_params.get('date_to', '')
            search = request.query_params.get('search', '')
            
            # Start with all travel orders
            queryset = TravelOrder.objects.all()
            
            # Apply filters
            if office:
                queryset = queryset.filter(prepared_by__employee_type=office)
            
            if status_filter:
                if status_filter == 'approved':
                    queryset = queryset.filter(status__icontains='approved by the regional director')
                elif status_filter == 'pending':
                    queryset = queryset.exclude(status__icontains='approved by the regional director')
            
            if date_from:
                try:
                    date_from_obj = parse_date(date_from)
                    if date_from_obj:
                        queryset = queryset.filter(submitted_at__date__gte=date_from_obj)
                except ValueError:
                    pass
            
            if date_to:
                try:
                    date_to_obj = parse_date(date_to)
                    if date_to_obj:
                        queryset = queryset.filter(submitted_at__date__lte=date_to_obj)
                except ValueError:
                    pass
            
            if search:
                queryset = queryset.filter(
                    Q(destination__icontains=search) |
                    Q(travel_order_number__icontains=search) |
                    Q(prepared_by__first_name__icontains=search) |
                    Q(prepared_by__last_name__icontains=search)
                )
            
            # Order by submission date (newest first)
            queryset = queryset.order_by('-submitted_at')
            
            # Serialize the data
            serializer = TravelOrderReportSerializer(queryset, many=True, context={'request': request})
            
            # Debug: Print some sample data
            if queryset.exists():
                sample = queryset.first()
                print(f"Debug - Sample travel order: ID={sample.id}, prepared_by={sample.prepared_by}, employee_type={sample.prepared_by.employee_type if sample.prepared_by else 'None'}")
            
            return Response({
                'travels': serializer.data,
                'total_count': queryset.count(),
                'filters_applied': {
                    'office': office,
                    'status': status_filter,
                    'date_from': date_from,
                    'date_to': date_to,
                    'search': search
                }
            })
            
        except Exception as e:
            print(f"Error in get_travels_report: {str(e)}")
            return Response(
                {"error": f"Error fetching travels report: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_liquidations_report(self, request):
        """Get filtered liquidations report"""
        try:
            # Get filter parameters
            office = request.query_params.get('office', '')
            status_filter = request.query_params.get('status', '')
            date_from = request.query_params.get('date_from', '')
            date_to = request.query_params.get('date_to', '')
            search = request.query_params.get('search', '')
            
            # Start with all liquidations
            queryset = Liquidation.objects.all()
            
            # Apply filters
            if office:
                queryset = queryset.filter(travel_order__prepared_by__employee_type=office)
            
            if status_filter:
                if status_filter == 'completed':
                    # Check if all components are approved
                    queryset = queryset.filter(
                        after_travel_report_approved=True,
                        certificate_of_travel_approved=True,
                        certificate_of_appearance_approved=True
                    )
                elif status_filter == 'pending':
                    queryset = queryset.filter(
                        Q(after_travel_report_approved=False) |
                        Q(certificate_of_travel_approved=False) |
                        Q(certificate_of_appearance_approved=False)
                    )
            
            if date_from:
                try:
                    date_from_obj = parse_date(date_from)
                    if date_from_obj:
                        queryset = queryset.filter(submitted_at__date__gte=date_from_obj)
                except ValueError:
                    pass
            
            if date_to:
                try:
                    date_to_obj = parse_date(date_to)
                    if date_to_obj:
                        queryset = queryset.filter(submitted_at__date__lte=date_to_obj)
                except ValueError:
                    pass
            
            if search:
                queryset = queryset.filter(
                    Q(travel_order__destination__icontains=search) |
                    Q(travel_order__travel_order_number__icontains=search) |
                    Q(uploaded_by__first_name__icontains=search) |
                    Q(uploaded_by__last_name__icontains=search)
                )
            
            # Order by submission date (newest first)
            queryset = queryset.order_by('-submitted_at')
            
            # Serialize the data
            serializer = LiquidationSerializer(queryset, many=True, context={'request': request})
            
            return Response({
                'liquidations': serializer.data,
                'total_count': queryset.count(),
                'filters_applied': {
                    'office': office,
                    'status': status_filter,
                    'date_from': date_from,
                    'date_to': date_to,
                    'search': search
                }
            })
            
        except Exception as e:
            print(f"Error in get_liquidations_report: {str(e)}")
            return Response(
                {"error": f"Error fetching liquidations report: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_all_reports(self, request):
        """Get summary of all reports"""
        try:
            # Get basic counts
            total_travels = TravelOrder.objects.count()
            approved_travels = TravelOrder.objects.filter(
                status__icontains='approved by the regional director'
            ).count()
            
            total_liquidations = Liquidation.objects.count()
            completed_liquidations = Liquidation.objects.filter(
                after_travel_report_approved=True,
                certificate_of_travel_approved=True,
                certificate_of_appearance_approved=True
            ).count()
            
            return Response({
                'summary': {
                    'total_travels': total_travels,
                    'approved_travels': approved_travels,
                    'pending_travels': total_travels - approved_travels,
                    'total_liquidations': total_liquidations,
                    'completed_liquidations': completed_liquidations,
                    'pending_liquidations': total_liquidations - completed_liquidations                                                                         
                }
            })

        except Exception as e:
            print(f"Error in get_all_reports: {str(e)}")
            return Response(
                {"error": f"Error fetching reports summary: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Location API Views
class TravelOrderSignaturesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, travel_order_id):
        """Get all signatures for a travel order, ordered by most recent first"""
        try:
            travel_order = get_object_or_404(TravelOrder, id=travel_order_id)
            
            # Get all signatures for this travel order, ordered by most recent first
            signatures = Signature.objects.filter(order=travel_order).order_by('-signed_at')
            
            # Serialize the signatures
            signature_data = []
            for signature in signatures:
                signature_data.append({
                    'id': signature.id,
                    'signed_by': {
                        'id': signature.signed_by.id,
                        'full_name': signature.signed_by.get_full_name(),
                        'email': signature.signed_by.email,
                        'user_level': signature.signed_by.user_level
                    },
                    'signature_photo': signature.signature_photo.url if signature.signature_photo else None,
                    'signed_at': signature.signed_at,
                    'comment': signature.comment
                })
            
            return Response(signature_data)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class TravelOrderPDFDataView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, travel_order_id):
        """Get the appropriate data for PDF generation based on approval chain logic"""
        try:
            travel_order = get_object_or_404(TravelOrder.objects.select_related('purpose', 'specific_role'), id=travel_order_id)
            current_user = request.user
            
            # Determine what data to show based on the approval chain logic
            pdf_data = None
            pdf_itineraries = None
            previous_approver_signature = None
            
            # Debug: Check all signatures for this travel order
            all_employee_signatures = EmployeeSignature.objects.filter(order=travel_order)
            all_head_signatures = Signature.objects.filter(order=travel_order)
            print(f"DEBUG: Travel order status: {travel_order.status}")
            print(f"DEBUG: Travel order approval stage: {travel_order.approval_stage}")
            print(f"DEBUG: Travel order current approver: {travel_order.current_approver}")
            print(f"DEBUG: All employee signatures for order {travel_order.id}: {list(all_employee_signatures.values('signed_by__email', 'signature_photo'))}")
            print(f"DEBUG: All head signatures for order {travel_order.id}: {list(all_head_signatures.values('signed_by__email', 'signature_photo'))}")
            
            # Get all approval snapshots, ordered by approval stage
            snapshots = TravelOrderApprovalSnapshot.objects.filter(travel_order=travel_order).order_by('approval_stage')
            
            # Check if this is a resubmission (status contains "resubmitted" and approval stage is 0)
            is_resubmission = 'resubmitted' in travel_order.status.lower() and travel_order.approval_stage == 0
            print(f"DEBUG: Is resubmission: {is_resubmission} (status: {travel_order.status}, stage: {travel_order.approval_stage})")
            
            if snapshots.exists() and not is_resubmission:
                # If there are approvals and it's NOT a resubmission, show the data from the most recent approval
                latest_snapshot = snapshots.last()
                pdf_data = latest_snapshot.approved_data.copy()  # Create a copy to avoid modifying the original
                pdf_itineraries = latest_snapshot.approved_itineraries
                
                # Add additional fields that the PDF expects
                pdf_data['employee_names'] = pdf_data.get('employees', [])
                # Ensure purpose_name and specific_role_name are set (they should already be in approved_data as 'purpose' and 'specific_role')
                # The approved_data contains purpose and specific_role as names (strings), not IDs
                pdf_data['purpose_name'] = pdf_data.get('purpose', '')
                pdf_data['specific_role_name'] = pdf_data.get('specific_role', '')
                # Keep the old keys for backward compatibility (already set from approved_data)
                pdf_data['date_of_filing'] = travel_order.date_of_filing.strftime('%Y-%m-%d') if travel_order.date_of_filing else ''
                
                # Show the signature of the person who approved this snapshot (previous head)
                approver_signature = Signature.objects.filter(
                    order=travel_order,
                    signed_by=latest_snapshot.approved_by
                ).order_by('-signed_at').first()  # Get the most recent signature by this approver
                
                print(f"DEBUG: Looking for signature by {latest_snapshot.approved_by} for order {travel_order.id}")
                print(f"DEBUG: Found approver signature: {approver_signature}")
                
                if approver_signature:
                    print(f"DEBUG: Approver signature file: {approver_signature.signature_photo}")
                    previous_approver_signature = {
                        'signed_by': {
                            'full_name': approver_signature.signed_by.get_full_name(),
                            'user_level': approver_signature.signed_by.user_level
                        },
                        'signature_photo': approver_signature.signature_photo.url if approver_signature.signature_photo else None
                    }
                    print(f"DEBUG: Previous approver signature set: {previous_approver_signature}")
                else:
                    print("DEBUG: No approver signature found")
            else:
                # No approvals yet, show the original employee data
                pdf_data = {
                    'destination': travel_order.destination,
                    'date_travel_from': travel_order.date_travel_from.isoformat() if travel_order.date_travel_from else None,
                    'date_travel_to': travel_order.date_travel_to.isoformat() if travel_order.date_travel_to else None,
                    'purpose_name': travel_order.purpose.purpose_name if travel_order.purpose else None,
                    'specific_role_name': travel_order.specific_role.role_name if travel_order.specific_role else None,
                    # Keep the old keys for backward compatibility
                    'purpose': travel_order.purpose.purpose_name if travel_order.purpose else None,
                    'specific_role': travel_order.specific_role.role_name if travel_order.specific_role else None,
                    'fund_cluster': travel_order.fund_cluster,
                    'mode_of_filing': travel_order.mode_of_filing,
                    'distance': int(travel_order.distance) if travel_order.distance else 0,
                    'official_station': travel_order.official_station,
                    'prepared_by_name': travel_order.prepared_by.get_full_name() if travel_order.prepared_by else None,
                    'prepared_by_position': travel_order.prepared_by_position_name,
                    'employees': [emp.get_full_name() for emp in travel_order.employees.all()],
                    'employee_names': [emp.get_full_name() for emp in travel_order.employees.all()],
                    'date_of_filing': travel_order.date_of_filing.strftime('%Y-%m-%d') if travel_order.date_of_filing else ''
                }
                
                # Get employee's signature - get the most recent one (for resubmissions)
                employee_signature = EmployeeSignature.objects.filter(order=travel_order).order_by('-signed_at').first()
                print(f"DEBUG: Employee signature found (most recent): {employee_signature}")
                if employee_signature:
                    print(f"DEBUG: Employee signature file: {employee_signature.signature_photo}")
                    print(f"DEBUG: Employee signature date: {employee_signature.signed_at}")
                    previous_approver_signature = {
                        'signed_by': {
                            'full_name': employee_signature.signed_by.get_full_name(),
                            'user_level': employee_signature.signed_by.user_level
                        },
                        'signature_photo': employee_signature.signature_photo.url if employee_signature.signature_photo else None
                    }
                
                # Get current itineraries
                current_itineraries = Itinerary.objects.filter(travel_order=travel_order)
                pdf_itineraries = []
                for itinerary in current_itineraries:
                    pdf_itineraries.append({
                        'id': itinerary.id,
                        'destination': itinerary.destination,
                        'itinerary_date': itinerary.itinerary_date.isoformat() if itinerary.itinerary_date else None,
                        'departure_time': itinerary.departure_time.isoformat() if itinerary.departure_time else None,
                        'arrival_time': itinerary.arrival_time.isoformat() if itinerary.arrival_time else None,
                        'transportation': itinerary.transportation.id if itinerary.transportation else None,
                        'transportation_allowance': float(itinerary.transportation_allowance) if itinerary.transportation_allowance else 0,
                        'per_diem': float(itinerary.per_diem) if itinerary.per_diem else 0,
                        'others': float(itinerary.other_expense) if itinerary.other_expense else 0,
                        'total': float(itinerary.total_amount) if itinerary.total_amount else 0
                    })
            
            return Response({
                'travel_order_data': pdf_data,
                'itineraries': pdf_itineraries,
                'previous_approver_signature': previous_approver_signature
            })
            
        except Exception as e:
            return Response({'error': str(e)}, status=500)

