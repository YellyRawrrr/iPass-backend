# serializers.py
# Django REST Framework serializers for API data transformation
from rest_framework import serializers
from .models import TravelOrder, Signature, CustomUser, Itinerary, Fund, Transportation, EmployeePosition, Liquidation, EmployeeSignature, Notification, AfterTravelReport, CertificateOfTravel, CertificateOfAppearance, AuditLog, Backup, Restore, Purpose, SpecificRole
from django.contrib.auth.hashers import make_password

# --- LOCATION SERIALIZERS ---
class TransportationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transportation
        fields = ['id', 'means_of_transportation', 'is_archived']

class ItinerarySerializer(serializers.ModelSerializer):
    transportation = serializers.PrimaryKeyRelatedField(queryset=Transportation.objects.all(), allow_null=True, required=False)
    transportation_allowance = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    per_diem = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    other_expense = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    departure_time = serializers.TimeField(required=False, allow_null=True)
    arrival_time = serializers.TimeField(required=False, allow_null=True)
    
    def validate_transportation_allowance(self, value):
        if value == '' or value is None:
            return None
        return value
    
    def validate_per_diem(self, value):
        if value == '' or value is None:
            return None
        return value
    
    def validate_other_expense(self, value):
        if value == '' or value is None:
            return None
        return value
    
    def validate_total_amount(self, value):
        if value == '' or value is None:
            return None
        return value
    
    def validate_departure_time(self, value):
        if value == '' or value is None:
            return None
        return value
    
    def validate_arrival_time(self, value):
        if value == '' or value is None:
            return None
        return value
    
    class Meta:
        model = Itinerary
        fields = '__all__'
        extra_kwargs = {
            'travel_order': {'required': False},
            'itinerary_date': {'required': False, 'allow_null': True},
            'departure_time': {'required': False, 'allow_null': True},
            'arrival_time': {'required': False, 'allow_null': True},
        }

class FundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fund
        fields = ['id', 'source_of_fund', 'is_archived']

class TravelOrderReportSerializer(serializers.ModelSerializer):
    employees = serializers.SerializerMethodField()
    prepared_by_name = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()

    class Meta:
        model = TravelOrder
        fields = [
            'id',
            'travel_order_number',
            'destination',
            'distance',
            'purpose',
            'date_travel_from',
            'date_travel_to',
            'official_station',
            'fund_cluster',
            'status',
            'submitted_at',
            'employees',
            'prepared_by_name',
            'office'
        ]

    def get_employees(self, obj):
        return [{'id': u.id, 'full_name': u.full_name} for u in obj.employees.all()]

    def get_prepared_by_name(self, obj):
        if obj.prepared_by:
            prefix_str = f"{obj.prepared_by.prefix} " if obj.prepared_by.prefix else ""
            return f"{prefix_str}{obj.prepared_by.first_name} {obj.prepared_by.last_name}"
        return "—"
    
    def get_office(self, obj):
        if obj.prepared_by and obj.prepared_by.employee_type:
            return obj.prepared_by.employee_type
        return None

class SignatureSerializer(serializers.ModelSerializer):
    signed_by_name = serializers.CharField(source="signed_by.full_name", read_only=True)
    position = serializers.CharField(source="signed_by.employee_position.position_name", read_only=True)
    signature_photo = serializers.SerializerMethodField()

    class Meta:
        model = Signature
        fields = ["id", "signed_by_name", "position", "signature_photo", "signed_at", "comment"]
    
    def get_signature_photo(self, obj):
        if obj.signature_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.signature_photo.url)
            return obj.signature_photo.url
        return None


class EmployeeSignatureSerializer(serializers.ModelSerializer):
    signed_by_name = serializers.CharField(source="signed_by.full_name", read_only=True)
    position = serializers.CharField(source="signed_by.employee_position.position_name", read_only=True)
    signature_photo = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeSignature
        fields = ["id", "signed_by_name", "position", "signature_photo", "signed_at"]
    
    def get_signature_photo(self, obj):
        if obj.signature_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.signature_photo.url)
            return obj.signature_photo.url
        return None



class TravelOrderSerializer(serializers.ModelSerializer):
    """Main serializer for travel orders with nested relationships"""
    employees = serializers.PrimaryKeyRelatedField(many=True, queryset=CustomUser.objects.all())
    employee_names = serializers.SerializerMethodField()
    prepared_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    itinerary = ItinerarySerializer(many=True)
    employee_position = serializers.PrimaryKeyRelatedField(queryset=EmployeePosition.objects.all(), allow_null=True, required=False)
    purpose = serializers.PrimaryKeyRelatedField(queryset=Purpose.objects.all(), allow_null=True, required=False)
    specific_role = serializers.PrimaryKeyRelatedField(queryset=SpecificRole.objects.all(), allow_null=True, required=False)
    purpose_name = serializers.SerializerMethodField()
    specific_role_name = serializers.SerializerMethodField()
    
    def get_purpose_name(self, obj):
        """Get purpose name from the related Purpose object"""
        try:
            if obj.purpose:
                # Access the purpose_name directly from the related object
                return obj.purpose.purpose_name
        except Exception as e:
            # If there's an error accessing the related object, log it
            print(f"Error getting purpose_name for travel order {obj.id}: {e}")
        return None
    
    def get_specific_role_name(self, obj):
        """Get specific role name from the related SpecificRole object"""
        try:
            if obj.specific_role:
                # Access the role_name directly from the related object
                return obj.specific_role.role_name
        except Exception as e:
            # If there's an error accessing the related object, log it
            print(f"Error getting specific_role_name for travel order {obj.id}: {e}")
        return None
    prepared_by_name = serializers.SerializerMethodField()
    prepared_by_position = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()
    approver_selection = serializers.JSONField(required=False, allow_null=True)
    approver_position = serializers.JSONField(required=False, allow_null=True)
    official_station = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    grand_total = serializers.SerializerMethodField()
    
    # Approval and signature data
    approvals = SignatureSerializer(source="signature_set", many=True, read_only=True)  
    employee_signature = EmployeeSignatureSerializer(read_only=True)
    travel_monitoring = serializers.SerializerMethodField()

    class Meta:
        model = TravelOrder
        fields = '__all__'
        extra_kwargs = {
            'date_travel_from': {'required': False, 'allow_null': True},
            'date_travel_to': {'required': False, 'allow_null': True},
        }
    
    def get_travel_monitoring(self, obj):
        """Compile all travel order movements into a timeline"""
        from django.utils import timezone
        from datetime import datetime
        
        timeline = []
        
        # Helper function to format datetime
        def format_datetime(dt):
            if dt is None:
                return None
            if isinstance(dt, datetime):
                return dt.isoformat()
            if hasattr(dt, 'isoformat'):
                return dt.isoformat()
            return str(dt)
        
        # Helper to get prepared_by info
        prepared_by_name = self.get_prepared_by_name(obj) if hasattr(self, 'get_prepared_by_name') else None
        prepared_by_position = self.get_prepared_by_position(obj) if hasattr(self, 'get_prepared_by_position') else None
        
        # 1. Created/Submitted
        if obj.submitted_at:
            timeline.append({
                'action': 'Created',
                'description': f'Travel order created by {prepared_by_name if prepared_by_name else "employee"}',
                'by': prepared_by_name,
                'position': prepared_by_position,
                'date_time': format_datetime(obj.submitted_at),
                'type': 'created'
            })
        
        # 2. Employee Signature
        try:
            if hasattr(obj, 'employee_signature') and obj.employee_signature:
                emp_sig = obj.employee_signature
                signed_by_name = None
                position = None
                
                if emp_sig.signed_by:
                    signed_by_name = emp_sig.signed_by.full_name
                    if emp_sig.signed_by.employee_position:
                        position = emp_sig.signed_by.employee_position.position_name
                
                timeline.append({
                    'action': 'Signed by Employee',
                    'description': f'Travel order signed by employee',
                    'by': signed_by_name,
                    'position': position,
                    'date_time': format_datetime(emp_sig.signed_at),
                    'type': 'employee_signed'
                })
        except Exception as e:
            pass  # No employee signature
        
        # 3. Approvals (sorted by signed_at)
        try:
            approvals_list = list(obj.signature_set.all().order_by('signed_at'))
            for approval in approvals_list:
                timeline.append({
                    'action': 'Approved',
                    'description': f'Travel order approved',
                    'by': approval.signed_by.full_name if approval.signed_by else None,
                    'position': approval.signed_by.employee_position.position_name if approval.signed_by and approval.signed_by.employee_position else None,
                    'date_time': format_datetime(approval.signed_at),
                    'type': 'approved',
                    'comment': approval.comment if approval.comment else None
                })
        except:
            pass  # No approvals
        
        # 4. Rejection
        if obj.rejected_at and obj.rejected_by:
            timeline.append({
                'action': 'Rejected',
                'description': f'Travel order rejected',
                'by': obj.rejected_by.full_name if obj.rejected_by else None,
                'position': obj.rejected_by.employee_position.position_name if obj.rejected_by and obj.rejected_by.employee_position else None,
                'date_time': format_datetime(obj.rejected_at),
                'type': 'rejected',
                'comment': obj.rejection_comment if obj.rejection_comment else None
            })
        
        # Sort by date_time (most recent last)
        timeline.sort(key=lambda x: x['date_time'] if x['date_time'] else '')
        
        return timeline

    def get_prepared_by_name(self, obj):
        if obj.prepared_by:
            prefix_str = f"{obj.prepared_by.prefix} " if obj.prepared_by.prefix else ""
            return f"{prefix_str}{obj.prepared_by.first_name} {obj.prepared_by.last_name}"
        return None
    
    def get_prepared_by_position(self, obj):
        if obj.prepared_by and obj.prepared_by.employee_position:
            return obj.prepared_by.employee_position.position_name
        return None

    def get_employee_names(self, obj):
        return [u.full_name for u in obj.employees.all()]

    def get_grand_total(self, obj):
        """Calculate grand total from all itinerary entries"""
        total = 0
        itineraries = obj.itinerary.all()
        for itinerary in itineraries:
            if itinerary.total_amount:
                total += float(itinerary.total_amount)
        return round(total, 2)

    def get_evidence(self, obj):
        if obj.evidence:
            from django.conf import settings
            # Get the request from context to build proper URL
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(f"{settings.MEDIA_URL}{obj.evidence.name}")
            else:
                # Fallback to localhost if no request context
                return f"http://localhost:8000{settings.MEDIA_URL}{obj.evidence.name}"
        return None

    def create(self, validated_data):
        itinerary_data = validated_data.pop('itinerary')
        employees_data = validated_data.pop('employees')

        travel_order = TravelOrder.objects.create(**validated_data)
        travel_order.employees.set(employees_data)

        # Use ItinerarySerializer to create itinerary entries
        itinerary_serializer = ItinerarySerializer()
        for item in itinerary_data:
            # Remove fields that shouldn't be passed to create (for amend mode)
            item.pop('travel_order', None)
            item.pop('id', None)
            # Add travel_order instance to the item data
            item['travel_order'] = travel_order
            # Use the serializer's create method
            itinerary_serializer.create(item)

        return travel_order

    def update(self, instance, validated_data, **kwargs):
        itinerary_data = validated_data.pop('itinerary', [])
        employees_data = validated_data.pop('employees', [])

        # Apply any additional kwargs (like travel_order_number from save_kwargs)
        for key, value in kwargs.items():
            setattr(instance, key, value)

        # Update TravelOrder fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update ManyToMany employees
        instance.employees.set(employees_data)

        # Refresh itineraries
        instance.itinerary.all().delete()
        # Use ItinerarySerializer to create itinerary entries
        itinerary_serializer = ItinerarySerializer()
        for item in itinerary_data:
            # Remove fields that shouldn't be passed to create (for amend mode)
            item.pop('travel_order', None)
            item.pop('id', None)
            # Add travel_order instance to the item data
            item['travel_order'] = instance
            # Use the serializer's create method
            itinerary_serializer.create(item)

        return instance



class EmployeePositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeePosition
        fields = ['id', 'position_name', 'is_archived']

class PurposeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purpose
        fields = ['id', 'purpose_name', 'is_archived']

class SpecificRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecificRole
        fields = ['id', 'role_name', 'is_archived']



class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    # Computed fields
    full_name = serializers.SerializerMethodField()
    employee_position = serializers.PrimaryKeyRelatedField(queryset=EmployeePosition.objects.all(), allow_null=True, required=False)
    employee_position_name = serializers.SerializerMethodField()

    # Enum display fields
    user_level_display = serializers.SerializerMethodField()
    employee_type_display = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'password',
            'prefix',
            'user_level', 'user_level_display',
            'employee_type', 'employee_type_display',
            'first_name', 'last_name',
            'full_name', 'employee_position', 'employee_position_name',
            'must_change_password'
        ]

    def get_full_name(self, obj):
        prefix_str = f"{obj.prefix} " if obj.prefix else ""
        return f"{prefix_str}{obj.first_name} {obj.last_name}"

    def get_user_level_display(self, obj):
        return obj.get_user_level_display()

    def get_employee_type_display(self, obj):
        return obj.get_employee_type_display()


    def get_employee_position_name(self, obj):
        return obj.employee_position.position_name if obj.employee_position else None

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'Password is required for new users.'})
        
        user = CustomUser(**validated_data)
        user.set_password(password)
        
        # Automatically set superuser and staff status for admin users
        if user.user_level == 'admin':
            user.is_superuser = True
            user.is_staff = True
        
        # Save user first to get an ID
        user.save()
        
        # Deactivate all other admin users if this is a new admin
        if user.user_level == 'admin' and user.is_active:
            CustomUser.objects.filter(user_level='admin', is_active=True).exclude(id=user.id).update(is_active=False)
        
        return user
    
    def update(self, instance, validated_data):
        # Handle password update if provided
        password = validated_data.pop('password', None)
        if password:
            # Check if password is already hashed (from make_password in views)
            # Django password hashes typically start with algorithm identifiers like pbkdf2_, argon2$, etc.
            if not password.startswith(('pbkdf2_', 'argon2$', 'bcrypt$', 'scrypt_')):
                # Password is plain text, hash it
                instance.set_password(password)
            else:
                # Password is already hashed, set it directly
                instance.password = password
        
        # Track if user level is being changed to admin
        old_user_level = instance.user_level
        user_level_changed_to_admin = False
        if 'user_level' in validated_data:
            new_user_level = validated_data['user_level']
            if new_user_level == 'admin' and old_user_level != 'admin':
                user_level_changed_to_admin = True
        
        # Update all other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Automatically set superuser and staff status for admin users
        if instance.user_level == 'admin':
            instance.is_superuser = True
            instance.is_staff = True
            # Deactivate all other admin users when user level is changed to admin
            if user_level_changed_to_admin and instance.is_active:
                CustomUser.objects.filter(user_level='admin', is_active=True).exclude(id=instance.id).update(is_active=False)
        
        instance.save()
        return instance



    
class TravelOrderSimpleSerializer(serializers.ModelSerializer):
    employee_names = serializers.SerializerMethodField()
    employees = serializers.SerializerMethodField()
    prepared_by_name = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()
    itinerary = ItinerarySerializer(many=True, read_only=True)
    approvals = SignatureSerializer(source="signature_set", many=True, read_only=True)
    employee_signature = EmployeeSignatureSerializer(read_only=True)
    
    purpose_name = serializers.SerializerMethodField()
    specific_role_name = serializers.SerializerMethodField()
    
    def get_purpose_name(self, obj):
        """Get purpose name from the related Purpose object"""
        try:
            if obj.purpose:
                # Access the purpose_name directly from the related object
                return obj.purpose.purpose_name
        except Exception as e:
            # If there's an error accessing the related object, log it
            print(f"Error getting purpose_name for travel order {obj.id}: {e}")
        return None
    
    def get_specific_role_name(self, obj):
        """Get specific role name from the related SpecificRole object"""
        try:
            if obj.specific_role:
                # Access the role_name directly from the related object
                return obj.specific_role.role_name
        except Exception as e:
            # If there's an error accessing the related object, log it
            print(f"Error getting specific_role_name for travel order {obj.id}: {e}")
        return None
    
    class Meta:
        model = TravelOrder
        fields = ['id', 'travel_order_number', 'destination', 'distance', 'date_travel_from', 'date_travel_to', 'date_of_filing', 'fund_cluster', 'purpose', 'purpose_name', 'specific_role', 'specific_role_name', 'official_station', 'employee_names', 'employees', 'prepared_by_name', 'office', 'itinerary', 'approvals', 'employee_signature']
    
    def get_prepared_by_name(self, obj):
        if obj.prepared_by:
            return obj.prepared_by.full_name
        return None
    
    def get_office(self, obj):
        if obj.prepared_by and obj.prepared_by.employee_type:
            return obj.prepared_by.employee_type
        return None
    
    def get_employee_names(self, obj):
        return [u.full_name for u in obj.employees.all()]
    
    def get_employees(self, obj):
        return [{'id': u.id, 'full_name': u.full_name} for u in obj.employees.all()]




class AfterTravelReportSerializer(serializers.ModelSerializer):
    prepared_by = serializers.PrimaryKeyRelatedField(many=True, queryset=CustomUser.objects.all(), required=False)
    prepared_by_names = serializers.SerializerMethodField()
    prepared_by_positions = serializers.SerializerMethodField()
    office_head_name = serializers.CharField(source='office_head.full_name', read_only=True)
    office_head_position = serializers.SerializerMethodField()
    regional_director_name = serializers.CharField(source='regional_director.full_name', read_only=True)
    regional_director_position = serializers.SerializerMethodField()
    photo_documentation_urls = serializers.SerializerMethodField()
    
    class Meta:
        model = AfterTravelReport
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
        extra_kwargs = {
            'pap': {'required': False, 'allow_blank': True, 'allow_null': True},
            'actual_output': {'required': False, 'allow_blank': True, 'allow_null': True},
            'cash_advance': {'required': False, 'allow_null': True},
            'period_of_implementation': {'required': False, 'allow_null': True},
            'date_of_submission': {'required': False, 'allow_null': True},
            'background': {'required': False, 'allow_blank': True, 'allow_null': True},
            'highlights_of_activity': {'required': False, 'allow_blank': True, 'allow_null': True},
            'ways_forward': {'required': False, 'allow_blank': True, 'allow_null': True},
            'travel_order': {'required': False, 'allow_null': True},
        }
    
    def get_prepared_by_names(self, obj):
        return [f"{user.full_name}" for user in obj.prepared_by.all()]
    
    def get_prepared_by_positions(self, obj):
        return [user.employee_position.position_name if user.employee_position else 'No Position' for user in obj.prepared_by.all()]
    
    def get_office_head_position(self, obj):
        if obj.office_head and obj.office_head.employee_position:
            return obj.office_head.employee_position.position_name
        return 'No Position'
    
    def get_regional_director_position(self, obj):
        if obj.regional_director and obj.regional_director.employee_position:
            return obj.regional_director.employee_position.position_name
        return 'No Position'
    
    def get_photo_documentation_urls(self, obj):
        if obj.photo_documentation:
            from django.conf import settings
            request = self.context.get('request')
            base_url = request.build_absolute_uri(settings.MEDIA_URL) if request else f"http://localhost:8000{settings.MEDIA_URL}"
            return [f"{base_url}{photo_path}" for photo_path in obj.photo_documentation]
        return []

class CertificateOfTravelSerializer(serializers.ModelSerializer):
    agency_head = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.filter(user_level='director'), allow_null=True, required=False)
    agency_head_name = serializers.CharField(source='agency_head.full_name', read_only=True)
    respectfully_submitted = serializers.PrimaryKeyRelatedField(many=True, queryset=CustomUser.objects.all(), required=False)
    respectfully_submitted_names = serializers.SerializerMethodField()
    respectfully_submitted_positions = serializers.SerializerMethodField()
    approved = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), allow_null=True, required=False)
    approved_name = serializers.CharField(source='approved.full_name', read_only=True)
    approved_position = serializers.SerializerMethodField()
    fund_cluster_display = serializers.CharField(source='get_fund_cluster_display', read_only=True)
    station_display = serializers.CharField(source='get_station_display', read_only=True)
    deviation_type_display = serializers.CharField(source='get_deviation_type_display', read_only=True)
    evidence_type_display = serializers.CharField(source='get_evidence_type_display', read_only=True)
    
    class Meta:
        model = CertificateOfTravel
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
        extra_kwargs = {
            'fund_cluster': {'required': False, 'allow_blank': True, 'allow_null': True},
            'station': {'required': False, 'allow_blank': True, 'allow_null': True},
            'travel_order_number': {'required': False, 'allow_blank': True, 'allow_null': True},
            'date_travel_from': {'required': False, 'allow_null': True},
            'date_travel_to': {'required': False, 'allow_null': True},
            'explanations_justifications': {'required': False, 'allow_blank': True, 'allow_null': True},
            'evidence_type': {'required': False, 'allow_blank': True, 'allow_null': True},
            'deviation_types': {'required': False, 'allow_null': True},
            'travel_order': {'required': False, 'allow_null': True},
        }
    
    def get_respectfully_submitted_names(self, obj):
        return [f"{user.full_name}" for user in obj.respectfully_submitted.all()]
    
    def get_respectfully_submitted_positions(self, obj):
        return [user.employee_position.position_name if user.employee_position else 'No position' for user in obj.respectfully_submitted.all()]
    
    def get_approved_position(self, obj):
        if obj.approved and obj.approved.employee_position:
            return obj.approved.employee_position.position_name
        return 'No position'


class CertificateOfAppearanceSerializer(serializers.ModelSerializer):
    certificate_of_appearance_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CertificateOfAppearance
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def get_certificate_of_appearance_url(self, obj):
        if obj.certificate_of_appearance:
            from django.conf import settings
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.certificate_of_appearance.url)
            # Fallback to constructing URL manually if no request context
            base_url = getattr(settings, 'MEDIA_URL', '/media/')
            if not base_url.startswith('http'):
                # If frontend expects full URL, construct it
                return f"http://localhost:8000{base_url}{obj.certificate_of_appearance.name}"
            return f"{base_url}{obj.certificate_of_appearance.name}"
        return None

class LiquidationSerializer(serializers.ModelSerializer):
    travel_order = serializers.SerializerMethodField()
    travel_order_id = serializers.PrimaryKeyRelatedField(
        queryset=TravelOrder.objects.all(), source='travel_order', write_only=True
    )
    after_travel_report = AfterTravelReportSerializer(read_only=True)
    certificate_of_travel = CertificateOfTravelSerializer(read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)
    uploaded_by_email = serializers.CharField(source='uploaded_by.email', read_only=True)
    
    # Reviewer information
    after_travel_report_reviewer_name = serializers.SerializerMethodField()
    certificate_of_travel_reviewer_name = serializers.SerializerMethodField()
    after_travel_report_reviewed_by_name = serializers.SerializerMethodField()
    certificate_of_travel_reviewed_by_name = serializers.SerializerMethodField()
    reviewed_by_bookkeeper_name = serializers.SerializerMethodField()
    reviewed_by_accountant_name = serializers.SerializerMethodField()
    
    # Component status summary
    component_status_summary = serializers.SerializerMethodField()

    # Explicit file fields for better control and frontend usability
    certificate_of_appearance = serializers.SerializerMethodField()
    
    # Signature photo fields
    after_travel_report_reviewer_signature = serializers.SerializerMethodField()
    certificate_of_travel_reviewer_signature = serializers.SerializerMethodField()

    class Meta:
        model = Liquidation
        fields = '__all__'
        read_only_fields = (
            'uploaded_by', 'submitted_at',
            'reviewed_by_bookkeeper', 'reviewed_at_bookkeeper',
            'reviewed_by_accountant', 'reviewed_at_accountant'
        )
    
    def get_travel_order(self, obj):
        """Get travel order data, handling broken relationships gracefully"""
        try:
            if obj.travel_order:
                return TravelOrderSimpleSerializer(obj.travel_order, context=self.context).data
            else:
                return None
        except:
            # Handle broken relationships
            return {
                'id': None,
                'travel_order_number': 'Travel Order Deleted',
                'destination': 'N/A',
                'date_travel_from': None,
                'date_travel_to': None,
                'status': 'Deleted'
            }
    
    def get_component_status_summary(self, obj):
        """Get a summary of all component statuses"""
        return obj.get_component_status_summary()
    
    def get_after_travel_report_reviewer_name(self, obj):
        """Get the full name of the after travel report reviewer"""
        if obj.after_travel_report_reviewer:
            return f"{obj.after_travel_report_reviewer.first_name} {obj.after_travel_report_reviewer.last_name}"
        return None
    
    def get_certificate_of_travel_reviewer_name(self, obj):
        """Get the full name of the certificate of travel reviewer"""
        if obj.certificate_of_travel_reviewer:
            return f"{obj.certificate_of_travel_reviewer.first_name} {obj.certificate_of_travel_reviewer.last_name}"
        return None
    
    def get_after_travel_report_reviewed_by_name(self, obj):
        """Get the full name of the after travel report reviewer who approved/rejected"""
        if obj.after_travel_report_reviewed_by:
            return f"{obj.after_travel_report_reviewed_by.first_name} {obj.after_travel_report_reviewed_by.last_name}"
        return None
    
    def get_certificate_of_travel_reviewed_by_name(self, obj):
        """Get the full name of the certificate of travel reviewer who approved/rejected"""
        if obj.certificate_of_travel_reviewed_by:
            return f"{obj.certificate_of_travel_reviewed_by.first_name} {obj.certificate_of_travel_reviewed_by.last_name}"
        return None
    
    def get_reviewed_by_bookkeeper_name(self, obj):
        """Get the full name of the bookkeeper who reviewed"""
        if obj.reviewed_by_bookkeeper:
            return f"{obj.reviewed_by_bookkeeper.first_name} {obj.reviewed_by_bookkeeper.last_name}"
        return None
    
    def get_reviewed_by_accountant_name(self, obj):
        """Get the full name of the accountant who reviewed"""
        if obj.reviewed_by_accountant:
            return f"{obj.reviewed_by_accountant.first_name} {obj.reviewed_by_accountant.last_name}"
        return None
    
    def get_certificate_of_appearance(self, obj):
        """Get the full URL for the certificate of appearance file"""
        if obj.certificate_of_appearance:
            from django.conf import settings
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.certificate_of_appearance.url)
            else:
                # Fallback to localhost if no request context
                return f"http://localhost:8000{obj.certificate_of_appearance.url}"
        return None
    
    def get_after_travel_report_reviewer_signature(self, obj):
        """Get the full URL for the after travel report reviewer signature photo"""
        if obj.after_travel_report_reviewer_signature:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.after_travel_report_reviewer_signature.url)
            return obj.after_travel_report_reviewer_signature.url
        return None
    
    def get_certificate_of_travel_reviewer_signature(self, obj):
        """Get the full URL for the certificate of travel reviewer signature photo"""
        if obj.certificate_of_travel_reviewer_signature:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.certificate_of_travel_reviewer_signature.url)
            return obj.certificate_of_travel_reviewer_signature.url
        return None
    
    def to_representation(self, instance):
        """Override to pass request context to nested serializers"""
        data = super().to_representation(instance)
        
        # Pass request context to nested serializers
        if instance.after_travel_report:
            after_travel_serializer = AfterTravelReportSerializer(
                instance.after_travel_report, 
                context=self.context
            )
            data['after_travel_report'] = after_travel_serializer.data
        
        if instance.certificate_of_travel:
            certificate_serializer = CertificateOfTravelSerializer(
                instance.certificate_of_travel, 
                context=self.context
            )
            data['certificate_of_travel'] = certificate_serializer.data
            
        return data

class NotificationSerializer(serializers.ModelSerializer):
    travel_order_destination = serializers.CharField(source='travel_order.destination', read_only=True)
    travel_order_id = serializers.IntegerField(source='travel_order.id', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message', 
            'is_read', 'email_sent', 'email_sent_at', 'created_at', 
            'travel_order_destination', 'travel_order_id'
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_level = serializers.CharField(source='user.user_level', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    resource_type_display = serializers.CharField(source='get_resource_type_display', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_name', 'user_level', 'action', 'action_display',
            'resource_type', 'resource_type_display', 'resource_id', 'resource_name',
            'description', 'user_agent', 'timestamp', 'metadata'
        ]
        read_only_fields = ['timestamp']


class BackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    backup_type_display = serializers.CharField(source='get_backup_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_size_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Backup
        fields = [
            'id', 'name', 'backup_type', 'backup_type_display', 'file_path', 
            'file_size', 'file_size_display', 'status', 'status_display',
            'created_by', 'created_by_name', 'created_at', 'completed_at',
            'description', 'metadata'
        ]
        read_only_fields = ['created_at', 'completed_at']
    
    def get_file_size_display(self, obj):
        if obj.file_size:
            size = obj.file_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        return None


class RestoreSerializer(serializers.ModelSerializer):
    restored_by_name = serializers.CharField(source='restored_by.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    original_backup_name = serializers.CharField(source='original_backup.name', read_only=True)
    
    class Meta:
        model = Restore
        fields = [
            'id', 'backup_file', 'original_backup', 'original_backup_name',
            'status', 'status_display', 'restored_by', 'restored_by_name',
            'created_at', 'completed_at', 'description', 'error_message', 'metadata'
        ]
        read_only_fields = ['created_at', 'completed_at']