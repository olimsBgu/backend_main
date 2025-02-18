import logging
import traceback
from pathlib import Path

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect
from django.conf import settings
from django.urls import path

from .models import User, Interest, University, City, FieldOfStudy

logger = logging.getLogger(__name__)

DATA_DIR = Path(settings.BASE_DIR) / "data"


def read_data_file(file_name: str):
    """Reads a file and returns a list of its contents, handling errors safely."""
    file_path = DATA_DIR / file_name
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except Exception as e:
        logger.error(
            f"Failed to read {file_path}: {e}",
            traceback.format_exc(),
            exc_info=True)
        raise e


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


class DataUpdateAdmin(admin.ModelAdmin):
    """
    A reusable base admin class that:
      - Defines a custom URL for "update" actions.
      - Calls a read_data_file(file_name) helper to load lines from disk.
      - Creates or updates objects in a model.
      - Has a custom change_list_template with an "Update <something>" button.
    """
    # These class attributes should be overridden in subclasses:
    file_name = None  # e.g. "cities.txt"
    model_cls = None  # e.g. City
    update_url_name = None  # e.g. "update-cities"
    update_button_name = None  # e.g. "Update cities"

    change_list_template = "admin/api/update_list.html"

    def get_urls(self):
        """
        Add a custom URL that maps to the 'update_view' method.
        """
        urls = super().get_urls()
        my_urls = [
            path(
                f"{self.update_url_name}/",  # e.g. "update-cities/"
                self.admin_site.admin_view(self.update_view),
                name=self.update_url_name
            ),
        ]
        return my_urls + urls

    def changelist_view(self, request, extra_context=None):
        """
        Override to pass variables into the template for the link.
        """
        extra_context = extra_context or {}
        # The template uses these for the button:
        extra_context["variable_for_url"] = f"admin:{self.update_url_name}"
        extra_context["button_name"] = self.update_button_name
        return super().changelist_view(request, extra_context=extra_context)

    def update_view(self, request):
        """
        Generic "update" view that reads the file, creates objects, etc.
        """
        if not self.file_name or not self.model_cls:
            messages.error(request, "This admin is not properly configured.")
            return redirect("..")

        try:
            lines = read_data_file(self.file_name)
            count = 0
            for line in lines:
                _, created = self.model_cls.objects.get_or_create(name=line)
                if created:
                    count += 1

            messages.success(
                request,
                f"Successfully updated {len(lines)} lines. ({count} new {self.model_cls.__name__} objects created.)"
            )
        except Exception as e:
            short_error = str(e)[:100]
            messages.error(
                request,
                f"Error while updating {self.update_button_name}: {short_error}"
            )

        return redirect("..")


@admin.register(City)
class CityAdmin(DataUpdateAdmin):
    file_name = "cities.txt"
    model_cls = City
    update_url_name = "update-cities"
    update_button_name = "Update cities"
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(University)
class UniversityAdmin(DataUpdateAdmin):
    file_name = "universities.txt"
    model_cls = University
    update_url_name = "update-universities"
    update_button_name = "Update universities"
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Interest)
class InterestAdmin(DataUpdateAdmin):
    file_name = "interests.txt"
    model_cls = Interest
    update_url_name = "update-interests"
    update_button_name = "Update interests"
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(FieldOfStudy)
class FieldOfStudyAdmin(DataUpdateAdmin):
    file_name = "fields_of_study.txt"
    model_cls = FieldOfStudy
    update_url_name = "update-fields-of-study"
    update_button_name = "Update fields of study"
    list_display = ("id", "name")
    search_fields = ("name",)
