from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import mark_safe
from .models import CustomUser, TravelOrder, Signature, Fund, Transportation, EmployeePosition, Purpose, SpecificRole

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'prefix', 'first_name', 'last_name', 'user_level', 'employee_type', 'employee_position', 'is_staff', 'is_active']
    ordering = ['email']
    search_fields = ['email', 'first_name', 'last_name', 'employee_type']
    
    # Override fieldsets to remove username field and customize for email-based auth
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('prefix', 'first_name', 'last_name')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('User Info', {'fields': ('user_level', 'employee_type', 'employee_position', 'must_change_password')}),
    )
    
    # Override add_fieldsets for creating new users
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        ('Personal info', {'fields': ('prefix', 'first_name', 'last_name')}),
        ('User Info', {'fields': ('user_level', 'employee_type', 'employee_position')}),
    )
    
    def save_model(self, request, obj, form, change):
        """Override save_model to automatically set superuser status for admin users"""
        # Track if user level is being changed to admin
        user_level_changed_to_admin = False
        if change:
            # Get the original instance from database
            try:
                original = CustomUser.objects.get(pk=obj.pk)
                if obj.user_level == 'admin' and original.user_level != 'admin':
                    user_level_changed_to_admin = True
            except CustomUser.DoesNotExist:
                pass
        
        # If user_level is 'admin', automatically set is_superuser and is_staff
        if obj.user_level == 'admin':
            obj.is_superuser = True
            obj.is_staff = True
            # Deactivate all other admin users if creating new admin or changing to admin
            if not change or user_level_changed_to_admin:
                # Creating new admin or changing user level to admin
                if obj.is_active:
                    CustomUser.objects.filter(user_level='admin', is_active=True).exclude(pk=obj.pk if obj.pk else None).update(is_active=False)
        
        super().save_model(request, obj, form, change)

class TravelOrderAdmin(admin.ModelAdmin):
    list_display = ['destination', 'mode_of_filing', 'status', 'submitted_at', 'evidence_preview']
    readonly_fields = ['evidence_preview']

    def evidence_preview(self, obj):
        if obj.evidence:
            return mark_safe(f'<img src="{obj.evidence.url}" width="200" />')
        return "No evidence uploaded"

@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ['source_of_fund', 'is_archived']
    list_filter = ['is_archived']
    search_fields = ['source_of_fund']

@admin.register(Transportation)
class TransportationAdmin(admin.ModelAdmin):
    list_display = ['means_of_transportation', 'is_archived']
    list_filter = ['is_archived']
    search_fields = ['means_of_transportation']

@admin.register(EmployeePosition)
class EmployeePositionAdmin(admin.ModelAdmin):
    list_display = ['position_name', 'is_archived']
    list_filter = ['is_archived']
    search_fields = ['position_name']

@admin.register(Purpose)
class PurposeAdmin(admin.ModelAdmin):
    list_display = ['purpose_name', 'is_archived']
    list_filter = ['is_archived']
    search_fields = ['purpose_name']

@admin.register(SpecificRole)
class SpecificRoleAdmin(admin.ModelAdmin):
    list_display = ['role_name', 'is_archived']
    list_filter = ['is_archived']
    search_fields = ['role_name']

admin.site.register(CustomUser, CustomUserAdmin)


admin.site.register(TravelOrder, TravelOrderAdmin)
admin.site.register(Signature)