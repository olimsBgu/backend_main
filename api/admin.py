from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'surname', 'role', 'active', 'approved')
    list_filter = ('role', 'active', 'approved')
    search_fields = ('email', 'name', 'surname', 'role')
    actions = ['approve_users', 'reject_users']

    def approve_users(self, request, queryset):
        queryset.update(approved=True)
    approve_users.short_description = "Approve selected users"

    def reject_users(self, request, queryset):
        queryset.update(approved=False)
    reject_users.short_description = "Reject selected users"