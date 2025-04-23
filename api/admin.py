import logging
import random
import traceback
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.timezone import now
from unfold.admin import ModelAdmin
from unfold.components import register_component, BaseComponent
from unfold.widgets import INPUT_CLASSES

from chat.models import Chat, ChatMessage
from .models import User, Interest, University, City, FieldOfStudy, Image, Pending, Match

logger = logging.getLogger(__name__)

DATA_DIR = Path(settings.BASE_DIR) / "data"

admin.site.site_url = None

@register_component
class UserRegistrationsChart(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        data = (
            User.objects
            .annotate(month=TruncMonth("date_joined"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        context.update({
            "labels": [item["month"].strftime("%b %Y") for item in data],
            "data": [item["count"] for item in data],
        })
        return context


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
        self.fields["raw_login_code"].widget.attrs["class"] = " ".join(INPUT_CLASSES)
        # Make all fields optional except for 'email'
        for field_name, field in self.fields.items():
            if field_name not in {"email"}:
                field.required = False

        if self.instance and self.instance.pk:
            # Exclude self from 'partner':
            self.fields["partner"].queryset = User.objects.exclude(pk=self.instance.pk)

            # Exclude self from 'viewed_users':
            self.fields["viewed_users"].queryset = User.objects.exclude(pk=self.instance.pk)

            # Exclude self from 'saved_users':
            self.fields["saved_users"].queryset = User.objects.exclude(pk=self.instance.pk)

    def clean_raw_login_code(self):
        raw_login_code = self.cleaned_data.get("raw_login_code")
        if raw_login_code:
            # Validate the raw code if needed (e.g., length, characters, etc.)
            if len(raw_login_code) > 128:
                raise forms.ValidationError("The login code cannot exceed 128 characters.")
        return raw_login_code

    def clean_partner(self):
        partner = self.cleaned_data.get("partner")
        if partner and self.instance and partner == self.instance:
            raise forms.ValidationError("A user cannot be their own partner.")
        return partner

    def clean_viewed_users(self):
        viewed = self.cleaned_data.get("viewed_users")
        if self.instance and self.instance in viewed:
            raise forms.ValidationError("A user cannot view themselves.")
        return viewed

    def clean_saved_users(self):
        saved = self.cleaned_data.get("saved_users")
        if self.instance and self.instance in saved:
            raise forms.ValidationError("A user cannot save themselves.")
        return saved

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_login_code = self.cleaned_data.get("raw_login_code")
        if raw_login_code:
            # Hash and save the raw login code
            instance.set_login_code(raw_login_code)
        if commit:
            instance.save()
        return instance


class MatchAdminForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        user_a = cleaned_data.get("user_a")
        user_b = cleaned_data.get("user_b")
        if user_a and user_b and user_a == user_b:
            raise forms.ValidationError("A match cannot have the same user as user_a and user_b.")
        return cleaned_data


class PendingAdminForm(forms.ModelForm):
    class Meta:
        model = Pending
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        from_user = cleaned_data.get("from_user")
        to_user = cleaned_data.get("to_user")
        if from_user and to_user and from_user == to_user:
            raise forms.ValidationError("A user cannot like themselves (Pending from_user == to_user).")
        return cleaned_data


class ImageInline(admin.TabularInline):
    model = Image
    extra = 1  # number of empty inlines
    readonly_fields = ("preview",)
    fields = ("preview", "file",)  # Show a small thumbnail and the file field

    def preview(self, obj):
        if obj.file:
            return format_html(
                '<img src="{}" style="max-height: 100px;" />', obj.file.url
            )
        return ""

    preview.short_description = "Preview"


@admin.register(User)
class UserAdmin(ModelAdmin):
    form = UserAdminForm
    list_display = ('email', 'name', 'surname', 'user_type', 'active', 'approved')
    list_filter = ('user_type', 'active', 'approved')
    search_fields = ('email', 'name', 'surname', 'user_type')
    actions = ['approve_users', 'reject_users']

    inlines = [ImageInline]

    fieldsets = (
        (None, {
            'fields': ('public_id', 'email', 'name', 'surname', 'role', 'active', 'approved')
        }),
        ('Personal Information', {
            'fields': (
                'phone', 'birthdate', 'city', 'university', 'field_of_study',
                'interests', 'description', 'partner', 'user_type'
            )
        }),
        ('User Interactions', {
            'fields': ('viewed_users', 'saved_users')
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

    readonly_fields = ('public_id', 'hashed_login_code',)  # Make the hashed login code read-only

    def approve_users(self, request, queryset):
        queryset.update(approved=True)

    approve_users.short_description = "Approve selected users"

    def reject_users(self, request, queryset):
        queryset.update(approved=False)

    reject_users.short_description = "Reject selected users"

    # (1) Filter horizontal can provide a nicer UX for M2M fields
    filter_horizontal = ('viewed_users', 'saved_users', 'interests')


@admin.register(Pending)
class PendingAdmin(ModelAdmin):
    form = PendingAdminForm

    list_display = ('id', 'from_user', 'to_user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('from_user__email', 'to_user__email')
    date_hierarchy = 'created_at'


@admin.register(Match)
class MatchAdmin(ModelAdmin):
    form = MatchAdminForm

    list_display = ('id', 'user_a', 'user_b', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user_a__email', 'user_b__email')
    date_hierarchy = 'created_at'


class DataUpdateAdmin(ModelAdmin):
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


@lru_cache
def cohort_random_data():
    rows = []
    headers = []
    cols = []

    dates = reversed(
        [(now() - timedelta(days=x)).strftime("%B %d, %Y") for x in range(8)]
    )
    groups = range(1, 10)

    for row_index, date in enumerate(dates):
        cols = []

        for col_index, _col in enumerate(groups):
            color_index = 8 - row_index - col_index
            col_classes = []

            if color_index > 0:
                col_classes.append(
                    f"bg-primary-{color_index}00 dark:bg-primary-{9 - color_index}00"
                )

            if color_index >= 4:
                col_classes.append("text-white dark:text-base-600")

            value = random.randint(
                4000 - (col_index * row_index * 225),
                5000 - (col_index * row_index * 225),
            )

            subtitle = f"{random.randint(10, 100)}%"

            if value <= 0:
                value = 0
                subtitle = None

            cols.append(
                {
                    "value": value,
                    "color": " ".join(col_classes),
                    "subtitle": subtitle,
                }
            )

        rows.append(
            {
                "header": {
                    "title": date,
                    "subtitle": f"Total {sum(col['value'] for col in cols):,}",
                },
                "cols": cols,
            }
        )

    for index, group in enumerate(groups):
        total = sum(row["cols"][index]["value"] for row in rows)

        headers.append(
            {
                "title": f"Group #{group}",
                "subtitle": f"Total {total:,}",
            }
        )

    return {
        "headers": headers,
        "rows": rows,
    }

@register_component
class CohortComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["data"] = cohort_random_data()
        return context

class ChatCreateForm(forms.ModelForm):
    """
    Custom 'add chat' form that presents two user selectors instead of
    the raw ManyToMany widget.
    """
    user_a = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=AutocompleteSelect(Chat._meta.get_field("users"), admin.site),
        label="User A",
        help_text="First participant",
    )
    user_b = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=AutocompleteSelect(Chat._meta.get_field("users"), admin.site),
        label="User B",
        help_text="Second participant",
    )

    class Meta:
        model   = Chat
        fields  = ("user_a", "user_b")  # we hide ws_key & users m2m

    def clean(self):
        cleaned = super().clean()
        a, b = cleaned.get("user_a"), cleaned.get("user_b")

        if a and b and a == b:
            raise ValidationError("A user cannot chat with themselves.")
        return cleaned

    def save_m2m(self):
        pass

    def save(self, commit=True):
        a, b = self.cleaned_data["user_a"], self.cleaned_data["user_b"]

        # Build canonical key (same order no matter who is first)
        sorted_ids = sorted([str(a.public_id), str(b.public_id)])
        ws_key = f"chat_{'_'.join(sorted_ids)}"

        chat, created = Chat.objects.get_or_create(ws_key=ws_key)

        # Ensure exactly the two chosen users are set
        chat.users.set([a, b], clear=True)

        if commit:
            chat.save()

        # Let the admin know if we re-used an existing chat
        self._created = created
        return chat


@admin.register(Chat)
class ChatAdmin(ModelAdmin):
    autocomplete_fields = ("users",)

    list_display = (
        "details_link",          # ← new first column
        "user_a_email",
        "user_b_email",
        "message_count",
        "last_message_at",
    )
    list_display_links = ("details_link",)  # only this column opens the chat

    readonly_fields = ("ws_key", "users")
    ordering = ("-messages__created_at",)
    search_fields = ("users__email", "users__name", "users__surname")

    def get_readonly_fields(self, request, obj=None):
        """
        Show ws_key & users only on the edit page (obj is not None).
        """
        return ("ws_key", "users") if obj else ()

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj is None:                                    # add-view
            return [f for f in fields if f not in ("ws_key", "users")]
        return fields

    # use custom form only in the “add” page
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = ChatCreateForm
        return super().get_form(request, obj, **kwargs)

    # -------- prettified columns ----------
    def _two_users(self, obj):
        """
        Returns the two participants ordered by email.
        """
        return obj.users.order_by("email")[:2]
    @admin.display(description="Details")
    def details_link(self, obj):
        url = reverse("admin:chat_chat_change", args=[obj.pk])
        return format_html(
            '<a href="{}" class="text-primary-500 font-semibold">open</a>', url
        )

    @admin.display(description="User A")
    def user_a_email(self, obj):
        user = self._two_users(obj)[0] if obj.users.count() else None
        return self._user_link(user)

    @admin.display(description="User B")
    def user_b_email(self, obj):
        users = self._two_users(obj)
        return self._user_link(users[1]) if len(users) == 2 else "-"

    def _user_link(self, user):
        if not user:
            return "-"
        url = reverse("admin:api_user_change", args=[user.pk])
        return format_html('<a href="{}">{}</a>', url, user.email)

    @admin.display(description="Messages")
    def message_count(self, obj):
        return obj.messages.count()

    @admin.display(description="Last message at", ordering="messages__created_at")
    def last_message_at(self, obj):
        last = obj.messages.order_by("-created_at").first()
        return last.created_at if last else "-"

    # nicer info message when we re-use an existing chat
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and isinstance(form, ChatCreateForm) and not getattr(form, "_created", True):
            self.message_user(
                request,
                "That chat already existed — re-using the same room.",
                messages.INFO,
            )