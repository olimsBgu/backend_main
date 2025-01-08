from django import forms
from django.contrib import admin
from .models import User

class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional except for the email field
        for field_name, field in self.fields.items():
            if field_name not in set('email'):  # Keep 'email' as required
                field.required = False

    def clean_partner(self):
        partner = self.cleaned_data.get("partner")
        if partner and partner == self.instance:
            raise forms.ValidationError("A user cannot be their own partner.")
        return partner

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm  # Use the custom form
    list_display = ('email', 'name', 'surname', 'role', 'active', 'approved')
    list_filter = ('role', 'active', 'approved')
    search_fields = ('email', 'name', 'surname', 'role')
    actions = ['approve_users', 'reject_users']

    fieldsets = (
        (None, {
            'fields': ('email', 'name', 'surname', 'role', 'active', 'approved')
        }),
        ('Personal Information', {
            'fields': ('phone', 'birthdate', 'city', 'university', 'field_of_study', 'interests', 'description', 'images', 'partner')
        }),
        ('Permissions', {
            'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Important Dates', {
            'fields': ('date_joined',)
        }),
    )

    def approve_users(self, request, queryset):
        queryset.update(approved=True)
    approve_users.short_description = "Approve selected users"

    def reject_users(self, request, queryset):
        queryset.update(approved=False)
    reject_users.short_description = "Reject selected users"