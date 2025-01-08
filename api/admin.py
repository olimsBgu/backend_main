from django import forms
from django.contrib import admin

from .models import User


class UserAdminForm(forms.ModelForm):
    raw_login_code = forms.CharField(
        required=False,
        label="Login Code (raw)",
        help_text="Enter a raw login code to be hashed and saved. Leave blank to keep the current code.",
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional except for email
        for field_name, field in self.fields.items():
            if field_name not in set('email'):
                field.required = False

    def clean_raw_login_code(self):
        raw_login_code = self.cleaned_data.get("raw_login_code")
        if raw_login_code:
            # Validate the raw code if needed (e.g., length, characters, etc.)
            if len(raw_login_code) > 128:
                raise forms.ValidationError("The login code cannot exceed 128 characters.")
        return raw_login_code

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_login_code = self.cleaned_data.get("raw_login_code")
        if raw_login_code:
            # Hash and save the raw login code
            instance.set_login_code(raw_login_code)
        if commit:
            instance.save()
        return instance


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ('email', 'name', 'surname', 'role', 'active', 'approved')
    list_filter = ('role', 'active', 'approved')
    search_fields = ('email', 'name', 'surname', 'role')
    actions = ['approve_users', 'reject_users']

    fieldsets = (
        (None, {
            'fields': ('email', 'name', 'surname', 'role', 'active', 'approved')
        }),
        ('Personal Information', {
            'fields': (
            'phone', 'birthdate', 'city', 'university', 'field_of_study', 'interests', 'description', 'images',
            'partner')
        }),
        ('Login Code', {
            'fields': ('raw_login_code', 'hashed_login_code'),
        }),
        ('Permissions', {
            'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Important Dates', {
            'fields': ('date_joined',)
        }),
    )

    readonly_fields = ('hashed_login_code',)  # Make the hashed login code read-only

    def approve_users(self, request, queryset):
        queryset.update(approved=True)

    approve_users.short_description = "Approve selected users"

    def reject_users(self, request, queryset):
        queryset.update(approved=False)

    reject_users.short_description = "Reject selected users"